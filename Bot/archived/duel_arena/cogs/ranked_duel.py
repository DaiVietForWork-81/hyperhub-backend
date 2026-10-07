import os
import random
import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select

from config.settings import settings
from database.database import async_session_factory
from database.models import DuelMatch
from database.repositories.user_repo import UserRepository
from services.duel_service import MatchmakingManager
from services.rank import get_rank_badge, get_rank_by_rating, get_rank_name
from utils.embeds import EmbedType, create_embed
from utils.logger import get_logger

logger = get_logger("RankedDuelCog")


async def grant_spectator_permission(session, member: discord.Member) -> discord.Embed:
    """Cấp quyền Khán giả cho một thành viên và trả về Embed thông báo."""
    import inspect

    res = session.channel.set_permissions(
        member,
        read_messages=True,
        send_messages=False,
        add_reactions=False,
        create_public_threads=False,
        create_private_threads=False,
        send_messages_in_threads=False,
        reason=f"Khán giả {getattr(member, 'display_name', member.id)} tham gia theo dõi trận #{session.match_code}",
    )
    if inspect.isawaitable(res):
        await res

    match_type = "Trận Giao Hữu" if getattr(session, "is_custom_match", False) else "Đấu Trường Ranked 1:1"
    p1_rank = getattr(session, "p1_ranked_rank", "T8")
    p2_rank = getattr(session, "p2_ranked_rank", "T8")
    p1_badge = get_rank_badge(p1_rank)
    p2_badge = get_rank_badge(p2_rank)
    p1_name = getattr(session.player1, "display_name", "P1")
    p2_name = getattr(session.player2, "display_name", "P2")
    ch_mention = getattr(session.channel, "mention", f"#{getattr(session.channel, 'name', 'duel')}")

    embed = discord.Embed(
        title=f"👁️ CHẾ ĐỘ KHÁN GIẢ • TRẬN #{session.match_code.upper()}",
        description=(
            f"Bạn đã được cấp quyền theo dõi trực tiếp **{match_type}** giữa:\n\n"
            f"⚔️ **{p1_name}** ({p1_badge} `{p1_rank}`) **VS** **{p2_name}** ({p2_badge} `{p2_rank}`)\n\n"
            f"• 🏟️ **Phòng đấu:** {ch_mention}\n"
            f"• ⏱️ **Chặng hiện tại:** Chặng {session.current_round}\n"
            f"• ❤️ **Mạng sinh lực:** {p1_name} (`{session.p1_lives}/2`) | {p2_name} (`{session.p2_lives}/2`)\n\n"
            f"🔒 **Quy định Khán giả:** Bạn chỉ có quyền **xem trực tiếp**, tuyệt đối **không thể nhắn tin hay thả reaction** để đảm bảo sự tập trung tối đa cho hai đấu thủ!"
        ),
        color=0x9B59B6,
    )
    return embed


class SpectatorJumpView(discord.ui.View):
    """View cung cấp nút bấm chuyển thẳng tới phòng thi đấu."""

    def __init__(self, jump_url: str | None = None):
        super().__init__(timeout=180)
        if jump_url and str(jump_url).startswith("http"):
            self.add_item(
                discord.ui.Button(
                    label="Vào Phòng Đấu 🏟️",
                    style=discord.ButtonStyle.link,
                    url=jump_url,
                )
            )


