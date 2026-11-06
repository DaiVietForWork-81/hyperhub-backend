"""Kênh CF_ID: Quy trình xác minh tài khoản Codeforces tự động nhận diện bài nộp ngẫu nhiên siêu dễ (Div 4 / Unrated) với bộ 3 Embeds và code mẫu."""

import asyncio
import random
import time
from typing import Any

import discord
from discord.ext import commands

from config.settings import settings
from database.database import async_session_factory
from database.repositories.cf_repo import CFAccountRepository
from database.repositories.submission_repo import SubmissionRepository
from database.repositories.user_repo import UserRepository
from services.codeforces_api import cf_api
from utils.embeds import EmbedType, create_embed, error_embed, info_embed, success_embed
from utils.logger import get_logger

logger = get_logger("CodeforcesCog")

# Danh sách các bài tập siêu dễ (Div 4 / Unrated / Rating 800) kèm code mẫu sẵn sàng copy
EASY_VERIFY_PROBLEMS: list[dict[str, Any]] = [
    {
        "contest_id": 4,
        "index": "A",
        "name": "Watermelon",
        "url": "https://codeforces.com/contest/4/problem/A",
        "cpp": (
            "#include <iostream>\n"
            "using namespace std;\n"
            "int main() {\n"
            "    int w;\n"
            '    if (cin >> w) cout << (w > 2 && w % 2 == 0 ? "YES" : "NO") << endl;\n'
            "    return 0;\n"
            "}"
        ),
        "py": ("w = int(input())\n" 'print("YES" if w > 2 and w % 2 == 0 else "NO")'),
    },
    {
        "contest_id": 71,
        "index": "A",
        "name": "Way Too Long Words",
        "url": "https://codeforces.com/contest/71/problem/A",
        "cpp": (
            "#include <iostream>\n"
            "#include <string>\n"
            "using namespace std;\n"
            "int main() {\n"
            "    int n; if (cin >> n) {\n"
            "        while(n--) {\n"
            "            string s; cin >> s;\n"
            "            if (s.size() > 10) cout << s.front() << s.size() - 2 << s.back() << endl;\n"
            "            else cout << s << endl;\n"
            "        }\n"
            "    }\n"
            "    return 0;\n"
            "}"
        ),
        "py": (
            "n = int(input())\n"
            "for _ in range(n):\n"
            "    s = input().strip()\n"
            "    print(s[0] + str(len(s) - 2) + s[-1] if len(s) > 10 else s)"
        ),
    },
    {
        "contest_id": 231,
        "index": "A",
        "name": "Team",
        "url": "https://codeforces.com/contest/231/problem/A",
        "cpp": (
            "#include <iostream>\n"
            "using namespace std;\n"
            "int main() {\n"
            "    int n, ans = 0;\n"
            "    if (cin >> n) {\n"
            "        while(n--) { int a, b, c; cin >> a >> b >> c; if (a + b + c >= 2) ans++; }\n"
            "    }\n"
            "    cout << ans << endl;\n"
            "    return 0;\n"
            "}"
        ),
        "py": (
            "n = int(input())\n"
            "ans = sum(1 for _ in range(n) if sum(map(int, input().split())) >= 2)\n"
            "print(ans)"
        ),
    },
    {
        "contest_id": 282,
        "index": "A",
        "name": "Bit++",
        "url": "https://codeforces.com/contest/282/problem/A",
        "cpp": (
            "#include <iostream>\n"
            "#include <string>\n"
            "using namespace std;\n"
            "int main() {\n"
            "    int n, x = 0;\n"
            "    if (cin >> n) {\n"
            '        while(n--) { string s; cin >> s; if (s.find("++") != string::npos) x++; else x--; }\n'
            "    }\n"
            "    cout << x << endl;\n"
            "    return 0;\n"
            "}"
        ),
        "py": (
            "n = int(input())\n"
            "x = 0\n"
            "for _ in range(n):\n"
            '    x += 1 if "++" in input() else -1\n'
            "print(x)"
        ),
    },
    {
        "contest_id": 1742,
        "index": "A",
        "name": "Sum (Div. 4)",
        "url": "https://codeforces.com/contest/1742/problem/A",
        "cpp": (
            "#include <iostream>\n"
            "using namespace std;\n"
            "int main() {\n"
            "    int t; if (cin >> t) {\n"
            "        while(t--) {\n"
            "            int a, b, c; cin >> a >> b >> c;\n"
            '            if (a + b == c || a + c == b || b + c == a) cout << "YES\\n";\n'
            '            else cout << "NO\\n";\n'
            "        }\n"
            "    }\n"
            "    return 0;\n"
            "}"
        ),
        "py": (
            "t = int(input())\n"
            "for _ in range(t):\n"
            "    a, b, c = sorted(map(int, input().split()))\n"
            '    print("YES" if a + b == c else "NO")'
        ),
    },
    {
        "contest_id": 1829,
        "index": "A",
        "name": "Love Story (Div. 4)",
        "url": "https://codeforces.com/contest/1829/problem/A",
        "cpp": (
            "#include <iostream>\n"
            "#include <string>\n"
            "using namespace std;\n"
            "int main() {\n"
            '    int t; string target = "codeforces";\n'
            "    if (cin >> t) {\n"
            "        while(t--) {\n"
            "            string s; cin >> s; int diff = 0;\n"
            "            for(int i=0; i<10; ++i) if (s[i] != target[i]) diff++;\n"
            '            cout << diff << "\\n";\n'
            "        }\n"
            "    }\n"
            "    return 0;\n"
            "}"
        ),
        "py": (
            "t = int(input())\n"
            'target = "codeforces"\n'
            "for _ in range(t):\n"
            "    s = input().strip()\n"
            "    print(sum(1 for a, b in zip(s, target) if a != b))"
        ),
    },
    {
        "contest_id": 1999,
        "index": "A",
        "name": "A+B Again? (Div. 4)",
        "url": "https://codeforces.com/contest/1999/problem/A",
        "cpp": (
            "#include <iostream>\n"
            "using namespace std;\n"
            "int main() {\n"
            "    int t; if (cin >> t) {\n"
            "        while(t--) {\n"
            "            int n; cin >> n;\n"
            '            cout << (n / 10 + n % 10) << "\\n";\n'
            "        }\n"
            "    }\n"
            "    return 0;\n"
            "}"
        ),
        "py": (
            "t = int(input())\n"
            "for _ in range(t):\n"
            "    s = input().strip()\n"
            "    print(int(s[0]) + int(s[1]))"
        ),
    },
]


