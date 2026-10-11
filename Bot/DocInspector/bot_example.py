"""
DocInspector - Bot Integration Engine & Examples (Discord & Telegram)
Hệ thống đường ống 2 tầng (Two-Channel Ingestion & Classification Pipeline):
- Kênh Nộp Tài Liệu (Ingestion Gateway): ID 1535278288828633138
- Thư Mục Phân Loại (Classification Category): ID 1534147951797080174

Đặc tính kỹ thuật:
1. 100% Deterministic - Không AI/LLM - Tốc độ < 25ms/tài liệu.
2. Phân loại 4 chiều toàn diện:
   - Môn học: Toán, Tin, Lý, Hóa, Sinh, Văn, Anh, Sử, Địa, GDCD, KHTN...
   - Khối lớp: Lớp 12, 11, 10, 9, 8, 7, 6, THCS, THPT, Tiểu học, Đội tuyển/Olympic, Đại học.
   - Thể loại: thường / hsg / chuyên (theo quy tắc: thường < hsg < chuyên, hsg là cấp độ dễ hơn chuyên)
   - 4 trạng thái xác minh:
     * Xác minh (thấy ổn)
     * Chưa rõ ràng (là xác minh nhưng chưa chắc là đúng đề)
     * Không rõ ràng (xem được đề nhưng không biết là đề nào)
     * Không xác minh (không được gì hết / nếu web chặn bot thì báo 'không rõ nguồn gốc')
3. Tự động chuyển tiếp/lưu trữ tài liệu sang kênh đích tương ứng trong Thư mục phân loại 1534147951797080174.
"""

import os
import sys
from typing import Optional, Union

# Ensure safe utf-8 printing on Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Đảm bảo import được DocInspector từ project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from DocInspector import (
    DEFAULT_SUBMISSION_CHANNEL_ID,
    DEFAULT_TARGET_CATEGORY_ID,
    BotInspectorAdapter,
    CategoryDirectoryManager,
    ChannelAutoDetector,
    ChannelComplianceValidator,
    DocumentInspector,
    ExamTrackTier,
    InspectionReport,
    Subject,
    SubmissionRoutingResult,
    VerificationVerdict,
)

# CÁC ID DISCORD CHUẨN CỦA SERVER:
SUBMISSION_CHANNEL_ID: int = int(DEFAULT_SUBMISSION_CHANNEL_ID)  # 1535278288828633138 - Kênh nộp tài liệu
TARGET_CATEGORY_ID: int = int(DEFAULT_TARGET_CATEGORY_ID)        # 1534147951797080174 - Thư mục phân loại