class SpectatorMatchSelect(discord.ui.Select):
    """Dropdown menu danh sách các trận đấu đang diễn ra để khán giả chọn vào xem."""

    def __init__(self, active_matches: list, matchmaker: MatchmakingManager):
        self.matchmaker = matchmaker
        options = []
        for s in active_matches[:25]:
            m_type = "Custom" if s.is_custom_match else "Ranked"
            p1_n = s.player1.display_name[:12]
            p2_n = s.player2.display_name[:12]
            label = f"#{s.match_code.upper()} • {p1_n} vs {p2_n}"
            desc = f"[{m_type}] Chặng {s.current_round} • Mạng: {s.p1_lives}v{s.p2_lives}"
            options.append(
                discord.SelectOption(
                    label=label,
                    value=s.match_code,
                    description=desc,
                    emoji="⚔️" if not s.is_custom_match else "🤝",
                )
            )
        super().__init__(
            placeholder="👉 Chọn một trận đấu để vào xem trực tiếp...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="select_spectate_match",
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        member = interaction.user
        if not isinstance(member, discord.Member):
            return

        selected_code = self.values[0]
        target_session = next(
            (
                s for s in self.matchmaker.active_sessions.values()
                if s.is_active and s.channel and s.match_code.lower() == selected_code.lower()
            ),
            None,
        )

        if not target_session:
            await interaction.followup.send(
                "❌ Trận đấu này vừa kết thúc hoặc không còn khả dụng.", ephemeral=True
            )
            return

        if member.id in (target_session.player1.id, target_session.player2.id):
            await interaction.followup.send(
                f"⚔️ Bạn đang là đấu thủ chính thức của trận đấu này! Kênh thi đấu: {target_session.channel.mention}",
                ephemeral=True,
            )
            return

        try:
            embed = await grant_spectator_permission(target_session, member)
            jump_url = getattr(target_session.channel, "jump_url", None)
            view = SpectatorJumpView(jump_url)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            logger.info(f"Khán giả {member.display_name} ({member.id}) đã vào xem trận #{target_session.match_code}")
        except Exception as e:
            logger.warning(f"Lỗi khi cấp quyền khán giả cho {member.display_name}: {e}")
            await interaction.followup.send(
                f"❌ Không thể vào phòng theo dõi trận đấu lúc này: {e}",
                ephemeral=True,
            )


class SpectatorMatchSelectView(discord.ui.View):
    """View cung cấp danh sách dropdown để chọn trận vào xem trực tiếp (ephemeral)."""

    def __init__(self, active_matches: list, matchmaker: MatchmakingManager):
        super().__init__(timeout=180)
        self.add_item(SpectatorMatchSelect(active_matches, matchmaker))


class RankedArenaView(discord.ui.View):
    """Bảng điều khiển tương tác tham gia và quản lý hàng chờ Ranked 1:1."""

    def __init__(self, matchmaker: MatchmakingManager):
        super().__init__(timeout=None)
        self.matchmaker = matchmaker

    @discord.ui.button(
        label="⚔️ Tìm Trận Đấu (Tham gia 1:1)",
        style=discord.ButtonStyle.success,
        custom_id="btn_join_ranked_duel",
        row=0,
    )
    async def join_duel_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer(ephemeral=True)
        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.followup.send(
                "❌ Lỗi: Không xác định được thành viên server.", ephemeral=True
            )
            return

        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.followup.send(
                "❌ Lỗi: Kênh không hợp lệ.", ephemeral=True
            )
            return

        # Chế độ Beta: Tạm khóa hàng chờ Ranked, chỉ mở cho Owner & Quản trị viên
        is_admin_or_owner = (
            member.id == settings.OWNER_ID
            or (interaction.guild and member.id == interaction.guild.owner_id)
            or member.guild_permissions.administrator
        )
        if not is_admin_or_owner:
            await interaction.followup.send(
                "🔒 **ĐẤU TRƯỜNG RANKED 1:1 ĐANG TRONG GIAI ĐOẠN BETA**\n"
                "Hàng chờ thi đấu Ranked 1:1 đang tạm khóa để nâng cấp thêm hệ thống.\n"
                "Hiện tại tính năng chỉ mở riêng cho **Owner & Ban Quản Trị** tham gia thử nghiệm. Vui lòng đón chờ bản mở rộng sắp tới!",
                ephemeral=True,
            )
            return

        ok, embed, session = await self.matchmaker.add_to_queue(member, channel)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(
        label="❌ Rời Hàng Chờ",
        style=discord.ButtonStyle.secondary,
        custom_id="btn_leave_ranked_duel",
        row=0,
    )
    async def leave_duel_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer(ephemeral=True)
        removed = self.matchmaker.remove_from_queue(interaction.user.id)
        if removed:
            embed = create_embed(
                title="✅ ĐÃ RỜI HÀNG CHỜ",
                description="Bạn đã hủy tìm trận đấu Ranked 1:1 thành công.",
                embed_type=EmbedType.INFO,
                color=0x95A5A6,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            embed = create_embed(
                title="ℹ️ THÔNG BÁO",
                description="Bạn hiện không có trong hàng chờ ghép trận.",
                embed_type=EmbedType.INFO,
                color=0x3498DB,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(
        label="📊 Thống Kê Ranked Của Tôi",
        style=discord.ButtonStyle.primary,
        custom_id="btn_my_ranked_stats",
        row=0,
    )
    async def my_stats_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer(ephemeral=True)
        async with async_session_factory() as session:
            repo = UserRepository(session)
            user, _ = await repo.get_or_create(interaction.user.id)

        badge = get_rank_badge(user.ranked_rank)
        rank_full = get_rank_name(user.ranked_rank)
        freedom_badge = get_rank_badge(user.rank)

        overall_pts = (user.rating + user.ranked_rating) / 2.0
        overall_rank = get_rank_by_rating(int(overall_pts))
        overall_badge = get_rank_badge(overall_rank)

        desc = (
            f"### 🛡️ HỒ SƠ THI ĐẤU RANKED 1:1: {interaction.user.mention}\n\n"
            f"• **Điểm Overall Tổng Hợp:** {overall_badge} `⭐ {overall_pts:.1f} pts` *[(Freedom + Ranked) / 2]*\n"
            f"• **Bậc Rank Ranked:** {badge} `{user.ranked_rank}` *({rank_full})*\n"
            f"• **Điểm Rating Ranked:** `⭐ {user.ranked_rating} pts` *(Cao nhất: `{user.ranked_max_rating} pts`)*\n"
            f"• **Thành tích đối đầu:** 🏆 `{user.ranked_wins} Thắng` • 💀 `{user.ranked_losses} Thua` • ⚖️ `{user.ranked_draws} Hòa`\n"
            f"• **Tỷ lệ thắng:** `{(user.ranked_wins / max(1, user.ranked_wins + user.ranked_losses) * 100):.1f}%`\n\n"
            f"• **Bậc Rank Freedom:** {freedom_badge} `{user.rank}` (`⭐ {user.rating} pts`)\n"
            f"• **Trạng thái mở khóa Ranked:** {'🟢 Đã Mở Khóa' if user.rating >= 400 or user.rank != 'T8' else '🔒 Khóa (Cần ≥ T7 Freedom / 400 pts)'}"
        )

        embed = discord.Embed(
            title="📊 THÔNG SỐ ĐẤU TRƯỜNG RANKED 1:1",
            description=desc,
            color=0x9B59B6,
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(
        label="👁️ Xem Trực Tiếp (Khán Giả)",
        style=discord.ButtonStyle.secondary,
        custom_id="btn_ranked_spectate_random",
        row=1,
    )
    async def spectate_random_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer(ephemeral=True)
        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.followup.send(
                "❌ Lỗi: Không xác định được thành viên server.", ephemeral=True
            )
            return

        # Lấy danh sách các trận đấu 1:1 đang diễn ra
        active_matches = [
            s for s in self.matchmaker.active_sessions.values()
            if s.is_active and s.channel
        ]

        if not active_matches:
            await interaction.followup.send(
                "ℹ️ Hiện tại không có trận đấu Ranked 1:1 nào đang diễn ra! Hãy bấm **'⚔️ Tìm Trận Đấu'** để tự mình tham chiến.",
                ephemeral=True,
            )
            return

        if len(active_matches) == 1:
            session = active_matches[0]
            if member.id in (session.player1.id, session.player2.id):
                await interaction.followup.send(
                    f"⚔️ Bạn đang là đấu thủ chính thức trong trận này! Kênh thi đấu của bạn: {session.channel.mention}",
                    ephemeral=True,
                )
                return

            try:
                embed = await grant_spectator_permission(session, member)
                jump_url = getattr(session.channel, "jump_url", None)
                view = SpectatorJumpView(jump_url)
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
                logger.info(f"Khán giả {member.display_name} ({member.id}) đã vào xem trận #{session.match_code}")
            except Exception as e:
                logger.warning(f"Lỗi khi cấp quyền khán giả cho {member.display_name}: {e}")
                await interaction.followup.send(
                    f"❌ Không thể vào phòng theo dõi trận đấu lúc này: {e}",
                    ephemeral=True,
                )
            return

        # Nếu có nhiều trận đấu -> Hiển thị danh sách và dropdown để khán giả chọn (chỉ khán giả thấy)
        lines = []
        for idx, s in enumerate(active_matches, 1):
            m_type = "Giao Hữu" if s.is_custom_match else "Ranked 1:1"
            p1_str = f"{s.player1.display_name} ({s.p1_ranked_rank})"
            p2_str = f"{s.player2.display_name} ({s.p2_ranked_rank})"
            p1_hearts = "❤️" * s.p1_lives + "💔" * (2 - s.p1_lives)
            p2_hearts = "❤️" * s.p2_lives + "💔" * (2 - s.p2_lives)
            lines.append(
                f"**{idx}. [{m_type}]** Mã: **`{s.match_code.upper()}`** │ ⚔️ {p1_str} **VS** {p2_str} │ ⏱️ Chặng {s.current_round} ({p1_hearts} vs {p2_hearts})"
            )

        list_desc = (
            f"Hiện đang có **{len(active_matches)}** trận đấu đang diễn ra trong đấu trường.\n\n"
            + "\n".join(lines)
            + "\n\n👉 **Hãy chọn trận đấu từ menu bên dưới để vào theo dõi trực tiếp:**"
        )
        embed_list = discord.Embed(
            title="🏟️ DANH SÁCH TRẬN ĐẤU ĐANG DIỄN RA (CHẾ ĐỘ KHÁN GIẢ)",
            description=list_desc,
            color=0x9B59B6,
        )
        embed_list.set_footer(text="Chọn trận từ menu bên dưới • Hoặc dùng /view <id>")
        select_view = SpectatorMatchSelectView(active_matches, self.matchmaker)
        await interaction.followup.send(embed=embed_list, view=select_view, ephemeral=True)


class CustomMatchChallengeView(discord.ui.View):
    """View tương tác xác nhận lời mời thách đấu Custom Match qua DM (hoặc fallback channel)."""

    def __init__(
        self,
        matchmaker: MatchmakingManager,
        challenger: discord.Member,
        target_member: discord.Member,
        tier: str,
    ):
        super().__init__(timeout=90)
        self.matchmaker = matchmaker
        self.challenger = challenger
        self.target_member = target_member
        self.tier = tier.upper()
        self.responded = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.target_member.id:
            await interaction.response.send_message(
                "❌ Lời thách đấu này không dành cho bạn!", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(
        label="✅ Chấp Nhận",
        style=discord.ButtonStyle.success,
        custom_id="btn_accept_custom_duel",
    )
    async def accept_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if self.responded:
            return
        self.responded = True
        self.stop()

        for item in self.children:
            item.disabled = True

        if self.matchmaker.is_in_duel(self.challenger.id):
            await interaction.response.edit_message(
                content=f"⚠️ {self.challenger.mention} hiện đang trong một trận đấu khác!",
                view=self,
            )
            return

        if self.matchmaker.is_in_duel(self.target_member.id):
            await interaction.response.edit_message(
                content="⚠️ Bạn hiện đang trong một trận đấu khác!",
                view=self,
            )
            return

        from services.duel_service import DuelSession
        async with async_session_factory() as session:
            repo = UserRepository(session)
            u1, _ = await repo.get_or_create(self.challenger.id)
            u2, _ = await repo.get_or_create(self.target_member.id)
            p1_rank, p1_rating = u1.ranked_rank, u1.ranked_rating
            p2_rank, p2_rating = u2.ranked_rank, u2.ranked_rating

        duel_session = DuelSession(
            bot=self.matchmaker.bot,
            guild=self.challenger.guild,
            player1=self.challenger,
            player2=self.target_member,
            p1_ranked_rank=p1_rank,
            p1_ranked_rating=p1_rating,
            p2_ranked_rank=p2_rank,
            p2_ranked_rating=p2_rating,
            is_custom_match=True,
            custom_tier=self.tier,
        )

        started = await duel_session.start()
        if started and duel_session.channel:
            self.matchmaker.active_sessions[duel_session.channel.id] = duel_session
            await interaction.response.edit_message(
                content=(
                    f"✅ **BẠN ĐÃ CHẤP NHẬN LỜI THÁCH ĐẤU!**\n\n"
                    f"⚔️ Trận giao hữu độ khó `⭐ Tier {self.tier}` đã sẵn sàng tại {duel_session.channel.mention}!\n"
                    f"🚀 Mau vào phòng đấu để so tài thôi nào!"
                ),
                view=self,
            )
            try:
                await self.challenger.send(
                    f"🎉 {self.target_member.mention} đã chấp nhận lời thách đấu giao hữu của bạn!\n"
                    f"👉 Kênh thi đấu: {duel_session.channel.mention}"
                )
            except Exception:
                pass
        else:
            await interaction.response.edit_message(
                content="❌ Có lỗi xảy ra khi tạo phòng thi đấu. Vui lòng thử lại sau!",
                view=self,
            )

    @discord.ui.button(
        label="❌ Từ Chối",
        style=discord.ButtonStyle.danger,
        custom_id="btn_decline_custom_duel",
    )
    async def decline_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if self.responded:
            return
        self.responded = True
        self.stop()

        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(
            content=f"❌ Bạn đã từ chối lời thách đấu của {self.challenger.mention}.",
            view=self,
        )
        try:
            await self.challenger.send(
                f"ℹ️ {self.target_member.display_name} đã từ chối lời thách đấu giao hữu của bạn."
            )
        except Exception:
            pass

    async def on_timeout(self):
        if not self.responded:
            self.responded = True
            for item in self.children:
                item.disabled = True


class RankedDuelCog(commands.Cog):
    """Cog xử lý hệ thống Đấu Trường Ranked 1:1."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.matchmaker = MatchmakingManager(bot)
        self._initialized = False

    async def cog_load(self):
        """Khởi tạo persistent view khi cog load."""
        self.bot.add_view(RankedArenaView(self.matchmaker))

    @commands.Cog.listener()
    async def on_ready(self):
        """Dọn dẹp phân quyền ẩn mồ côi và khởi tạo giao diện kênh nếu chưa chạy."""
        await self._cleanup_orphaned_category_hides()
        if not self._initialized:
            self._initialized = True
            await self._auto_setup_ranked_channel()

    async def _cleanup_orphaned_category_hides(self) -> None:
        """Dọn dẹp các phân quyền ẩn danh mục còn sót lại từ các phiên đấu trước (nếu bot bị restart)."""
        hidden_cat_ids = getattr(
            settings,
            "RANKED_HIDDEN_CATEGORY_IDS",
            [1534147161091211414, 1534147951797080174, 1534148003701719070],
        )
        active_player_ids = set()
        for session in getattr(self.matchmaker, "active_sessions", {}).values():
            if getattr(session, "is_active", False):
                if getattr(session, "player1", None):
                    active_player_ids.add(session.player1.id)
                if getattr(session, "player2", None):
                    active_player_ids.add(session.player2.id)

        for guild in getattr(self.bot, "guilds", []):
            for cat_id in hidden_cat_ids:
                cat = guild.get_channel(cat_id)
                if cat and isinstance(cat, discord.CategoryChannel) and hasattr(cat, "overwrites"):
                    for target in list(cat.overwrites.keys()):
                        if isinstance(target, discord.Member):
                            if target.id not in active_player_ids:
                                ow = cat.overwrites[target]
                                if ow.view_channel is False or ow.connect is False:
                                    try:
                                        await cat.set_permissions(
                                            target,
                                            overwrite=None,
                                            reason="Khôi phục danh mục do bot khởi động lại hoặc trận đấu đã kết thúc",
                                        )
                                        logger.info(f"Đã khôi phục quyền danh mục {cat.name} cho thành viên {target.display_name} ({target.id})")
                                    except Exception as e:
                                        logger.debug(f"Không thể gỡ overwrite cho {target.id}: {e}")

    async def _auto_setup_ranked_channel(self) -> None:
        """Đăng 2 Embeds chuẩn luật & Trạm ghép trận tại kênh #📋・ranked."""
        self._initialized = True
        channel_id = settings.RANKED_CHANNEL_ID
        if not channel_id:
            return

        channel = self.bot.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            logger.warning(f"Không tìm thấy kênh RANKED_CHANNEL_ID: {channel_id}")
            return

        try:
            # Dọn dẹp tin nhắn cũ
            await channel.purge(limit=25)
        except discord.NotFound:
            pass
        except Exception as e:
            logger.debug(f"Bỏ qua lỗi purge kênh RANKED_CHANNEL_ID: {e}")

        # Embed 1: Luật thi đấu & Hệ thống 2 Mạng
        rules_desc = (
            "### ⚔️ CHÀO MỪNG ĐẾN VỚI ĐẤU TRƯỜNG RANKED 1:1\n"
            "> Chế độ thi đấu đối kháng trực tiếp theo thời gian thực giữa các thành viên Server HyperHub.\n\n"
            "### 1. 🎯 ĐIỀU KIỆN MỞ KHÓA & GHÉP TRẬN\n"
            "• **Điều kiện mở khóa:** Thí sinh phải đạt tối thiểu **⭐ Bậc T7 (Freedom)** (Rating Freedom `≥ 400 pts`).\n"
            "• **Phạm vi ghép đối thủ:** Hệ thống tự động ghép với đối thủ có Tier **ngang bằng hoặc chênh lệch tối đa 1 bậc** (`±1 Tier`).\n\n"
            "### 2. ❤️ HỆ THỐNG 2 MẠNG (HEARTS SYSTEM)\n"
            "• Mỗi đấu thủ khởi đầu với **2 Mạng (❤️ ❤️)**.\n"
            "• Sau mỗi bài toán, người có tỷ lệ test đúng vượt trội (chênh lệch `> 10%`) → Người thua bị **trừ 1 mạng (💔)**.\n"
            "• Nếu khoảng cách điểm `≤ 10%` → **Hòa vòng**, không ai bị trừ mạng.\n"
            "• Trận đấu kết thúc khi **1 người còn 0 mạng**.\n\n"
            "### 3. ⭐ CƠ CHẾ CỘNG / TRỪ ĐIỂM RATING DYNAMIC ELO (OPTION B)\n"
            "• **Đối đầu Cùng Tier:** Thắng `+60 pts` • Thua `-60 pts`\n"
            "• **Đánh Hơn 1 Tier (Kèo dưới lật kèo):** Thắng `+80 pts` (thưởng thêm) • Thua `-50 pts` (trừ nhẹ)\n"
            "• **Đánh Kém 1 Tier (Kèo trên gặp kèo dưới):** Thắng `+50 pts` • Thua `-80 pts` (phạt nặng nếu sẩy chân)\n"
            "• **Bonus chênh lệch Rating:** Điểm thưởng/phạt tự động cộng/trừ thêm dựa trên khoảng cách Rating thực tế giữa 2 người.\n"
            "• **Performance & Độ dài trận đấu (5 - 15 pts):** Kéo đối thủ mạnh hơn vào trận đấu càng dài (> 2 chặng) → Thắng được cộng thêm điểm (+5 đến +15 pts), Thua được giảm bớt điểm trừ! Ngược lại, để đối thủ yếu hơn kéo dài trận đấu sẽ bị giảm điểm thắng hoặc trừ nặng hơn.\n"
            "• **Quy tắc bảo toàn mạng**:\n"
            "  • **Người thắng (còn nguyên 2 mạng ❤️❤️):** Nhận 100% điểm thưởng\n"
            "  • **Người thắng (chỉ còn 1 mạng ❤️💔):** Nhận 75% điểm thưởng\n\n"
            "### 4. 🏷️ PHÂN CẤP 4 DIVISION & ĐỘ KHÓ TĂNG DẦN\n"
            "• **Tier 8 - 7 - 6 : `Div. 4`** *(Nhập môn & cơ bản, 15 phút, file 64KB)*\n"
            "• **Tier 6 - 5 - 4 - 3 : `Div. 3`** *(Trung bình, thuật toán nền tảng, 20-25 phút, 128KB)*\n"
            "• **Low Tier 2 - High Tier 2 : `Div. 2`** *(Nâng cao, cấu trúc dữ liệu khó, đề bài dài, 35-40 phút, 256KB)*\n"
            "• **Low Tier 1 - High Tier 1 : `Div. 1`** *(Chuyên sâu & cực khó, đề bài rất dài & chi tiết toán học, 50-60 phút, 512KB)*\n"
            "📌 *Quy luật: Tier càng cao → Bài toán càng khó, đề bài càng dài và chi tiết!*\n\n"
            "### 5. 🚫 QUY TẮC CHỐNG GIAN LẬN & AI\n"
            "• **Nghiêm cấm tuyệt đối** việc sử dụng AI (ChatGPT, Copilot, DeepSeek...). Mọi vi phạm sẽ bị xử thua và ban nick vĩnh viễn!"
        )

        embed_rules = create_embed(
            title="📖 [1] SỔ TAY LUẬT ĐẤU TRƯỜNG RANKED 1:1",
            description=rules_desc,
            embed_type=EmbedType.INFO,
            color=0xE74C3C,
            footer_text="HyperHub Ranked 1:1 Arena • Đối kháng thời gian thực",
        )

        # Embed 2: Trạm ghép trận trực quan
        station_desc = (
            "### 🧭 TRẠM GHÉP TRẬN THỜI GIAN THỰC (MATCHMAKING STATION)\n"
            "Bấm vào nút **'⚔️ Tìm Trận Đấu (Tham gia 1:1)'** bên dưới để vào hàng chờ tìm đối thủ!\n\n"
            "1. ⚔️ **Tìm Trận Đấu:** Quét đối thủ xung quanh có cùng trình độ (±1 Tier).\n"
            "2. ❌ **Rời Hàng Chờ:** Hủy bỏ hàng chờ ghép trận bất kỳ lúc nào.\n"
            "3. 📊 **Thống Kê Ranked:** Tra cứu bậc Rank, số trận Thắng/Thua và tỷ lệ thắng cá nhân.\n"
            "4. 👁️ **Xem Trực Tiếp (Khán Giả):** Theo dõi ngẫu nhiên 1 trận 1:1 đang diễn ra (Chế độ chỉ xem, không thể nhắn tin/react).\n\n"
            "💡 *Sau khi ghép thành công, Bot sẽ tự động tạo kênh riêng `#⚔️・duel-xxxxxx` và tag 2 đấu thủ vào thi đấu!*"
        )

        embed_station = create_embed(
            title="🎮 [2] TRẠM THAM GIA ĐẤU TRƯỜNG RANKED 1:1",
            description=station_desc,
            embed_type=EmbedType.JUDGE,
            color=0x2ECC71,
            footer_text="Bấm nút bên dưới để tham gia hàng chờ ngay bây giờ!",
        )

        view = RankedArenaView(self.matchmaker)
        await channel.send(embeds=[embed_rules, embed_station], view=view)
        logger.info(
            f"Đã tự động thiết lập giao diện kênh RANKED_CHANNEL_ID: #{channel.name}"
        )

    @app_commands.command(
        name="view",
        description="Chế độ khán giả: Theo dõi trực tiếp trận đấu Ranked / Custom 1:1 theo ID hoặc danh sách",
    )
    @app_commands.describe(
        id="Mã trận đấu muốn xem (Ví dụ: abc123). Để trống để xem danh sách các trận đang đấu và chọn trận."
    )
    async def view(
        self, interaction: discord.Interaction, id: str | None = None
    ) -> None:
        """Lệnh Khán Giả: Xem trận đấu theo ID cụ thể hoặc xem danh sách trận đang diễn ra (chỉ mình user thấy)."""
        await interaction.response.defer(ephemeral=True)
        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.followup.send(
                "❌ Lỗi: Không xác định được thành viên server.", ephemeral=True
            )
            return

        # Case 1: Người dùng nhập ID cụ thể (/view {id})
        if id and id.strip():
            query_code = id.strip().lower()
            target_session = next(
                (
                    s for s in self.matchmaker.active_sessions.values()
                    if s.is_active and s.channel and (s.match_code.lower() == query_code or str(s.channel.id) == query_code)
                ),
                None,
            )

            if not target_session:
                embed_err = discord.Embed(
                    title="❌ KHÔNG TÌM THẤY TRẬN ĐẤU",
                    description=(
                        f"Không tìm thấy trận đấu nào đang diễn ra với mã ID: **`{id.strip()}`**.\n\n"
                        f"💡 **Gợi ý:** Hãy dùng lệnh `/view` (để trống mã ID) để xem danh sách toàn bộ các trận đang diễn ra!"
                    ),
                    color=0xE74C3C,
                )
                await interaction.followup.send(embed=embed_err, ephemeral=True)
                return

            if member.id in (target_session.player1.id, target_session.player2.id):
                await interaction.followup.send(
                    f"⚔️ Bạn đang là đấu thủ chính thức của trận đấu này! Kênh thi đấu của bạn: {target_session.channel.mention}",
                    ephemeral=True,
                )
                return

            try:
                embed_ok = await grant_spectator_permission(target_session, member)
                jump_url = getattr(target_session.channel, "jump_url", None)
                jump_view = SpectatorJumpView(jump_url)
                await interaction.followup.send(embed=embed_ok, view=jump_view, ephemeral=True)
                logger.info(f"Khán giả {member.display_name} ({member.id}) đã vào xem trận #{target_session.match_code} qua /view")
            except Exception as e:
                logger.warning(f"Lỗi cấp quyền khán giả qua /view cho {member.display_name}: {e}")
                await interaction.followup.send(
                    f"❌ Không thể vào phòng xem lúc này: {e}", ephemeral=True
                )
            return

        # Case 2: Người dùng chỉ dùng /view (không kèm id) -> list trận và user chọn để vào (chỉ mình user thấy)
        active_matches = [
            s for s in self.matchmaker.active_sessions.values()
            if s.is_active and s.channel
        ]

        if not active_matches:
            embed_empty = discord.Embed(
                title="ℹ️ HIỆN TẠI KHÔNG CÓ TRẬN ĐẤU NÀO",
                description=(
                    "Hiện tại không có trận đấu Ranked 1:1 hoặc Giao Hữu nào đang diễn ra!\n\n"
                    "👉 Hãy vào kênh Ranked và bấm **'⚔️ Tìm Trận Đấu'** để tự mình tham chiến."
                ),
                color=0x95A5A6,
            )
            await interaction.followup.send(embed=embed_empty, ephemeral=True)
            return

        lines = []
        for idx, s in enumerate(active_matches, 1):
            m_type = "Giao Hữu" if s.is_custom_match else "Ranked 1:1"
            p1_str = f"{s.player1.display_name} ({s.p1_ranked_rank})"
            p2_str = f"{s.player2.display_name} ({s.p2_ranked_rank})"
            p1_hearts = "❤️" * s.p1_lives + "💔" * (2 - s.p1_lives)
            p2_hearts = "❤️" * s.p2_lives + "💔" * (2 - s.p2_lives)
            lines.append(
                f"**{idx}. [{m_type}]** Mã: **`{s.match_code.upper()}`** │ ⚔️ {p1_str} **VS** {p2_str} │ ⏱️ Chặng {s.current_round} ({p1_hearts} vs {p2_hearts})"
            )

        list_desc = (
            f"Hiện đang có **{len(active_matches)}** trận đấu đang diễn ra trong đấu trường.\n\n"
            + "\n".join(lines)
            + "\n\n👉 **Hãy chọn trận đấu từ menu bên dưới để vào theo dõi trực tiếp:**"
        )
        embed_list = discord.Embed(
            title="🏟️ DANH SÁCH TRẬN ĐẤU ĐANG DIỄN RA (CHẾ ĐỘ KHÁN GIẢ)",
            description=list_desc,
            color=0x9B59B6,
        )
        embed_list.set_footer(text="Chọn trận từ menu bên dưới • Chỉ mình bạn nhìn thấy danh sách này")
        select_view = SpectatorMatchSelectView(active_matches, self.matchmaker)
        await interaction.followup.send(embed=embed_list, view=select_view, ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Bắt sự kiện gửi file code và các câu lệnh trong các kênh Duel 1:1 hoặc kênh Ranked."""
        if message.author.bot or not message.guild:
            return

        content = message.content.strip().lower()
        channel_id = message.channel.id

        # Nếu đang ở trong một phòng đấu Ranked 1:1 (Ticket)
        if channel_id in self.matchmaker.active_sessions:
            session = self.matchmaker.active_sessions[channel_id]
            if session.is_active:
                try:
                    if content == ".close":
                        await session.handle_close_command(message)
                    elif content == ".list":
                        await session.handle_list_command(message)
                    elif content == ".test":
                        await session.handle_test_command(message)
                    elif content == ".skip":
                        await session.handle_skip_command(message)
                    elif message.attachments:
                        await session.handle_code_submission(message)
                    else:
                        # Tự động nhận diện xem tin nhắn là code hay tin nhắn trò chuyện thông thường
                        await session.handle_raw_text_submission(message)
                except Exception as e:
                    logger.warning(f"Lỗi khi xử lý tin nhắn trong session {channel_id}: {e}")
            return

        # Lệnh .skip ở ngoài phòng thi đấu: Dành riêng cho Owner ID để skip thời gian chờ hàng chờ và vào thẳng trận mô phỏng
        if content == ".skip" and message.author.id == settings.OWNER_ID:
            ok, embed, session = await self.matchmaker.start_mock_duel_for_owner(
                message.author, message.channel
            )
            await message.channel.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(RankedDuelCog(bot))
