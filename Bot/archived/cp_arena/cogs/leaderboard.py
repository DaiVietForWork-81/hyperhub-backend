"""Kênh UP_RANK: Bảng xếp hạng 2 Embeds song song (Freedom Mode & Ranked 1:1) kèm điều hướng phân trang và tự động cập nhật mỗi 45 phút."""

import asyncio
import datetime
import math

import discord
from discord.ext import commands

from config.settings import settings
from database.database import async_session_factory
from database.repositories.user_repo import UserRepository
from services.rank import get_rank_badge
from utils.embeds import EmbedType, create_embed, get_logo_file
from utils.logger import get_logger

logger = get_logger("LeaderboardCog")

PAGE_SIZE_RANK_CHANNEL = 15
MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}
AUTO_UPDATE_INTERVAL = 45 * 60  # Tự động cập nhật mỗi 45 phút (2700 giây)


class RankChannelLeaderboardView(discord.ui.View):
    """Bảng điều khiển Bảng Xếp Hạng 2 Embeds (Freedom + Ranked 1:1) dành riêng cho kênh UP_RANK."""

    def __init__(self, bot: commands.Bot, page: int = 1):
        super().__init__(timeout=None)  # Persistent View
        self.bot = bot
        self.page = page
        self._rebuild_components(total_pages=1)

    def _rebuild_components(self, total_pages: int) -> None:
        self.clear_items()
        self.page = max(1, min(self.page, max(1, total_pages)))

        # Nút điều hướng phân trang (Row 0)
        btn_first = discord.ui.Button(
            label="⏮️",
            style=discord.ButtonStyle.secondary,
            disabled=(self.page <= 1),
            custom_id="btn_rank_first",
            row=0,
        )
        btn_prev = discord.ui.Button(
            label="◀️",
            style=discord.ButtonStyle.primary,
            disabled=(self.page <= 1),
            custom_id="btn_rank_prev",
            row=0,
        )
        btn_info = discord.ui.Button(
            label=f"Trang {self.page}/{total_pages}",
            style=discord.ButtonStyle.secondary,
            disabled=True,
            custom_id="btn_rank_info",
            row=0,
        )
        btn_next = discord.ui.Button(
            label="▶️",
            style=discord.ButtonStyle.primary,
            disabled=(self.page >= total_pages),
            custom_id="btn_rank_next",
            row=0,
        )
        btn_last = discord.ui.Button(
            label="⏭️",
            style=discord.ButtonStyle.secondary,
            disabled=(self.page >= total_pages),
            custom_id="btn_rank_last",
            row=0,
        )
        btn_refresh = discord.ui.Button(
            label="🔄 Làm Mới Ngay",
            style=discord.ButtonStyle.success,
            custom_id="btn_rank_refresh",
            row=1,
        )

        btn_first.callback = self._on_first
        btn_prev.callback = self._on_prev
        btn_next.callback = self._on_next
        btn_last.callback = self._on_last
        btn_refresh.callback = self._on_refresh

        self.add_item(btn_first)
        self.add_item(btn_prev)
        self.add_item(btn_info)
        self.add_item(btn_next)
        self.add_item(btn_last)
        self.add_item(btn_refresh)

    async def render_embeds(self) -> tuple[discord.Embed, discord.Embed]:
        """Tạo 2 Embeds song song: [1] Freedom Mode BXH, [2] Ranked 1:1 Arena BXH."""
        async with async_session_factory() as session:
            repo = UserRepository(session)
            # 1. Lấy danh sách Freedom
            freedom_users, freedom_total = await repo.get_leaderboard(
                page=self.page,
                per_page=PAGE_SIZE_RANK_CHANNEL,
                sort_by="rating",
                include_retired=False,
            )
            # 2. Lấy danh sách Ranked 1:1
            ranked_users, ranked_total = await repo.get_leaderboard(
                page=self.page,
                per_page=PAGE_SIZE_RANK_CHANNEL,
                sort_by="ranked",
                include_retired=False,
            )

        max_total = max(freedom_total, ranked_total)
        total_pages = max(1, math.ceil(max_total / PAGE_SIZE_RANK_CHANNEL))
        self._rebuild_components(total_pages=total_pages)

        start_rank = (self.page - 1) * PAGE_SIZE_RANK_CHANNEL + 1
        now_str = datetime.datetime.now().strftime("%H:%M:%S")

        # ── Embed 1: Freedom Mode Leaderboard ──
        freedom_lines = []
        for i, u in enumerate(freedom_users, start=start_rank):
            medal = MEDALS.get(i, f"`#{i:02d}`")
            badge = get_rank_badge(u.rank)
            usr = self.bot.get_user(u.discord_id)
            if usr:
                name_str = f"**{usr.display_name}**"
            elif u.codeforces_handle:
                name_str = f"`{u.codeforces_handle}`"
            else:
                name_str = f"<@{u.discord_id}>"
            freedom_lines.append(
                f"{medal} {name_str} │ ⭐ **{u.rating}** pts │ {badge} **{u.rank}** │ 🎯 {u.total_solved} AC"
            )

        freedom_desc = (
            f"**🏆 TOP {PAGE_SIZE_RANK_CHANNEL} — FREEDOM RATING (PTS)**\n"
            f"👥 **{freedom_total}** thí sinh  •  🕐 Cập nhật lúc `{now_str}`\n\n"
            + (
                "\n".join(freedom_lines)
                if freedom_lines
                else "*Chưa có dữ liệu thí sinh.*"
            )
        )

        # Bảo vệ giới hạn an toàn 2200 ký tự mỗi embed (tránh lỗi Discord vượt 6000 ký tự tổng)
        MAX_DESC_LEN = 2200
        if len(freedom_desc) > MAX_DESC_LEN:
            freedom_desc = freedom_desc[:MAX_DESC_LEN] + "\n... *(Bấm ◀️ ▶️ để xem các trang)*"

        embed_freedom = create_embed(
            title="🌟 [1] BẢNG XẾP HẠNG FREEDOM MODE (CONTEST & CODEFORCES)",
            description=freedom_desc,
            embed_type=EmbedType.LEADERBOARD,
            color=0x1E90FF,
            footer_text=f"Trang {self.page}/{total_pages}  •  Tự động cập nhật mỗi 45 phút  •  Không tính RHT1",
        )

        # ── Embed 2: Ranked 1:1 Arena Leaderboard ──
        ranked_lines = []
        for i, u in enumerate(ranked_users, start=start_rank):
            medal = MEDALS.get(i, f"`#{i:02d}`")
            r_badge = get_rank_badge(u.ranked_rank)
            total_matches = u.ranked_wins + u.ranked_losses
            win_rate = (
                (u.ranked_wins / total_matches * 100.0) if total_matches > 0 else 0.0
            )
            usr = self.bot.get_user(u.discord_id)
            if usr:
                name_str = f"**{usr.display_name}**"
            elif u.codeforces_handle:
                name_str = f"`{u.codeforces_handle}`"
            else:
                name_str = f"<@{u.discord_id}>"
            ranked_lines.append(
                f"{medal} {name_str} │ ⭐ **{u.ranked_rating}** pts │ {r_badge} **{u.ranked_rank}** │ 🏆 `{u.ranked_wins}W - {u.ranked_losses}L` *({win_rate:.0f}%)*"
            )

        ranked_desc = (
            f"**⚔️ TOP {PAGE_SIZE_RANK_CHANNEL} — RANKED 1:1 ARENA RATING**\n"
            f"👥 **{ranked_total}** đấu thủ  •  🕐 Cập nhật lúc `{now_str}`\n\n"
            + (
                "\n".join(ranked_lines)
                if ranked_lines
                else "*Chưa có dữ liệu đấu thủ.*"
            )
        )
        if len(ranked_desc) > MAX_DESC_LEN:
            ranked_desc = ranked_desc[:MAX_DESC_LEN] + "\n... *(Bấm ◀️ ▶️ để xem các trang)*"

        embed_ranked = create_embed(
            title="⚔️ [2] BẢNG XẾP HẠNG ĐẤU TRƯỜNG RANKED 1:1 (DUEL ARENA)",
            description=ranked_desc,
            embed_type=EmbedType.JUDGE,
            color=0xE74C3C,
            footer_text=f"Trang {self.page}/{total_pages}  •  Tự động cập nhật mỗi 45 phút  •  Không tính RHT1",
        )

        return embed_freedom, embed_ranked

    async def _on_first(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        self.page = 1
        embed_freedom, embed_ranked = await self.render_embeds()
        await interaction.edit_original_response(
            embeds=[embed_freedom, embed_ranked], view=self
        )

    async def _on_prev(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        if self.page > 1:
            self.page -= 1
        embed_freedom, embed_ranked = await self.render_embeds()
        await interaction.edit_original_response(
            embeds=[embed_freedom, embed_ranked], view=self
        )

    async def _on_next(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        self.page += 1
        embed_freedom, embed_ranked = await self.render_embeds()
        await interaction.edit_original_response(
            embeds=[embed_freedom, embed_ranked], view=self
        )

    async def _on_last(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        async with async_session_factory() as session:
            repo = UserRepository(session)
            _, freedom_total = await repo.get_leaderboard(
                page=1,
                per_page=PAGE_SIZE_RANK_CHANNEL,
                sort_by="rating",
                include_retired=False,
            )
            _, ranked_total = await repo.get_leaderboard(
                page=1,
                per_page=PAGE_SIZE_RANK_CHANNEL,
                sort_by="ranked",
                include_retired=False,
            )
        max_total = max(freedom_total, ranked_total)
        self.page = max(1, math.ceil(max_total / PAGE_SIZE_RANK_CHANNEL))
        embed_freedom, embed_ranked = await self.render_embeds()
        await interaction.edit_original_response(
            embeds=[embed_freedom, embed_ranked], view=self
        )

    async def _on_refresh(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        embed_freedom, embed_ranked = await self.render_embeds()
        await interaction.edit_original_response(
            embeds=[embed_freedom, embed_ranked], view=self
        )


class LeaderboardCog(commands.Cog, name="Leaderboard"):
    """Lệnh hiển thị bảng xếp hạng thành viên thi đấu trên server và quản lý kênh UP_RANK."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._live_message: discord.Message | None = None
        self._live_view: RankChannelLeaderboardView | None = None
        self._auto_update_task: asyncio.Task | None = None

    # ──────────────────────── Auto-update background loop ────────────────────────

    def start_auto_update(self) -> None:
        """Khởi động vòng lặp tự động cập nhật bảng xếp hạng mỗi 45 phút."""
        if self._auto_update_task and not self._auto_update_task.done():
            return
        self._auto_update_task = asyncio.create_task(self._auto_update_loop())
        logger.info(
            f"Bắt đầu tự động cập nhật 2 Bảng Xếp Hạng mỗi {AUTO_UPDATE_INTERVAL // 60} phút."
        )

    def stop_auto_update(self) -> None:
        if self._auto_update_task:
            self._auto_update_task.cancel()
            self._auto_update_task = None

    async def _auto_update_loop(self) -> None:
        await self.bot.wait_until_ready()
        while True:
            await asyncio.sleep(AUTO_UPDATE_INTERVAL)
            try:
                if self._live_message and self._live_view:
                    embed_freedom, embed_ranked = await self._live_view.render_embeds()
                    await self._live_message.edit(
                        embeds=[embed_freedom, embed_ranked], view=self._live_view
                    )
                    logger.info(
                        "Đã tự động cập nhật 2 Embeds Bảng Xếp Hạng (Freedom & Ranked 1:1)."
                    )
            except discord.NotFound:
                self._live_message = None
                logger.warning("Tin nhắn bảng xếp hạng đã bị xóa. Dừng auto-update.")
                break
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Lỗi tự động cập nhật bảng xếp hạng: {e}")

    def cog_unload(self) -> None:
        self.stop_auto_update()

    # ──────────────────────── Setup channel ────────────────────────

    async def auto_setup_rank_channel(self) -> None:
        """Tự động xóa tin nhắn cũ, đăng 2 Embeds Bảng Xếp Hạng (Freedom & Ranked 1:1) và khởi động auto-update 45 phút."""
        if not settings.UP_RANK or settings.UP_RANK <= 0:
            return
        channel = self.bot.get_channel(settings.UP_RANK)
        if not channel or not isinstance(channel, discord.TextChannel):
            return
        try:
            try:
                await channel.purge(limit=50)
            except Exception:
                pass

            view = RankChannelLeaderboardView(bot=self.bot, page=1)
            embed_freedom, embed_ranked = await view.render_embeds()
            logo_file = get_logo_file()
            if logo_file:
                msg = await channel.send(
                    embeds=[embed_freedom, embed_ranked], file=logo_file, view=view
                )
            else:
                msg = await channel.send(
                    embeds=[embed_freedom, embed_ranked], view=view
                )

            self._live_message = msg
            self._live_view = view
            self.start_auto_update()
            logger.info(
                "Đã làm mới 2 Embeds Bảng Xếp Hạng và khởi động auto-update 45 phút."
            )
        except Exception as e:
            logger.error(f"Lỗi khi tự động thiết lập kênh UP_RANK: {e}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LeaderboardCog(bot))