# ==============================================================================
# 1. DISCORD.PY INTEGRATION FULL CODE (KÊNH NỘP 1535278288828633138 ➔ THƯ MỤC 1534147951797080174)
# ==============================================================================
DISCORD_EXAMPLE_CODE = '''
import io
import discord
from discord.ext import commands
from DocInspector import (
    DEFAULT_SUBMISSION_CHANNEL_ID,
    DEFAULT_TARGET_CATEGORY_ID,
    BotInspectorAdapter,
    CategoryDirectoryManager,
)

# 1. CẤU HÌNH ID DISCORD (ĐÃ ĐƯỢC ĐỊNH SẴN THEO YÊU CẦU CỦA BẠN):
SUBMISSION_CHANNEL_ID = 1535278288828633138   # Kênh nộp tài liệu (Ingestion Gateway)
TARGET_CATEGORY_ID = 1534147951797080174      # Thư mục phân loại (Classification Category)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"🤖 Bot DocInspector đã online thành công dưới tên: {bot.user.name}")
    print(f"📌 Kênh Nộp Tài Liệu: ID {SUBMISSION_CHANNEL_ID}")
    print(f"📁 Thư Mục Phân Loại: ID {TARGET_CATEGORY_ID}")

    # TỰ ĐỘNG XEM & QUÉT THƯ MỤC KÊNH TRÊN SERVER DISCORD
    category = bot.get_channel(TARGET_CATEGORY_ID)
    if category and isinstance(category, discord.CategoryChannel):
        print(f"✅ Đã kết nối Thư mục: '{category.name}' (ID: {TARGET_CATEGORY_ID})")
        channel_names = [ch.name for ch in category.channels if isinstance(ch, discord.TextChannel)]
        
        # In cây thư mục phân bổ môn học & thể loại tự động ra console
        tree_text = CategoryDirectoryManager.format_category_tree(
            channel_names=channel_names,
            category_name=category.name,
            category_id=str(TARGET_CATEGORY_ID),
        )
        print("\\n" + tree_text + "\\n")
    else:
        print(f"⚠️ Chưa tìm thấy Thư mục ID: {TARGET_CATEGORY_ID}. Hãy đảm bảo bot có quyền View Channel!")

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # =========================================================================
    # TRƯỜNG HỢP A: NGƯỜI DÙNG NỘP BÀI TẠI KÊNH NỘP (ID 1535278288828633138)
    # ➔ Thẩm định < 25ms, phân loại Môn + Thể loại (thường/hsg/chuyên) + 4 trạng thái
    # ➔ Trả lời kết quả tại kênh nộp và TỰ ĐỘNG CHUYỂN TIẾP sang đúng kênh trong Thư mục 1534147951797080174!
    # =========================================================================
    if message.channel.id == SUBMISSION_CHANNEL_ID:
        category = bot.get_channel(TARGET_CATEGORY_ID)
        category_channel_names = [ch.name for ch in category.channels if isinstance(ch, discord.TextChannel)] if category else None

        # 1. Nộp qua tệp đính kèm (PDF, DOCX, DOC)
        for attachment in message.attachments:
            if attachment.filename.lower().endswith((".pdf", ".docx", ".doc")):
                file_bytes = await attachment.read()

                # Kiểm tra & Tự động định tuyến (Zero AI - < 25ms)
                report, routing = BotInspectorAdapter.inspect_and_route_submission(
                    file_path_or_bytes=file_bytes,
                    category_channels=category_channel_names,
                    category_id=TARGET_CATEGORY_ID,
                    submission_channel_id=SUBMISSION_CHANNEL_ID,
                    file_name=attachment.filename,
                )

                # Phản hồi tại kênh nộp tài liệu 1535278288828633138
                await message.reply(routing.submission_reply_message)

                # Nếu tệp hợp lệ và đọc được -> Tự động chuyển tiếp vào kênh tương ứng trong Thư mục 1534147951797080174
                if not routing.is_blocked_or_unverifiable and category:
                    target_ch = discord.utils.get(category.channels, name=routing.target_channel_name)
                    if target_ch and isinstance(target_ch, discord.TextChannel):
                        # Chuyển tiếp file kèm tin nhắn phân loại
                        file_forward = discord.File(io.BytesIO(file_bytes), filename=attachment.filename)
                        await target_ch.send(
                            content=routing.forwarded_post_message,
                            file=file_forward,
                        )
                return

        # 2. Nộp qua liên kết (Google Drive, Web đề thi, link học tập)
        if any(k in message.content for k in ["drive.google.com", "http://", "https://"]):
            words = message.content.split()
            for word in words:
                if word.startswith(("http://", "https://")):
                    report, routing = BotInspectorAdapter.inspect_and_route_submission(
                        file_path_or_bytes=word,
                        category_channels=category_channel_names,
                        category_id=TARGET_CATEGORY_ID,
                        submission_channel_id=SUBMISSION_CHANNEL_ID,
                    )

                    await message.reply(routing.submission_reply_message)

                    # Chuyển tiếp link sang kênh đích nếu đọc được
                    if not routing.is_blocked_or_unverifiable and category:
                        target_ch = discord.utils.get(category.channels, name=routing.target_channel_name)
                        if target_ch and isinstance(target_ch, discord.TextChannel):
                            await target_ch.send(
                                content=f"{routing.forwarded_post_message}\\n🔗 **Link gốc:** {word}"
                            )
                    return

        await bot.process_commands(message)
        return

    # =========================================================================
    # TRƯỜNG HỢP B: NGƯỜI DÙNG ĐĂNG BÀI TRỰC TIẾP TRONG CÁC KÊNH THUỘC THƯ MỤC 1534147951797080174
    # ➔ Kiểm tra xem môn học và thể loại có đúng với quy định của kênh đó hay không.
    # ➔ Nếu sai kênh -> Cảnh báo nhắc nhở và hướng dẫn nộp vào Kênh Nộp 1535278288828633138!
    # =========================================================================
    channel_category_id = getattr(message.channel, "category_id", None)
    if channel_category_id == TARGET_CATEGORY_ID:
        channel_name = message.channel.name

        for attachment in message.attachments:
            if attachment.filename.lower().endswith((".pdf", ".docx", ".doc")):
                file_bytes = await attachment.read()
                report = BotInspectorAdapter.inspect_in_channel(
                    file_path_or_bytes=file_bytes,
                    channel_name=channel_name,
                    category_id=TARGET_CATEGORY_ID,
                    file_name=attachment.filename,
                )
                compliance = report.channel_compliance
                bot_reply = compliance.bot_reply_formatted if compliance else report.human_summary
                await message.reply(bot_reply)
                return

        if any(k in message.content for k in ["drive.google.com", "http://", "https://"]):
            words = message.content.split()
            for word in words:
                if word.startswith(("http://", "https://")):
                    report = BotInspectorAdapter.inspect_in_channel(
                        file_path_or_bytes=word,
                        channel_name=channel_name,
                        category_id=TARGET_CATEGORY_ID,
                    )
                    compliance = report.channel_compliance
                    reply_msg = compliance.bot_reply_formatted if compliance else report.human_summary
                    await message.reply(reply_msg)
                    return

    await bot.process_commands(message)

# bot.run("YOUR_DISCORD_BOT_TOKEN")
'''


