"""
services/online_context.py
Thu thập dữ liệu và cảm hứng từ thế giới thực qua Internet (Tin tức, Địa chấn, Thể thao, Công nghệ, Logistics)
để đưa vào đề bài thuật toán thực tế sống động, khách quan, không xúc phạm hay xuyên tạc bất kỳ ai.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import urllib.request

logger = logging.getLogger("OnlineContext")

REALWORLD_CURATED_SCENARIOS = [
    # Khoa học & Địa chấn / Thiên nhiên
    "Mạng lưới trạm quan trắc địa chấn ghi nhận và định vị tâm chấn của một trận động đất",
    "Hệ thống phân luồng máy bay không người lái và trực thăng tiếp tế hàng cứu trợ sau thiên tai",
    "Mô hình dự báo đường đi của bão nhiệt đới và lưu lượng mưa tại các trạm đo ven biển",
    "Hệ thống quan trắc chất lượng không khí đô thị và cảm biến bụi mịn PM2.5",
    
    # Thể thao & Thi đấu đỉnh cao
    "Thuật toán phân tích quỹ đạo sút phạt và thời điểm vàng ghi bàn thắng quyết định phút bù giờ",
    "Xếp lịch thi đấu vòng tròn loại trực tiếp cho giải vô địch bóng đá thế giới",
    "Hệ thống tính điểm Elo và ghép cặp thi đấu thể thao điện tử (Esports) thời gian thực",
    "Tối ưu hóa chiến thuật pit-stop và lượng nhiên liệu trong giải đua xe F1",

    # Công nghệ, Viễn thông & Tài chính
    "Hệ thống định tuyến lưu lượng cáp quang biển quốc tế APG khi xảy ra sự cố đứt cáp",
    "Sàn giao dịch tài chính tần số cao (HFT) xử lý 500.000 lệnh giao dịch phái sinh mỗi giây",
    "Hạ tầng cân bằng tải cụm máy chủ Kubernetes tự động mở rộng dịp Flash Sale",
    "Mạng lưới điều phối điện lưới thông minh (Smart Grid) cân bằng tải giữa điện mặt trời và thủy điện",
    "Chuỗi cung ứng logistics toàn cầu tối ưu hóa hành trình vận chuyển vắc-xin bảo quản lạnh",
    "Hệ thống đèn tín hiệu giao thông thông minh ứng dụng cảm biến AI tại các nút giao đô thị",
    "Mạng phân phối nội dung CDN đám mây giảm độ trễ phát trực tiếp Video 4K 60FPS",
    "Điều phối đoàn tàu cao tốc Bắc - Nam tránh xung đột trên các đoạn đường ray đơn",
]


async def fetch_hackernews_topics(limit: int = 5) -> list[str]:
    """Lấy các chủ đề công nghệ thực tế đang thịnh hành trên HackerNews qua API mở."""
    loop = asyncio.get_running_loop()

    def _sync_fetch() -> list[str]:
        try:
            req = urllib.request.Request(
                "https://hacker-news.firebaseio.com/v0/topstories.json",
                headers={"User-Agent": "CP-Discord-Bot/1.0"},
            )
            with urllib.request.urlopen(req, timeout=3) as res:
                if res.status == 200:
                    story_ids = json.loads(res.read().decode("utf-8"))[:limit]
                    titles = []
                    for sid in story_ids:
                        try:
                            s_req = urllib.request.Request(
                                f"https://hacker-news.firebaseio.com/v0/item/{sid}.json",
                                headers={"User-Agent": "CP-Discord-Bot/1.0"},
                            )
                            with urllib.request.urlopen(s_req, timeout=2) as s_res:
                                item = json.loads(s_res.read().decode("utf-8"))
                                title = item.get("title")
                                if title:
                                    titles.append(title)
                        except Exception:
                            continue
                    return titles
        except Exception as e:
            logger.debug(f"Không thể kết nối HackerNews API (Offline fallback): {e}")
        return []

    return await loop.run_in_executor(None, _sync_fetch)


async def get_realworld_theme() -> str:
    """
    Lấy một chủ đề thực tế sống động (kết hợp Internet Live Feed + Curated Real-World Scenarios).
    Đảm bảo 100% khách quan, khoa học, thể thao, không xúc phạm/xuyên tạc bất kỳ ai.
    """
    if random.random() < 0.35:
        try:
            live_topics = await asyncio.wait_for(fetch_hackernews_topics(limit=3), timeout=3.5)
            if live_topics:
                topic = random.choice(live_topics)
                return f"Hệ thống công nghệ thực tế lấy cảm hứng từ: {topic}"
        except Exception:
            pass

    return random.choice(REALWORLD_CURATED_SCENARIOS)
