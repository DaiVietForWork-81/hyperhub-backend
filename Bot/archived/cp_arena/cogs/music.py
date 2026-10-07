from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from music.player import FFmpegNotFoundError, MusicPlayer, VoiceNotConnectedError
from music.provider import InvalidUrlError, TrackNotFoundError, UnsupportedSourceError
from utils import embeds, permissions
from utils.respond import reply

log = logging.getLogger(__name__)

CHANNEL_RESTRICTION_MSG = (
    "Bạn chỉ có thể thay đổi nhạc trong kênh #change-music."
)
COOLDOWN_REJECTED_MSG = (
    "Bạn đã sử dụng lượt đổi nhạc hôm nay.\n"
    "Bạn có thể đổi nhạc lại vào ngày mai."
)


class MusicCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def settings(self):
        return self.bot.settings

    @property
    def player(self) -> MusicPlayer:
        return self.bot.player

    @property
    def cooldowns(self):
        return self.bot.cooldowns

    async def _ensure_change_channel(self, interaction: discord.Interaction) -> bool:
        if permissions.in_change_channel(interaction, self.settings):
            return True
        log.info(
            "Chặn lệnh ở sai kênh - user %s, channel %s",
            interaction.user.id,
            interaction.channel_id,
        )
        await reply(interaction, embeds.error(CHANNEL_RESTRICTION_MSG, title="Sai kênh"))
        return False

    @app_commands.command(
        name="play",
        description="Phát nhạc từ URL hoặc từ khoá tìm kiếm (giới hạn 1 lần/ngày)",
    )
    @app_commands.describe(query="URL YouTube/Spotify hoặc từ khoá tìm kiếm")
    async def play(self, interaction: discord.Interaction, query: str) -> None:
        if not await self._ensure_change_channel(interaction):
            return
        await interaction.response.defer(ephemeral=True)

        try:
            tracks = await self.bot.extractor.resolve(query)
        except InvalidUrlError:
            await reply(interaction, embeds.error("URL không hợp lệ. Hãy kiểm tra lại đường dẫn."))
            return
        except UnsupportedSourceError:
            await reply(interaction, embeds.error("Nguồn nhạc này hiện chưa được hỗ trợ."))
            return
        except TrackNotFoundError:
            log.warning("Không tìm thấy bài hát theo query")
            await reply(interaction, embeds.error("Không tìm thấy bài hát nào khớp với yêu cầu."))
            return
        except Exception:
            log.exception("Lỗi khi resolve query")
            await reply(interaction, embeds.error("Lỗi hệ thống khi tìm kiếm bài hát, hãy thử lại sau."))
            return

        if not tracks:
            await reply(interaction, embeds.error("Không tìm thấy bài hát nào."))
            return

        try:
            await self.player.connect()
        except FFmpegNotFoundError:
            await reply(
                interaction,
                embeds.error("ffmpeg chưa được cài đặt trên máy chủ. Xem README để cài đặt."),
            )
            return
        except VoiceNotConnectedError:
            await reply(
                interaction,
                embeds.error(
                    "Bot chưa vào voice channel. Kiểm tra MUSIC_ID.",
                    title="Không kết nối được",
                ),
            )
            return
        except Exception:
            log.exception("Lỗi khi join voice channel")
            await reply(interaction, embeds.error("Lỗi hệ thống khi kết nối voice channel."))
            return

        user = interaction.user
        unlimited = permissions.has_unlimited_role(user, self.settings)
        if not unlimited:
            allowed, _last = await self.cooldowns.can_change(user.id)
            if not allowed:
                log.info("User cooldown rejected - user %s", user.id)
                await reply(interaction, embeds.error(COOLDOWN_REJECTED_MSG, title="Hết lượt hôm nay"))
                return
            await self.cooldowns.record_change(user.id)

        for track in tracks:
            track.requested_by = user.id
        first_track = tracks[0]
        extra_tracks = tracks[1:]

        position = await self.player.play_track(first_track)
        for extra in extra_tracks:
            await self.player.queue.add(extra)

        log.info("User requested song - %s by user %s", first_track.title, user.id)
        description = f"Đã thêm vào hàng chờ: **{first_track.title}**"
        if extra_tracks:
            description += f"\n{len(extra_tracks)} bài khác được thêm từ playlist."
        embed = embeds.success(description, title="Đã thêm vào queue")
        embed.add_field(name="Vị trí", value=f"#{position}", inline=True)
        await reply(interaction, embed)

    @app_commands.command(name="skip", description="Bỏ qua bài hát hiện tại")
    async def skip(self, interaction: discord.Interaction) -> None:
        if not await self._ensure_change_channel(interaction):
            return
        if self.player.current_track is None and await self.player.queue.size() == 0:
            await reply(
                interaction,
                embeds.error("Queue trống, không có bài nào để skip.", title="Không thể skip"),
            )
            return
        skipped = await self.player.skip()
        message = f"Đã bỏ qua: **{skipped.title}**" if skipped else "Đã bỏ qua bài hiện tại."
        await reply(interaction, embeds.success(message, title="Skip"))

    @app_commands.command(name="pause", description="Tạm dừng phát nhạc")
    async def pause(self, interaction: discord.Interaction) -> None:
        if not await self._ensure_change_channel(interaction):
            return
        if await self.player.pause():
            await reply(interaction, embeds.success("Đã tạm dừng phát nhạc.", title="Pause"))
        else:
            await reply(interaction, embeds.error("Không có bài nào đang phát để tạm dừng."))

    @app_commands.command(name="resume", description="Tiếp tục phát nhạc")
    async def resume(self, interaction: discord.Interaction) -> None:
        if not await self._ensure_change_channel(interaction):
            return
        if await self.player.resume():
            await reply(interaction, embeds.success("Đã tiếp tục phát nhạc.", title="Resume"))
        else:
            await reply(interaction, embeds.error("Nhạc không đang tạm dừng."))

    @app_commands.command(name="stop", description="Dừng phát nhạc và xoá toàn bộ hàng chờ")
    async def stop(self, interaction: discord.Interaction) -> None:
        if not await self._ensure_change_channel(interaction):
            return
        await self.player.stop()
        await reply(interaction, embeds.success("Đã dừng phát nhạc và xoá hàng chờ.", title="Stop"))

    @app_commands.command(name="queue", description="Xem hàng chờ phát nhạc")
    async def queue(self, interaction: discord.Interaction) -> None:
        current = self.player.current_track
        up_next = await self.player.queue.items()
        await reply(interaction, embeds.queue(current, up_next))

    @app_commands.command(name="nowplaying", description="Xem bài hát đang phát")
    async def nowplaying(self, interaction: discord.Interaction) -> None:
        current = self.player.current_track
        if current is None:
            await reply(interaction, embeds.error("Không có bài hát nào đang phát.", title="Now Playing"))
            return
        up_next = await self.player.queue.items()
        await reply(interaction, embeds.now_playing(current, up_next))

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        original = error.original if isinstance(error, app_commands.CommandInvokeError) else error
        log.exception("Slash command lỗi - %s", original)
        if not interaction.response.is_done():
            embed = embeds.error("Lỗi hệ thống không mong muốn. Đã ghi log để xử lý.", title="Lỗi hệ thống")
            await reply(interaction, embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MusicCommands(bot))