# ==============================================================================
# 2. TELEGRAM BOT INTEGRATION EXAMPLE
# ==============================================================================
TELEGRAM_EXAMPLE_CODE = '''
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from DocInspector import BotInspectorAdapter, DEFAULT_TARGET_CATEGORY_ID, DEFAULT_SUBMISSION_CHANNEL_ID

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if doc and doc.file_name.lower().endswith((".pdf", ".docx", ".doc")):
        tg_file = await doc.get_file()
        file_bytes = await tg_file.download_as_bytearray()

        # Tự động thẩm định và phân loại
        report, routing = BotInspectorAdapter.inspect_and_route_submission(
            file_path_or_bytes=bytes(file_bytes),
            category_id=DEFAULT_TARGET_CATEGORY_ID,
            submission_channel_id=DEFAULT_SUBMISSION_CHANNEL_ID,
            file_name=doc.file_name,
        )

        await update.message.reply_text(routing.submission_reply_message, parse_mode="Markdown")

# app = ApplicationBuilder().token("YOUR_TELEGRAM_BOT_TOKEN").build()
# app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
# app.run_polling()
'''


# ==============================================================================
# 3. CLI SIMULATOR (MÔ PHỎNG ĐƯỜNG ỐNG NỘP TÀI LIỆU VÀ PHÂN LOẠI KÊNH)
# ==============================================================================
def simulate_submission_pipeline(
    file_path_or_url: str,
    submission_channel_id: int = SUBMISSION_CHANNEL_ID,
    category_id: int = TARGET_CATEGORY_ID,
) -> None:
    """
    Mô phỏng đường ống nộp bài tại Kênh Nộp 1535278288828633138
    và tự động phân loại chuyển tiếp sang Thư mục 1534147951797080174.
    """
    sample_channels = [
        "toan-12",
        "toan-11",
        "toan-10",
        "de-toan",
        "chuyen-toan",
        "chuyen-tin",
        "de-tin",
        "ly-12",
        "de-ly",
        "hoa-12",
        "de-hoa",
        "de-sinh",
        "de-van",
        "tieng-anh",
        "chuyen-anh",
        "khoa-hoc-tu-nhien",
        "khoi-12",
        "khoi-thcs",
        "giao-an-5512",
        "tai-lieu-chung",
    ]

    print("=" * 85)
    print(f"📥 [SIMULATOR] NGƯỜI DÙNG GỬI BÀI VÀO KÊNH NỘP TÀI LIỆU: <#{submission_channel_id}>")
    print(f"   • Tệp/Liên kết: '{file_path_or_url}'")
    print(f"   • Thư mục đích phân loại: <#{category_id}> (Kho {len(sample_channels)} kênh chuyên môn)")
    print("-" * 85)

    report, routing = BotInspectorAdapter.inspect_and_route_submission(
        file_path_or_bytes=file_path_or_url,
        category_channels=sample_channels,
        category_id=category_id,
        submission_channel_id=submission_channel_id,
    )

    print("💬 [PHẢN HỒI CỦA BOT TẠI KÊNH NỘP TÀI LIỆU 1535278288828633138]:")
    print(routing.submission_reply_message)
    print("-" * 85)

    if not routing.is_blocked_or_unverifiable:
        print(f"🚀 [TỰ ĐỘNG CHUYỂN TIẾP SANG KÊNH #{routing.target_channel_name} TRONG THƯ MỤC {category_id}]:")
        print(routing.forwarded_post_message)
    else:
        print(f"🛑 [KHÔNG CHUYỂN TIẾP]: Tài liệu bị chặn hoặc không rõ nguồn gốc (Bảo vệ Thư mục {category_id}).")
    print("=" * 85)


