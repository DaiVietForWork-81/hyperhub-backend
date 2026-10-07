"""
cogs/search.py
Lệnh tra cứu đề bài, thuật toán và lời giải mẫu thống nhất (/search {id}) cho cả Freedom và Ranked 1:1.
"""

import discord
from discord import app_commands
from discord.ext import commands

from config.settings import settings
from services.problem_archive import ProblemArchiveService
from utils.embeds import EmbedType, create_embed
from utils.logger import get_logger

logger = get_logger("SearchCog")


class SearchProblemView(discord.ui.View):
    """View cung cấp nút liên kết tới kênh lưu trữ."""

    def __init__(self, jump_url: str | None = None):
        super().__init__(timeout=180)
        if jump_url:
            self.add_item(
                discord.ui.Button(
                    label="Xem Tin Nhắn Lưu Trữ 📦",
                    style=discord.ButtonStyle.link,
                    url=jump_url,
                )
            )


class SearchCog(commands.Cog, name="Search"):
    """Lệnh tra cứu kho đề bài, lời giải và mã nguồn mẫu."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="search",
        description="Tra cứu thông tin chi tiết đề bài, thuật toán (editorial) và code mẫu theo ID",
    )
    @app_commands.describe(
        id="Mã bài tập cần tra cứu (chung cho cả Freedom và Ranked, ví dụ: 1700A, PRB-T8-01, 4A)"
    )
    async def search(self, interaction: discord.Interaction, id: str) -> None:
        try:
            await interaction.response.defer()
        except discord.NotFound:
            return
        except Exception as defer_err:
            logger.warning(f"Lỗi defer /search: {defer_err}")

        query_id = id.strip()
        data = await ProblemArchiveService.search_problem(self.bot, query_id)

        if not data:
            embed_err = create_embed(
                title="🔍 KHÔNG TÌM THẤY BÀI TẬP",
                description=(
                    f"Không tìm thấy dữ liệu đề bài với mã ID: **`{query_id}`**.\n\n"
                    f"• 💡 **Gợi ý tra cứu:**\n"
                    f"  - Đối với bài **Freedom**: Nhập mã Codeforces (Ví dụ: `1700A`, `4A`, `2251B`).\n"
                    f"  - Đối với bài **Ranked 1:1**: Nhập mã bài đấu trường (Ví dụ: `PRB-T8-01`, `PRB-MT2-03`).\n"
                    f"• 📦 Bạn cũng có thể xem toàn bộ kho bài đã lưu trữ tại kênh <#{settings.PROBLEM_ARCHIVE_CHANNEL_ID}>."
                ),
                embed_type=EmbedType.ERROR,
            )
            await interaction.followup.send(embed=embed_err)
            return

        p_id = data["id"]
        name = data["name"]
        mode = data["mode"]
        tier = data["tier"]
        div = data.get("division", "")
        rating = data.get("rating", 1000)
        time_lim = data.get("time_limit", 1.0)
        mem_lim = data.get("memory_limit", 256)
        stmt = data.get("statement", "Chưa có mô tả.")
        inp_fmt = data.get("input_format", "Đọc từ standard input.")
        out_fmt = data.get("output_format", "In ra standard output.")
        constraints = data.get("constraints", "")
        sample_in = data.get("sample_input", "")
        sample_out = data.get("sample_output", "")
        editorial = data.get("editorial", "Xem xét kỹ cấu trúc dữ liệu và trường hợp biên.")
        sol_code = data.get("solution_code", "")
        sol_lang = data.get("solution_lang", "cpp")
        jump_url = data.get("jump_url")

        stmt_cut = stmt[:1000] if len(stmt) > 1000 else stmt
        div_str = f" • {div}" if div else ""

        # Embed 1: Đề bài & Ràng buộc
        embed1 = discord.Embed(
            title=f"📖 [{p_id}] {name}",
            description=(
                f"🎯 **Chế độ:** `{mode}` | **Phân hạng:** `{tier}`{div_str} | **Rating:** `{rating} pts`\n"
                f"⏱️ **Giới hạn:** `{time_lim}s` | **Bộ nhớ:** `{mem_lim} MB`\n\n"
                f"📝 **MÔ TẢ BÀI TOÁN (STATEMENT):**\n{stmt_cut}"
            ),
            color=0x38BDF8 if str(mode).lower() == "freedom" else 0xFBBF24,
        )
        if inp_fmt or out_fmt:
            embed1.add_field(
                name="📥 INPUT & OUTPUT",
                value=f"• **Input:** {inp_fmt[:300]}\n• **Output:** {out_fmt[:300]}",
                inline=False,
            )
        if constraints or sample_in or sample_out:
            embed1.add_field(
                name="📋 RÀNG BUỘC & VÍ DỤ",
                value=(
                    f"• **Ràng buộc:** {constraints[:250]}\n"
                    f"• **Sample In:** `{sample_in[:120] or 'N/A'}`\n"
                    f"• **Sample Out:** `{sample_out[:120] or 'N/A'}`"
                ),
                inline=False,
            )

        # Embed 2: Lời giải & Code mẫu
        edit_cut = editorial[:1000] if len(editorial) > 1000 else editorial
        if len(sol_code) > 1000:
            sol_cut = sol_code[:950] + "\n// ... [Mã nguồn rút gọn để tối ưu hiển thị Discord] ..."
        else:
            sol_cut = sol_code

        embed2 = discord.Embed(
            title=f"💡 PHÂN TÍCH THUẬT TOÁN & CODE MẪU — {p_id}",
            description=(
                f"🧠 **EDITORIAL & PHÂN TÍCH TIẾP CẬN:**\n{edit_cut}\n\n"
                f"💻 **MÃ NGUỒN MẪU CHUẨN AC ({sol_lang.upper()}):**\n"
                f"```{sol_lang}\n{sol_cut}\n```"
            ),
            color=0x10B981,
        )
        embed2.set_footer(
            text=f"Mã tra cứu: {p_id} • Kho lưu trữ đề bài tại kênh ID: {settings.PROBLEM_ARCHIVE_CHANNEL_ID}"
        )

        view = SearchProblemView(jump_url=jump_url) if jump_url else None
        await interaction.followup.send(embeds=[embed1, embed2], view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SearchCog(bot))
