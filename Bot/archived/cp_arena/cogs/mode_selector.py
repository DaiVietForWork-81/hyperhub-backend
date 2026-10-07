"""Kênh CHON_ID: Sổ tay toàn diện về Máy Chủ HyperHub — Thông Tin, 12 Bậc Rank, 2 Chế Độ & Nội Quy."""

import discord
from discord import app_commands
from discord.ext import commands

from config.settings import settings
from utils.embeds import EmbedType, create_embed, get_logo_file
from utils.logger import get_logger

logger = get_logger("ModeSelectorCog")


class ModeInteractiveView(discord.ui.View):
    """Bảng điều khiển tương tác Dropdown Menu và Action Buttons cố định tại kênh CHON_ID."""

    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)  # Persistent View
        self.bot = bot

    @discord.ui.select(
        placeholder="🧭 Tra cứu Sổ tay & Hướng dẫn toàn diện HyperHub Arena...",
        custom_id="select_mode_guide",
        row=0,
        options=[
            discord.SelectOption(
                label="🌟 [1] Tổng Quan Máy Chủ & Quick Start",
                value="overview",
                description="Giới thiệu HyperHub CP Arena & Hướng dẫn nhanh cho tân thủ",
                emoji="🌟",
            ),
            discord.SelectOption(
                label="👑 [2] Hệ Thống 12 Bậc Rank & Elo Rating",
                value="ranks",
                description="Bảng 12 bậc Tier từ T8 đến HT1, công thức Elo và thăng hạng",
                emoji="👑",
            ),
            discord.SelectOption(
                label="🌐 [3] Chế Độ Tự Do (Freedom Mode)",
                value="freedom",
                description="Luyện tập Codeforces, contest, nộp bài nhận điểm thưởng",
                emoji="🌐",
            ),
            discord.SelectOption(
                label="⚔️ [4] Đấu Trường Đối Kháng 1:1 (Ranked)",
                value="ranked",
                description="Ghép đấu 1:1, hệ thống 2 Mạng, đề AI đời sống & Focus Mode",
                emoji="⚔️",
            ),
            discord.SelectOption(
                label="📦 [5] Kho Đề (/search), Khán Giả (/view) & 4K",
                value="features",
                description="Tra cứu đề bài, xem trực tiếp trận đấu & thẻ Profile 4K",
                emoji="📦",
            ),
            discord.SelectOption(
                label="🛡️ [6] Nội Quy & Chống Gian Lận (Anti-Cheat)",
                value="rules",
                description="Quy tắc Fair-play, cấm AI khi đấu 1:1, bảo vệ tân binh",
                emoji="🛡️",
            ),
        ],
    )
    async def on_guide_select(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        val = select.values[0] if select.values else "overview"
        embeds = ModeSelectorCog.build_mode_explanation_embeds()

        target_embed_map = {
            "overview": embeds[0],
            "ranks": embeds[1],
            "freedom": embeds[2],
            "ranked": embeds[3],
            "features": embeds[4],
            "rules": embeds[5],
        }
        chosen = target_embed_map.get(val, embeds[0])
        await interaction.followup.send(embed=chosen, ephemeral=True)

    # === HÀNG 1: CÁC NÚT THAO TÁC THI ĐẤU & TÀI KHOẢN ===

    @discord.ui.button(
        label="🔗 Liên Kết Codeforces",
        style=discord.ButtonStyle.primary,
        custom_id="btn_mode_link_cf",
        row=1,
    )
    async def btn_link_cf(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        cf_cog = self.bot.get_cog("Codeforces")
        if cf_cog:
            from cogs.codeforces import LinkCFModal

            await interaction.response.send_modal(LinkCFModal())
        else:
            await interaction.response.send_message(
                f"🔗 Vui lòng đến kênh <#{settings.CF_ID}> để liên kết tài khoản Codeforces của bạn!",
                ephemeral=True,
            )

    @discord.ui.button(
        label="📝 Nộp Bài Trực Tiếp",
        style=discord.ButtonStyle.success,
        custom_id="btn_mode_submit_open",
        row=1,
    )
    async def btn_submit(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        try:
            from cogs.submission import SubmitModal

            modal = SubmitModal(bot=self.bot, is_rated=True, is_event=False)
            await interaction.response.send_modal(modal)
        except Exception:
            await interaction.response.send_message(
                f"📝 Hãy đến trạm nộp bài <#{settings.SUBMIT_ID}> hoặc dùng lệnh `/submit` để gửi mã nguồn!",
                ephemeral=True,
            )

    @discord.ui.button(
        label="⚔️ Đấu Trường Ranked 1:1",
        style=discord.ButtonStyle.danger,
        custom_id="btn_mode_ranked_duel",
        row=1,
    )
    async def btn_ranked_duel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        is_admin_or_owner = (
            interaction.user.id == settings.OWNER_ID
            or (interaction.guild and interaction.user.id == interaction.guild.owner_id)
            or (isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator)
        )
        ranked_id = settings.RANKED_CHANNEL_ID
        if not is_admin_or_owner:
            await interaction.response.send_message(
                "🔒 **ĐẤU TRƯỜNG RANKED 1:1 (BETA THỬ NGHIỆM)**\n"
                "• Chế độ đấu đối kháng Ranked 1:1 và leo Rank đang tạm khóa để nâng cấp thêm hệ thống.\n"
                "• Hiện tại chỉ dành riêng cho **Owner & Ban Quản Trị** tham gia thử nghiệm nội bộ.\n"
                "• Bạn vẫn có thể tham gia luyện tập tại **Chế Độ Tự Do (Freedom Mode)** và kho tài liệu phong phú nhé!",
                ephemeral=True,
            )
            return

        if ranked_id > 0:
            await interaction.response.send_message(
                f"⚔️ Hãy đến kênh <#{ranked_id}> để tham gia hàng chờ ghép trận Đấu Trường Ranked 1:1 đối kháng thời gian thực!",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                "⚔️ Đấu trường Ranked 1:1 đang sẵn sàng khởi động.",
                ephemeral=True,
            )

    @discord.ui.button(
        label="🏆 Bảng Xếp Hạng",
        style=discord.ButtonStyle.secondary,
        custom_id="btn_mode_view_rank",
        row=1,
    )
    async def btn_rank(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.send_message(
            f"🏆 Xem đầy đủ Bảng Xếp Hạng Song Song Freedom & Ranked tại kênh <#{settings.UP_RANK}> hoặc gõ `/leaderboard`!",
            ephemeral=True,
        )

    # === HÀNG 2: CÁC TIỆN ÍCH NÂNG CAO ===

    @discord.ui.button(
        label="🔍 Tra Cứu Đề (/search)",
        style=discord.ButtonStyle.primary,
        custom_id="btn_mode_search_prob",
        row=2,
    )
    async def btn_search(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        archive_id = settings.PROBLEM_ARCHIVE_CHANNEL_ID
        await interaction.response.send_message(
            f"🔍 **HƯỚNG DẪN TRA CỨU ĐỀ BÀI (`/search`)**\n"
            f"• Mọi bài toán sau khi giải xong (Freedom & Ranked) đều được lưu trữ tự động tại kênh <#{archive_id}>.\n"
            f"• Cú pháp tra cứu: `/search id:<MÃ_BÀI>` (Ví dụ: `/search id:F_1710` hoặc `/search id:R_2026_09`).\n"
            f"• Bot sẽ lập tức hiển thị lại: Đề bài, Giới hạn thời gian/bộ nhớ, Testcase mẫu, Lời giải thuật toán và Code mẫu tối ưu!",
            ephemeral=True,
        )

    @discord.ui.button(
        label="👁️ Chế Độ Khán Giả (/view)",
        style=discord.ButtonStyle.secondary,
        custom_id="btn_mode_spectate",
        row=2,
    )
    async def btn_spectate(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.send_message(
            "👁️ **CHẾ ĐỘ KHÁN GIẢ REAL-TIME (`/view`)**\n"
            "• Gõ `/view` (không tham số) để mở danh sách các trận đấu Ranked 1:1 đang diễn ra và chọn trận muốn xem qua Menu riêng tư.\n"
            "• Gõ `/view id:<MÃ_TRẬN>` để nhận ngay vé khán giả và truy cập trực tiếp phòng đấu.\n"
            "• *Khán giả theo dõi dưới quyền Read-Only để đảm bảo tính công bằng tuyệt đối cho các đấu sĩ!*",
            ephemeral=True,
        )

    @discord.ui.button(
        label="👤 Thẻ Hồ Sơ 4K (/profile)",
        style=discord.ButtonStyle.success,
        custom_id="btn_mode_profile",
        row=2,
    )
    async def btn_profile(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        is_admin_or_owner = (
            interaction.user.id == settings.OWNER_ID
            or (interaction.guild and interaction.user.id == interaction.guild.owner_id)
            or (isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator)
        )
        if not is_admin_or_owner:
            await interaction.response.send_message(
                "🔒 **THẺ HỒ SƠ 4K (/profile) ĐANG TẠM KHÓA (BETA)**\n"
                "• Tính năng hồ sơ cá nhân `/profile` đang được nâng cấp thêm giao diện & dữ liệu mới.\n"
                "• Hiện tính năng chỉ mở riêng cho **Owner & Ban Quản Trị** thử nghiệm. Sẽ sớm mở lại cho toàn bộ thành viên!",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "👤 **THẺ HỒ SƠ THI ĐẤU ESPORTS 4K UHD (`/profile`)**\n"
            "• Gõ `/profile` để xuất ngay thẻ căn cước thi đấu độ phân giải siêu nét 3840×2160.\n"
            "• Hiển thị: Avatar, Tier Rank, Elo Rating, Tỷ lệ Thắng, Chuỗi Streak.\n"
            "• Bảng Lịch Sử Kép độc quyền: 1 bên Lịch sử Ranked 1:1 và 1 bên Lịch sử Freedom Mode!",
            ephemeral=True,
        )


class ModeSelectorCog(commands.Cog, name="Mode Selection"):
    """Quản lý hiển thị sổ tay hướng dẫn toàn diện 6 Rich Embeds tại kênh CHON_ID."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._initialized = False

    @classmethod
    def build_mode_explanation_embeds(cls) -> list[discord.Embed]:
        """Tạo danh sách 6 Rich Embeds cung cấp Sổ Tay & Toàn Bộ Thông Tin Máy Chủ HyperHub."""
        cf_id = settings.CF_ID
        baitap_id = settings.BAITAP_ID
        ranked_id = settings.RANKED_CHANNEL_ID
        rank_id = settings.UP_RANK
        submit_id = settings.SUBMIT_ID
        archive_id = settings.PROBLEM_ARCHIVE_CHANNEL_ID

        # =====================================================================
        # Embed 1: Thông tin máy chủ & Giới thiệu chung & Quick Start
        # =====================================================================
        embed1_desc = (
            "Chào mừng bạn đến với **HyperHub Competitive Programming Arena** — Cộng đồng lập trình thi đấu, "
            "luyện thuật toán chuyên nghiệp và đấu trường đối kháng thời gian thực!\n\n"
            "### 🎯 MỤC TIÊU & ĐỊNH HƯỚNG:\n"
            "• 🚀 **Rèn Luyện Nghiêm Túc:** Chuẩn mực thi đấu Olympic Tin Học, HSG Quốc Gia & Codeforces Div 1/2/3/4.\n"
            "• ⚔️ **Đấu Trường Đối Kháng 1:1:** Độc quyền theo thời gian thực với đề AI ứng dụng thực tiễn & hệ thống 2 Mạng sống.\n"
            "• 📊 **Elo Rating Minh Bạch:** Bảng xếp hạng Elo quốc tế 12 Tier công bằng, cập nhật tự động.\n"
            "• 🛡️ **Anti-Cheat 2.0:** Hệ thống phân tích mã nguồn đa lớp ngăn chặn tuyệt đối AI và gian lận.\n\n"
            "### 🚀 BẮT ĐẦU NHANH (QUICK START):\n"
            f"1️⃣ **Liên kết Codeforces:** Nhấn nút bên dưới hoặc gõ lệnh tại <#{cf_id}>.\n"
            f"2️⃣ **Luyện tập tự do:** Tham gia giải đề tại <#{baitap_id}> hoặc nộp bài tại <#{submit_id}>.\n"
            f"3️⃣ **Đấu trường 1:1:** Ghép trận leo Rank tại <#{ranked_id}> để thăng hạng.\n"
            f"4️⃣ **Theo dõi thành tích:** Xem bảng xếp hạng tại <#{rank_id}> hoặc gõ `/profile`."
        )
        embed1 = create_embed(
            title="🌟 [1] SỔ TAY TOÀN DIỆN MÁY CHỦ — HYPERHUB CP ARENA",
            description=embed1_desc,
            embed_type=EmbedType.INFO,
            color=0x3498DB,
            footer_text="HyperHub CP Arena • Hệ sinh thái Lập trình Thi đấu Chuyên nghiệp",
        )

        # =====================================================================
        # Embed 2: Hệ thống 12 Bậc Rank & Elo Rating
        # =====================================================================
        rank_desc = (
            "Hệ thống Rank của HyperHub chia làm **12 Bậc Tier** dựa trên điểm Elo Rating thực chiến:\n\n"
            "### 👑 BẢNG 12 BẬC RANK CHÍNH THỨC:\n"
            "• `⭐ T8` : **Tier 8** *(0 – 399 pts)* — 🛡️ *Bảo hiểm tân binh: Không bao giờ bị trừ âm điểm*\n"
            "• `⭐ T7` : **Tier 7** *(400 – 699 pts)* — ⚔️ *Mở khóa tính năng ghép trận Đấu Trường Ranked 1:1*\n"
            "• `⭐ T6` : **Tier 6** *(700 – 1199 pts)* — Bước vào đấu trường thuật toán trung cấp\n"
            "• `🔶 T5` : **Tier 5** *(1200 – 1399 pts)* — Trình độ tương đương Codeforces Pupil / Specialist\n"
            "• `🔷 T4` : **Tier 4** *(1400 – 1599 pts)* — Nắm vững Dynamic Programming, Graph căn bản\n"
            "• `💠 T3` : **Tier 3** *(1600 – 1899 pts)* — Expert Level, làm chủ Tree, Segment Tree, Binary Search\n"
            "• `🛡️ LT2` : **Low Tier 2** *(1900 – 2099 pts)* — Tiệm cận Master, thuật toán nâng cao chuyên sâu\n"
            "• `⚜️ MT2` : **Mid Tier 2** *(2100 – 2299 pts)* — Master Level / Vận động viên HSG Quốc Gia\n"
            "• `🔱 HT2` : **High Tier 2** *(2300 – 2399 pts)* — Cao thủ thuật toán, cạnh tranh Top đầu máy chủ\n"
            "• `🏆 LT1` : **Low Tier 1** *(2400 – 2599 pts)* — Grandmaster Level, tốc độ phản xạ thuật toán thượng thừa\n"
            "• `💎 MT1` : **Mid Tier 1** *(2600 – 2999 pts)* — Siêu kỳ thủ, làm chủ mọi cấu trúc dữ liệu đỉnh cao\n"
            "• `👑 HT1` : **High Tier 1** *(≥ 3000 pts)* — Bậc Rank Tối Cao, tượng đài huyền thoại HyperHub\n"
            "• `🥀 RHT1` : **Retired High Tier 1** *(Danh hiệu bảo lưu kỷ lục trọn đời cho cựu danh thủ)*\n\n"
            "### 📈 CƠ CHẾ ELO & THĂNG BẬC:\n"
            "• Thắng trận Ranked 1:1 nhận từ `+50` đến `+100 pts` tùy theo chênh lệch trình độ đối thủ.\n"
            "• Có cơ chế **Điểm Kiên Cường** cộng thêm khi duy trì thế trận giằng co và nộp bài chính xác."
        )
        embed2 = create_embed(
            title="👑 [2] HỆ THỐNG 12 BẬC RANK & THANG ĐIỂM ELO RATING",
            description=rank_desc,
            embed_type=EmbedType.INFO,
            color=0xF1C40F,
            footer_text="Thang điểm chuẩn Elo Quốc tế • HyperHub Rating Engine",
        )

        # =====================================================================
        # Embed 3: Chế độ Tự Do (Freedom Mode)
        # =====================================================================
        modes_desc = (
            "Luyện tập thuật toán tự do không áp lực ghép đối thủ, tích lũy điểm Freedom và nâng cao tư duy:\n\n"
            f"### 🌐 ĐẶC ĐIỂM CHẾ ĐỘ TỰ DO (<#{baitap_id}>):\n"
            "• **Kho Bài Đa Dạng:** Tự động đồng bộ đề thi Codeforces Div 1, Div 2, Div 3, Div 4, Edu Contests.\n"
            "• **Hai Phương Thức Nộp Bài:**\n"
            "  1. 🟢 **Nộp trên Codeforces:** Bot tự động quét API và cộng **100% điểm thưởng** khi có AC.\n"
            f"  2. 🔵 **Nộp qua Sandbox Discord (<#{submit_id}>):** Chạy kiểm thử tự động, nhận **90% điểm thưởng**.\n"
            "• **Hỗ Trợ Đa Ngôn Ngữ:** C++ (GCC 14), Python 3.12, Java 21, Rust, C#, Go.\n"
            "• **Cơ Chế Bảo Vệ API:** Tự động chuyển sang chế độ dự phòng nếu Codeforces API bảo trì."
        )
        embed3 = create_embed(
            title="🌐 [3] CHẾ ĐỘ TỰ DO (FREEDOM MODE) — CODEFORCES & CONTEST",
            description=modes_desc,
            embed_type=EmbedType.JUDGE,
            color=0x2ECC71,
            footer_text="Tự do rèn luyện • Tích lũy điểm Freedom vững chắc",
        )

        # =====================================================================
        # Embed 4: Đấu Trường Đối Kháng 1:1 (Ranked Arena)
        # =====================================================================
        ranked_desc = (
            "Nơi bản lĩnh, tốc độ và thuật toán va chạm trực tiếp trong phòng đấu thời gian thực:\n\n"
            f"### ⚔️ QUY TẮC ĐẤU TRƯỜNG RANKED 1:1 (<#{ranked_id}>):\n"
            "• **Ghép Trận Cân Bằng:** Hệ thống tự động ghép với đối thủ có trình độ tương đương (±1 Tier).\n"
            "• **Hệ Thống 2 Mạng (❤️ ❤️):**\n"
            "  - Mỗi đấu sĩ khởi đầu với 2 Trái Tim sinh mệnh.\n"
            "  - Mỗi lần nộp bài sai (WA, TLE, MLE, CE) bị trừ 1 Mạng (❤️ 💔).\n"
            "  - Mất hết mạng hoặc hết thời gian thi đấu sẽ bị xử thua Knock-out!\n"
            "• **Đề Bài AI Độc Bản:** Đề toán đời sống sinh ngẫu nhiên từ kho dữ liệu hơn 1,000 bài mẫu, kiểm thử đa tầng.\n"
            "• 🚫 **Chế Độ Tập Trung (Focus Mode):**\n"
            "  - Trong thời gian thi đấu, thí sinh **bị tạm ẩn các danh mục Voice Chat, Cộng Đồng và Tài Liệu**.\n"
            "  - Tự động ngắt kết nối voice chat để đảm bảo tập trung tối đa và chống gian lận.\n"
            "  - Toàn bộ kênh sẽ được khôi phục nguyên vẹn ngay sau khi trận đấu kết thúc!"
        )
        embed4 = create_embed(
            title="⚔️ [4] ĐẤU TRƯỜNG ĐỐI KHÁNG 1:1 (RANKED ARENA)",
            description=ranked_desc,
            embed_type=EmbedType.SUBMISSION,
            color=0xE67E22,
            footer_text="Đấu trường thời gian thực • Luật 2 Mạng & Focus Mode",
        )

        # =====================================================================
        # Embed 5: Kho Đề (/search), Chế Độ Khán Giả (/view) & Thẻ 4K
        # =====================================================================
        features_desc = (
            "Các tính năng độc quyền nâng tầm trải nghiệm thi đấu tại HyperHub:\n\n"
            f"### 📦 1. KHO LƯU TRỮ ĐỀ BÀI TOÀN NĂNG (`/search`) — Kênh <#{archive_id}>:\n"
            "• Mọi bài toán sau khi hoàn thành ở Freedom hoặc Ranked đều được cấp một **Mã Bài Duy Nhất (Problem ID)**.\n"
            "• Dùng `/search {id}` để tra lại: Toàn văn đề bài, Testcase mẫu, Phân tích thuật toán & Code mẫu tối ưu.\n\n"
            "### 👁️ 2. CHẾ ĐỘ KHÁN GIẢ TRỰC TIẾP (`/view`):\n"
            "• Cổ vũ và học hỏi từ các trận thư hùng đỉnh cao giữa các cao thủ!\n"
            "• Dùng `/view` để duyệt danh sách các trận đấu đang diễn ra và chọn trận xem qua menu riêng tư.\n"
            "• Dùng `/view id:<mã_trận>` để truy cập thẳng vào khán đài (chế độ chỉ đọc, bảo mật 100%).\n\n"
            "### 👤 3. THẺ HỒ SƠ THI ĐẤU ESPORTS 4K UHD (`/profile`):\n"
            "• Xuất thẻ căn cước thi đấu độ phân giải 4K 3840×2160 cực đẹp chỉ trong <1.5s.\n"
            "• Thiết kế 2 Cột Lịch Sử Song Song: 1 bên **Ranked 1:1 Matches** & 1 bên **Freedom Submissions**."
        )
        embed5 = create_embed(
            title="📦 [5] KHO ĐỀ BÀI (/search), KHÁN GIẢ (/view) & THẺ 4K",
            description=features_desc,
            embed_type=EmbedType.INFO,
            color=0x9B59B6,
            footer_text="Hệ thống Tiện ích Toàn diện • Tra cứu & Theo dõi đỉnh cao",
        )

        # =====================================================================
        # Embed 6: Nội Quy & Hệ Thống Anti-Cheat 2.0
        # =====================================================================
        rules_desc = (
            "Để duy trì môi trường thi đấu lành mạnh, minh bạch và chuyên nghiệp, tất cả thành viên bắt buộc tuân thủ:\n\n"
            "### 🛡️ NỘI QUY THI ĐẤU & FAIR-PLAY:\n"
            "• 🚫 **Nghiêm Cấm Tuyệt Đối AI & Công Cụ Sinh Mã:** Cấm sử dụng ChatGPT, Copilot, DeepSeek, Claude trong các trận thi đấu Ranked 1:1.\n"
            "• 🤖 **Hệ Thống Anti-Cheat 2.0:** Tự động phân tích cây cú pháp trừu tượng (AST), phong cách code và thời gian giải để phát hiện gian lận.\n"
            "• ⚖️ **Khung Xử Phạt Vi Phạm:**\n"
            "  - *Vi phạm lần 1:* Hủy kết quả trận đấu, trừ 300 Elo và cấm thi đấu Ranked 7 ngày.\n"
            "  - *Vi phạm lần 2:* Giáng về Tier 8 (0 pts), tước toàn bộ danh hiệu và cấm thi đấu vĩnh viễn.\n"
            "• 🤝 **Văn Hóa Ứng Xử:** Tôn trọng đối thủ, trọng tài và khán giả. Không spam, toxic hoặc cố tình thoát trận (rage quit).\n"
            "• 🛡️ **Bảo Vệ Tân Binh:** Thành viên Tier 8 được kích hoạt bảo hiểm điểm số — không bị trừ âm điểm để an tâm cọ xát."
        )
        embed6 = create_embed(
            title="📜 [6] NỘI QUY MÁY CHỦ & HỆ THỐNG ANTI-CHEAT 2.0",
            description=rules_desc,
            embed_type=EmbedType.ERROR,
            color=0xE74C3C,
            footer_text="HyperHub CP Arena • Fair-Play & Integrity First",
        )

        return [embed1, embed2, embed3, embed4, embed5, embed6]

    async def auto_setup_chon_channel(self) -> None:
        """Tự động xóa tin nhắn cũ và đăng 6 Embeds Sổ Tay Thông Tin Máy Chủ vào kênh CHON_ID."""
        self._initialized = True
        if not settings.CHON_ID or settings.CHON_ID <= 0:
            logger.debug("CHON_ID chưa được cấu hình hoặc <= 0, bỏ qua thiết lập kênh #mode.")
            return

        channel = self.bot.get_channel(settings.CHON_ID)
        if not channel:
            try:
                channel = await self.bot.fetch_channel(settings.CHON_ID)
            except Exception as e:
                logger.error(f"Không thể tìm thấy kênh CHON_ID {settings.CHON_ID}: {e}")
                return

        if not isinstance(channel, discord.TextChannel):
            logger.warning(f"Kênh CHON_ID {settings.CHON_ID} không phải TextChannel.")
            return

        try:
            try:
                await channel.purge(limit=25)
            except Exception as e:
                logger.debug(f"Bỏ qua lỗi purge kênh CHON_ID: {e}")

            logo_file = get_logo_file()
            embeds = self.build_mode_explanation_embeds()
            view = ModeInteractiveView(self.bot)

            # Chia làm 2 tin nhắn liên tiếp để đảm bảo không vượt quá giới hạn 6,000 ký tự / tin nhắn của Discord:
            # Phần 1: Embed 1 - 3 (Tổng Quan, 12 Rank, Freedom Mode)
            if logo_file:
                await channel.send(embeds=embeds[:3], file=logo_file)
            else:
                await channel.send(embeds=embeds[:3])

            # Phần 2: Embed 4 - 6 (Ranked 1:1, Tiện Ích Độc Quyền, Anti-Cheat 2.0) kèm Bảng Điều Khiển Tương Tác
            await channel.send(embeds=embeds[3:], view=view)

            logger.info(
                f"Đã thiết lập thành công kênh CHON_ID #{channel.name} ({channel.id}) với 6 Embeds Sổ Tay Toàn Diện."
            )
        except Exception as e:
            logger.error(f"Lỗi khi tự động thiết lập kênh CHON_ID: {e}")

    # Bí danh tương thích ngược
    auto_setup_mode_channel = auto_setup_chon_channel

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Tự động kiểm tra và khởi tạo giao diện kênh CHON_ID khi Bot sẵn sàng."""
        if self._initialized:
            return
        self._initialized = True
        logger.info("ModeSelectorCog: Đang đồng bộ giao diện kênh CHON_ID...")
        await self.auto_setup_chon_channel()

    @app_commands.command(
        name="setup_mode",
        description="[Admin] Làm mới 6 Embeds Sổ Tay Toàn Diện tại kênh #mode (CHON_ID)",
    )
    async def setup_mode_cmd(self, interaction: discord.Interaction) -> None:
        """Slash command để Admin làm mới giao diện Sổ Tay Thông Tin Máy Chủ bất cứ lúc nào."""
        is_admin = interaction.user.guild_permissions.administrator
        is_owner = interaction.user.id == settings.OWNER_ID

        if not (is_admin or is_owner):
            await interaction.response.send_message(
                "❌ Bạn không có quyền thực hiện lệnh quản trị này.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        try:
            await self.auto_setup_chon_channel()
            await interaction.followup.send(
                f"✅ Đã làm mới thành công 6 Embeds Sổ Tay Toàn Diện tại kênh <#{settings.CHON_ID}>!",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.followup.send(
                f"❌ Thất bại khi làm mới kênh <#{settings.CHON_ID}>: `{e}`",
                ephemeral=True,
            )


async def setup(bot: commands.Bot) -> None:
    cog = ModeSelectorCog(bot)
    await bot.add_cog(cog)