class CFVerifySessionView(discord.ui.View):
    """Bảng điều khiển phiên xác minh tài khoản Codeforces tự động nhận diện bài nộp với bộ 3 Embeds."""

    def __init__(
        self,
        bot: commands.Bot,
        user: discord.User | discord.Member,
        handle: str,
        problem_info: dict[str, Any],
    ):
        super().__init__(timeout=300)
        self.bot = bot
        self.user = user
        self.handle = handle
        self.problem = problem_info
        self.start_time = time.time()
        self.message: discord.WebhookMessage | discord.Message | None = None
        self._polling_task: asyncio.Task | None = None
        self._is_verified = False

    def render_embeds(self) -> list[discord.Embed]:
        """Tạo bộ 3 Embeds: (1) Hướng dẫn xác minh, (2) Đoạn code mẫu, (3) Trạng thái bot tự động lắng nghe bài nộp."""
        pid = f"{self.problem['contest_id']}{self.problem['index']}"
        pname = self.problem["name"]
        purl = self.problem["url"]

        # Embed 1: Hướng Dẫn Xác Minh (Xanh Dương)
        embed1 = create_embed(
            title="🔐 [1] HƯỚNG DẪN XÁC MINH TÀI KHOẢN CODEFORCES",
            description=(
                f"Chào {self.user.mention}! Để chứng minh bạn là chủ sở hữu của tài khoản **[{self.handle}](https://codeforces.com/profile/{self.handle})**:\n\n"
                f"1. 🔗 **Truy cập bài tập:** **[{pid} - {pname}]({purl})**\n"
                f"2. 📝 **Nộp bài:** Đăng nhập tài khoản **{self.handle}** trên Codeforces và nộp mã nguồn vào bài tập trên.\n"
                f"3. 💡 **Lưu ý:** Bạn có thể nộp **ĐÚNG** hoặc **SAI** tuỳ ý (Bài nộp này **HOÀN TOÀN KHÔNG TÍNH ĐIỂM / KHÔNG ĐỔI RATING**).\n"
                f"4. ⚡ **Tự động kích hoạt:** Bạn không cần ấn nút gì cả, ngay khi bạn submit trên Codeforces, bot sẽ **TỰ ĐỘNG NHẬN DIỆN & LIÊN KẾT NGAY LẬP TỨC**!"
            ),
            embed_type=EmbedType.INFO,
            color=0x1E90FF,
            footer_text="Xác minh quyền sở hữu tài khoản • Codeforces Verification Step 1",
        )

        # Embed 2: Đoạn Code Mẫu Tiện Lợi (Tím)
        embed2 = create_embed(
            title="💻 [2] ĐOẠN CODE MẪU TIỆN LỢI (COPY & SUBMIT)",
            description=(
                f"Bạn có thể sao chép nhanh một trong 2 đoạn code mẫu bên dưới để nộp lên bài **[{pid}]({purl})**:\n\n"
                f"• **Mã nguồn C++ (GCC 17/20):**\n"
                f"```cpp\n{self.problem['cpp']}\n```\n"
                f"• **Mã nguồn Python 3:**\n"
                f"```python\n{self.problem['py']}\n```"
            ),
            embed_type=EmbedType.SUBMISSION,
            color=0x6C5CE7,
            footer_text="Code mẫu tiện lợi • Bạn cũng có thể nộp code bất kỳ",
        )

        # Embed 3: Trạng Thái Tự Động Lắng Nghe Bài Nộp (Vàng Cam)
        embed3 = create_embed(
            title="⏳ [3] BOT ĐANG TỰ ĐỘNG ĐỢI BÀI NỘP TỪ CODEFORCES...",
            description=(
                f"Bot đang tự động quét các bài nộp từ tài khoản **[{self.handle}](https://codeforces.com/profile/{self.handle})** cho bài **{pid}** mỗi 3 giây.\n\n"
                f"• ⏱️ **Thời gian phiên xác minh:** 5 phút\n"
                f"• 🎯 **Thao tác của bạn:** Chỉ cần vào Codeforces nộp bài, bot sẽ **tự động xác nhận 100%** ngay khi nhận được bài!"
            ),
            embed_type=EmbedType.WARNING,
            color=0xFFA502,
            footer_text="Đang tự động lắng nghe bài nộp • Bấm 🔄 Đổi bài hoặc ❌ Hủy",
        )

        return [embed1, embed2, embed3]

    def start_polling(self, message: discord.WebhookMessage | discord.Message) -> None:
        """Bắt đầu tiến trình nền tự động quét bài nộp trên Codeforces."""
        self.message = message
        if not self._polling_task or self._polling_task.done():
            self._polling_task = asyncio.create_task(self._auto_detection_loop())

    async def _auto_detection_loop(self) -> None:
        """Vòng lặp chạy ngầm mỗi 3.5s tự động phát hiện bài nộp xác minh trên Codeforces."""
        target_cid = self.problem["contest_id"]
        target_idx = self.problem["index"].upper()

        for _ in range(85):  # 85 lần * 3.5s ~= 5 phút
            if self._is_verified:
                break
            await asyncio.sleep(3.5)

            try:
                submissions = await cf_api.get_user_submissions(
                    handle=self.handle, count=5
                )
            except Exception:
                continue

            if not submissions:
                continue

            found_sub = None
            for sub in submissions:
                p = sub.get("problem", {})
                sub_cid = p.get("contestId")
                sub_idx = p.get("index", "").upper()
                sub_time = sub.get("creationTimeSeconds", 0)

                if sub_cid == target_cid and sub_idx == target_idx:
                    # Chấp nhận bài nộp được tạo từ thời điểm bắt đầu phiên xác minh (hoặc trước đó tối đa 2 phút)
                    if sub_time >= int(self.start_time) - 120:
                        found_sub = sub
                        break

            if found_sub:
                self._is_verified = True
                sub_id_int = found_sub.get("id")

                # 1. Cập nhật CSDL và LƯU BÀI NỘP VỚI SCORE 0.0 ĐỂ KHÔNG BỊ CỘNG ĐIỂM
                async with async_session_factory() as session:
                    cf_repo = CFAccountRepository(session)
                    user_repo = UserRepository(session)
                    sub_repo = SubmissionRepository(session)

                    await cf_repo.link_account(
                        discord_id=self.user.id,
                        cf_handle=self.handle,
                        verification_token="SUBMISSION_VERIFIED",
                        verified=True,
                    )
                    if sub_id_int:
                        await cf_repo.update_last_submission_id(
                            self.user.id, sub_id_int
                        )

                    await user_repo.get_or_create(self.user.id)

                    # Lưu bản ghi bài nộp xác minh vào CSDL với score = 0.0, is_rated = False
                    if sub_id_int:
                        try:
                            await sub_repo.create_from_cf(
                                discord_id=self.user.id,
                                cf_submission_id=sub_id_int,
                                problem_id=f"{target_cid}{target_idx}",
                                problem_name=self.problem["name"],
                                verdict=found_sub.get("verdict", "OK"),
                                execution_time=found_sub.get("timeConsumedMillis", 0),
                                memory_used=found_sub.get("memoryConsumedBytes", 0)
                                // 1024,
                                score=0.0,
                                is_rated=False,
                            )
                        except Exception:
                            pass

                # 2. Lấy thông tin Codeforces
                user_info = await cf_api.get_user_info(self.handle) or {}
                rating_cf = user_info.get("rating", "Unrated")
                rank_cf = user_info.get("rank", "Tân binh")
                sub_verdict = found_sub.get("verdict", "OK")

                fields = [
                    {
                        "name": "👤 Codeforces Handle",
                        "value": f"**[{self.handle}](https://codeforces.com/profile/{self.handle})**",
                        "inline": True,
                    },
                    {
                        "name": "📈 Điểm CF Rating",
                        "value": f"`⭐ {rating_cf}` *({rank_cf})*",
                        "inline": True,
                    },
                    {
                        "name": "📋 Bài nộp xác minh",
                        "value": f"Submission **[#{sub_id_int}](https://codeforces.com/contest/{target_cid}/submission/{sub_id_int})** (`{sub_verdict}`)",
                        "inline": True,
                    },
                    {
                        "name": "⚡ Trạng thái xác minh",
                        "value": "🟢 **Đã tự động xác minh qua bài nộp thành công 100%!** *(Không tính điểm)*",
                        "inline": False,
                    },
                    {
                        "name": "🎯 Bắt đầu thi đấu & Luyện tập:",
                        "value": (
                            "• **Mode 1 (CF Sync):** Làm bài trên Codeforces, bot tự động đồng bộ mỗi 45s (Nhận **100% điểm**).\n"
                            f"• **Mode 2 (In-Discord):** Nộp bài trực tiếp tại kênh <#{settings.SUBMIT_ID}> (Nhận **90% điểm**).\n"
                            f"• Kiểm tra hồ sơ cá nhân bằng lệnh `/profile`."
                        ),
                        "inline": False,
                    },
                ]

                embed_success = create_embed(
                    title="XÁC MINH & LIÊN KẾT TÀI KHOẢN THÀNH CÔNG! 🎉",
                    description=f"Bot đã tự động nhận diện bài nộp từ Codeforces! Tài khoản **[{self.handle}](https://codeforces.com/profile/{self.handle})** đã được liên kết thành công với {self.user.mention}!",
                    embed_type=EmbedType.SUCCESS,
                    fields=fields,
                    color=0x00B894,
                    footer_text="Xác minh tự động hoàn tất • Đã bảo lưu điểm số an toàn",
                )

                # Vô hiệu hóa nút và cập nhật giao diện
                for child in self.children:
                    child.disabled = True

                if self.message:
                    try:
                        await self.message.edit(embeds=[embed_success], view=None)
                    except Exception as e:
                        logger.warning(f"Không thể edit message xác minh tự động: {e}")
                break

    @discord.ui.button(
        label="Đổi Bài Khác 🔄",
        style=discord.ButtonStyle.secondary,
        custom_id="btn_cf_change_problem",
    )
    async def change_problem_click(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "❌ Bạn không có quyền tương tác với phiên xác minh này!",
                ephemeral=True,
            )
            return

        if self._is_verified:
            await interaction.response.send_message(
                "✅ Tài khoản của bạn đã được xác minh thành công rồi!", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        # Chọn ngẫu nhiên bài khác
        other_problems = [
            p
            for p in EASY_VERIFY_PROBLEMS
            if p["contest_id"] != self.problem["contest_id"]
        ]
        self.problem = (
            random.choice(other_problems)
            if other_problems
            else random.choice(EASY_VERIFY_PROBLEMS)
        )
        self.start_time = time.time()

        embeds = self.render_embeds()
        await interaction.edit_original_response(embeds=embeds, view=self)

    @discord.ui.button(
        label="Hủy Xác Minh ❌",
        style=discord.ButtonStyle.danger,
        custom_id="btn_cf_cancel_verify",
    )
    async def cancel_click(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "❌ Bạn không có quyền hủy phiên xác minh này!", ephemeral=True
            )
            return

        self._is_verified = True  # Dừng polling
        if self._polling_task and not self._polling_task.done():
            self._polling_task.cancel()

        for child in self.children:
            child.disabled = True

        embed = create_embed(
            title="ĐÃ HỦY PHIÊN XÁC MINH",
            description="Phiên xác minh tài khoản Codeforces đã được hủy theo yêu cầu của bạn.",
            embed_type=EmbedType.INFO,
        )
        await interaction.response.edit_message(embeds=[embed], view=None)


class LinkCFModal(discord.ui.Modal, title="Xác minh & Liên kết tài khoản Codeforces"):
    """Popup Modal cho phép thí sinh nhập Handle Codeforces để khởi tạo phiên xác minh tự động nhận diện."""

    handle_input = discord.ui.TextInput(
        label="Tên tài khoản (Handle) Codeforces của bạn",
        placeholder="Ví dụ: tourist, neal, DaiViet_81, v.v.",
        required=True,
        max_length=64,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        clean_handle = self.handle_input.value.strip()

        try:
            # 1. Kiểm tra handle trên Codeforces API
            user_info = await cf_api.get_user_info(clean_handle)
            if not user_info:
                embed = create_embed(
                    title="HANDLE KHÔNG TỒN TẠI",
                    description=f"❌ Không tìm thấy tài khoản Codeforces với handle **`{clean_handle}`**.\nVui lòng kiểm tra lại chính tả.",
                    embed_type=EmbedType.ERROR,
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # 2. Kiểm tra xem handle đã được ai khác liên kết chưa
            async with async_session_factory() as session:
                cf_repo = CFAccountRepository(session)
                existing = await cf_repo.get_by_handle(clean_handle)
                if (
                    existing
                    and existing.verified
                    and existing.discord_id != interaction.user.id
                ):
                    embed = create_embed(
                        title="TÀI KHOẢN ĐÃ ĐƯỢC LIÊN KẾT",
                        description=f"❌ Tài khoản Codeforces **`{clean_handle}`** đã được liên kết bởi thành viên khác (<@{existing.discord_id}>).",
                        embed_type=EmbedType.ERROR,
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return

            # 3. Khởi tạo phiên xác minh qua bài nộp ngẫu nhiên siêu dễ với 3 Embeds và tự động nhận diện
            problem_info = random.choice(EASY_VERIFY_PROBLEMS)
            view = CFVerifySessionView(
                bot=interaction.client,
                user=interaction.user,
                handle=clean_handle,
                problem_info=problem_info,
            )
            embeds = view.render_embeds()
            msg = await interaction.followup.send(
                embeds=embeds, view=view, ephemeral=True, wait=True
            )
            view.start_polling(msg)

        except Exception as e:
            logger.error(f"Lỗi khi khởi tạo phiên xác minh Codeforces: {e}")
            await interaction.followup.send(
                embed=error_embed("LỖI HỆ THỐNG", f"Có lỗi xảy ra: {e}"), ephemeral=True
            )


class CFChannelControlView(discord.ui.View):
    """Bảng điều khiển nút bấm cố định tại kênh CF_ID."""

    def __init__(self):
        super().__init__(timeout=None)  # Persistent view

    @discord.ui.button(
        label="Liên kết tài khoản Codeforces 🔗",
        style=discord.ButtonStyle.success,
        custom_id="btn_cf_link_modal",
    )
    async def link_cf_click(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        modal = LinkCFModal()
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="Kiểm tra trạng thái liên kết ℹ️",
        style=discord.ButtonStyle.primary,
        custom_id="btn_cf_check_status",
    )
    async def check_status_click(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        async with async_session_factory() as session:
            cf_repo = CFAccountRepository(session)
            cf_acc = await cf_repo.get_by_discord_id(interaction.user.id)

        if cf_acc and cf_acc.verified:
            embed = create_embed(
                title="TRẠNG THÁI LIÊN KẾT: ĐÃ XÁC MINH ✅",
                description=(
                    f"Tài khoản Discord của bạn đang liên kết với handle: "
                    f"**[{cf_acc.cf_handle}](https://codeforces.com/profile/{cf_acc.cf_handle})**.\n\n"
                    f"• Bạn có thể nộp bài trên Codeforces (Mode 1) hoặc kênh nộp bài Discord (Mode 2), bot sẽ tự động tính điểm và thăng hạng."
                ),
                embed_type=EmbedType.SUCCESS,
            )
        else:
            embed = create_embed(
                title="CHƯA LIÊN KẾT TÀI KHOẢN",
                description="Bạn chưa liên kết tài khoản Codeforces nào. Bấm nút **`Liên kết tài khoản Codeforces 🔗`** bên dưới để nộp bài siêu dễ và tự động liên kết trong 1 phút!",
                embed_type=EmbedType.INFO,
            )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(
        label="Hủy liên kết tài khoản ❌",
        style=discord.ButtonStyle.danger,
        custom_id="btn_cf_unlink",
    )
    async def unlink_click(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        async with async_session_factory() as session:
            repo = CFAccountRepository(session)
            unlinked = await repo.unlink_account(interaction.user.id)

        if unlinked:
            embed = success_embed(
                "HỦY LIÊN KẾT THÀNH CÔNG",
                f"Đã hủy liên kết tài khoản Codeforces của {interaction.user.mention}.",
            )
        else:
            embed = info_embed(
                "CHƯA LIÊN KẾT TÀI KHOẢN",
                "Bạn chưa liên kết tài khoản Codeforces nào.",
            )
        await interaction.followup.send(embed=embed, ephemeral=True)


class CodeforcesCog(commands.Cog, name="Codeforces"):
    """Quản lý liên kết và xác minh tài khoản Codeforces tự động tại kênh CF_ID."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @classmethod
    def build_cf_channel_embed(cls) -> discord.Embed:
        """Tạo Rich Embed hướng dẫn cố định tại kênh CF_ID."""
        fields = [
            {
                "name": "❓ Tại sao cần liên kết tài khoản Codeforces?",
                "value": (
                    "• Tự động ghi nhận bài làm trên Codeforces (Mode 1) nhận **100% điểm thưởng**.\n"
                    "• Tự động cập nhật điểm **Rating (pts)** và **Thăng hạng Rank Discord**.\n"
                    "• Hiển thị huy hiệu, profile và vinh danh trên Bảng Xếp Hạng Top 50."
                ),
                "inline": False,
            },
            {
                "name": "🔐 Quy trình xác minh bảo mật tự động nhận diện (3 Bước):",
                "value": (
                    "1. Bấm nút **`Liên kết tài khoản Codeforces 🔗`** bên dưới và nhập Handle của bạn.\n"
                    "2. Bot sẽ chọn ngẫu nhiên một bài tập **siêu dễ (Div 4 / Unrated)** và cung cấp **đoạn code mẫu sẵn sàng**.\n"
                    "3. Bạn chỉ cần nộp code lên Codeforces (đúng hoặc sai đều được, **hoàn toàn không tính điểm**), bot sẽ **tự động nhận diện và kích hoạt tài khoản ngay lập tức** mà không cần bấm thêm nút nào!"
                ),
                "inline": False,
            },
        ]

        embed = create_embed(
            title="HƯỚNG DẪN LIÊN KẾT TÀI KHOẢN CODEFORCES 🌐",
            description=(
                "Chào mừng bạn đến với kênh liên kết tài khoản **Codeforces ↔ Discord**!\n"
                "Sử dụng các nút bấm bên dưới để xác minh quyền sở hữu tài khoản an toàn và hoàn toàn tự động."
            ),
            embed_type=EmbedType.INFO,
            fields=fields,
            color=0x3498DB,
            footer_text="Hệ thống xác thực tự động qua bài nộp • Codeforces Auto Verification",
        )
        return embed

    async def auto_setup_cf_channel(self) -> None:
        """Tự động xóa tin nhắn cũ và đăng bảng hướng dẫn liên kết vào kênh CF_ID khi bot khởi động."""
        if not settings.CF_ID or settings.CF_ID <= 0:
            return

        channel = self.bot.get_channel(settings.CF_ID)
        if not channel or not isinstance(channel, discord.TextChannel):
            return

        try:
            # Xóa các tin nhắn cũ trong kênh để làm mới hoàn toàn
            try:
                await channel.purge(limit=50)
            except Exception:
                pass

            from utils.embeds import get_logo_file

            embed = self.build_cf_channel_embed()
            view = CFChannelControlView()
            logo_file = get_logo_file()
            if logo_file:
                await channel.send(embed=embed, file=logo_file, view=view)
            else:
                await channel.send(embed=embed, view=view)
            logger.info(
                "Đã làm mới và đăng bảng hướng dẫn liên kết Codeforces vào kênh CF_ID."
            )
        except Exception as e:
            logger.error(f"Lỗi khi tự động đăng bảng CF_ID: {e}")


async def setup(bot: commands.Bot) -> None:
    cog = CodeforcesCog(bot)
    await bot.add_cog(cog)