def simulate_direct_channel_post(
    file_path: str,
    channel_name: str,
    category_id: int = TARGET_CATEGORY_ID,
) -> None:
    """Mô phỏng trường hợp người dùng đăng trực tiếp vào một kênh trong thư mục."""
    print("=" * 85)
    print(f"📡 [SIMULATOR] Người dùng gửi trực tiếp vào kênh '#{channel_name}' (Thư mục {category_id})")
    print("-" * 85)

    report = BotInspectorAdapter.inspect_in_channel(
        file_path_or_bytes=file_path,
        channel_name=channel_name,
        category_id=category_id,
    )

    compliance = report.channel_compliance
    print("🤖 [BOT KIỂM DUYỆT TẠI KÊNH]:")
    if compliance:
        print(compliance.bot_reply_formatted)
        print()
        print(f"👉 Kết quả: {'✅ ĐÚNG KÊNH' if compliance.is_compliant else '🚨 SAI KÊNH'}")
        if not compliance.is_compliant and compliance.suggested_channels:
            print(f"👉 Gợi ý chuyển sang: {', '.join(['#' + c for c in compliance.suggested_channels])}")
    print("=" * 85)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Mô phỏng Bot Kênh Nộp Tài Liệu (1535278288828633138) & Phân Loại Thư Mục (1534147951797080174)"
    )
    parser.add_argument(
        "--file",
        "-f",
        default="samples/ielts_reading_cambridge_18.pdf",
        help="Đường dẫn file hoặc link URL cần test",
    )
    parser.add_argument(
        "--mode",
        "-m",
        choices=["submit", "direct", "both"],
        default="submit",
        help="Chế độ test: 'submit' (nộp qua kênh 1535278288828633138), 'direct' (đăng trực tiếp vào kênh), 'both' (cả hai)",
    )
    parser.add_argument(
        "--channel",
        "-c",
        default="de-toan",
        help="Tên kênh để test chế độ direct",
    )
    parser.add_argument(
        "--submission-channel-id",
        default=str(SUBMISSION_CHANNEL_ID),
        help="ID Kênh nộp tài liệu",
    )
    parser.add_argument(
        "--category-id",
        default=str(TARGET_CATEGORY_ID),
        help="ID Thư mục phân loại",
    )

    args = parser.parse_args()

    # 1. In cấu trúc Thư mục phân loại
    sample_channels = [
        "toan-12",
        "toan-11",
        "toan-10",
        "de-toan",
        "chuyen-toan",
        "chuyen-tin",
        "de-tin",
        "ly-12",
        "de-ly",
        "hoa-12",
        "de-hoa",
        "de-sinh",
        "de-van",
        "tieng-anh",
        "chuyen-anh",
        "khoa-hoc-tu-nhien",
        "khoi-12",
        "khoi-thcs",
        "giao-an-5512",
        "tai-lieu-chung",
    ]
    print("\n" + CategoryDirectoryManager.format_category_tree(
        channel_names=sample_channels,
        category_name="KHO TÀI LIỆU & ĐỀ THI TRƯỜNG HỌC",
        category_id=args.category_id,
    ) + "\n")

    target = args.file
    is_url = target.startswith(("http://", "https://"))
    if not is_url and not os.path.exists(target):
        alt = os.path.join(os.path.dirname(__file__), target)
        if os.path.exists(alt):
            target = alt

    if args.mode in ("submit", "both"):
        simulate_submission_pipeline(
            target,
            submission_channel_id=int(args.submission_channel_id),
            category_id=int(args.category_id),
        )

    if args.mode in ("direct", "both") and not is_url and os.path.exists(target):
        print("\n")
        simulate_direct_channel_post(
            target,
            channel_name=args.channel,
            category_id=int(args.category_id),
        )
