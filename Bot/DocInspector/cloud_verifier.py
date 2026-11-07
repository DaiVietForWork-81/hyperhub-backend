"""
DocInspector - Multi-Agent Academic Examiner & Deep Reasoning Verifier (NVIDIA NIM API).

Kiến trúc Agent Thẩm Định Đề Thi 3 Tầng (Multi-Agent Academic Verification Pipeline):
1. Agent 1 — Reader & Curriculum Analyst (nvidia/nemotron-3-ultra-550b-a55b với thinking=True):
   - Áp dụng Quy trình Tư duy Đọc Đề 6 Bước (6-Stage Examiner Reasoning Protocol).
   - Đối chiếu Bản đồ Kiến thức Chương trình GDPT 2018 (Lớp 6 -> Lớp 12) để suy luận chính xác Khối lớp & Môn học ngay cả khi tiêu đề bị khuyết hoặc đặt tên sai.
2. Agent 2 — Trap Auditor (Kiểm toán viên chống 5 bẫy phân loại kinh điển):
   - Bẫy 1: Tên "Trường THPT Chuyên / ĐH KHTN" nhưng đề là "Thi thử TN THPT / Giữa kỳ / Học kỳ / KSCL".
   - Bẫy 2: "Tuyển sinh vào lớp 10" là học sinh Khối 9 (THCS), không phải Khối 10.
   - Bẫy 3: Tổ hợp "Khoa học tự nhiên / Lịch sử & Địa lí" Cấp 2 vs. Môn đơn Cấp 3; GDCD Cấp 2 vs. GDKT&PL Cấp 3.
   - Bẫy 4: Đề Vật lí / Hóa học / Sinh học chứa nhiều phép tính Toán học.
   - Bẫy 5: Đề không ghi lớp ở tiêu đề -> phải suy luận từ chuyên đề câu hỏi (Oxyz/Tích phân/Ester/Vật lí hạt nhân -> Lớp 12; Lượng giác/Dãy số/Dao động cơ/Hydrocarbon -> Lớp 11; Mệnh đề/Vectơ Oxy/Động học/Cấu tạo nguyên tử -> Lớp 10; Vi-ét/Căn bậc hai/Tứ giác nội tiếp -> Lớp 9...).
3. Agent 3 — Independent Arbiter (nvidia/nemotron-3.5-super-vl-120b-a12b / google/gemma-4-31b-it):
   - Khi đề có độ mơ hồ cao (confidence < 0.92 hoặc xung đột giữa các phần), tự động triệu tập Agent độc lập thứ 2 để hội chẩn chéo (Second-Opinion Consensus) trước khi chốt kết quả.
"""

from __future__ import annotations

from collections import OrderedDict, deque
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger("DocInspector.CloudVerifier")

_ENV_LOADED = False
_DISK_CACHE_LOADED = False
_LOCK = threading.Lock()
_DISK_CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "cache" / "cloud_verifier_cache.db"

MAX_REQUESTS_PER_MINUTE = 34
MAX_REQUESTS_PER_DAY = 9500
MIN_INTERVAL_SECONDS = 1.6
BATCH_FLUSH_INTERVAL_SECONDS = 45.0

_MINUTE_WINDOW: deque[float] = deque()
_DAY_WINDOW: deque[float] = deque()
_LAST_REQUEST_TS: float = 0.0

_VERIFICATION_CACHE: OrderedDict[str, Dict[str, Any]] = OrderedDict()
_MAX_CACHE_SIZE = 5000

_PENDING_45S_QUEUE: OrderedDict[str, Dict[str, Any]] = OrderedDict()


def _ensure_disk_cache_loaded() -> None:
    global _DISK_CACHE_LOADED
    if _DISK_CACHE_LOADED:
        return
    _DISK_CACHE_LOADED = True
    try:
        _DISK_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(_DISK_CACHE_PATH, timeout=5.0) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS verifier_cache (
                    fp TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            cur = conn.execute(
                "SELECT fp, payload_json FROM verifier_cache ORDER BY updated_at ASC LIMIT ?",
                (_MAX_CACHE_SIZE,),
            )
            for fp_key, payload_str in cur.fetchall():
                try:
                    data = json.loads(payload_str)
                    if isinstance(data, dict) and data.get("subject"):
                        _VERIFICATION_CACHE[fp_key] = data
                except Exception:
                    continue
    except Exception as e:
        logger.debug("Không thể nạp disk cache CloudVerifier: %s", e)


def _save_to_disk_cache(fp: str, payload: Dict[str, Any]) -> None:
    try:
        _DISK_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(_DISK_CACHE_PATH, timeout=5.0) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO verifier_cache (fp, payload_json, updated_at)
                VALUES (?, ?, ?)
                """,
                (fp, json.dumps(payload, ensure_ascii=False), time.time()),
            )
            conn.commit()
    except Exception as e:
        logger.debug("Không thể lưu disk cache CloudVerifier: %s", e)


def _get_nvidia_credentials() -> tuple[str, str, str, str]:
    global _ENV_LOADED
    if not _ENV_LOADED:
        _ENV_LOADED = True
        try:
            from dotenv import load_dotenv

            bot_env = Path(__file__).resolve().parent.parent / ".env"
            if bot_env.exists():
                load_dotenv(bot_env)
        except Exception:
            pass

    api_key = os.environ.get("NVIDIA_API_KEY", "").strip()
    base_url = (
        os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
        .strip()
        .rstrip("/")
    )
    primary_model = os.environ.get(
        "NVIDIA_PRIMARY_MODEL", "nvidia/nemotron-3-ultra-550b-a55b"
    ).strip()
    fallback_model = os.environ.get(
        "NVIDIA_FALLBACK_MODEL", "nvidia/nemotron-3.5-super-vl-120b-a12b"
    ).strip()

    if not api_key:
        try:
            from config.settings import settings

            api_key = getattr(settings, "NVIDIA_API_KEY", "") or ""
            base_url = (getattr(settings, "NVIDIA_BASE_URL", base_url) or base_url).rstrip("/")
            primary_model = (
                getattr(settings, "NVIDIA_PRIMARY_MODEL", primary_model) or primary_model
            )
            fallback_model = (
                getattr(settings, "NVIDIA_FALLBACK_MODEL", fallback_model) or fallback_model
            )
        except Exception:
            pass

    return api_key, base_url, primary_model, fallback_model


def _make_fingerprint(file_name: str, raw_text: str) -> str:
    norm_name = re.sub(r"\s+", " ", (file_name or "").strip().lower())
    norm_head = re.sub(r"\s+", " ", (raw_text or "")[:1800].strip().lower())
    norm_tail = re.sub(r"\s+", " ", (raw_text or "")[-400:].strip().lower())
    digest = hashlib.sha256(f"{norm_name}||{norm_head}||{norm_tail}".encode("utf-8")).hexdigest()
    return digest[:32]


def _acquire_rate_limit_slot(wait_if_needed: bool = True, max_wait_sec: float = 45.0) -> bool:
    global _LAST_REQUEST_TS
    deadline = time.time() + max_wait_sec

    while True:
        now = time.time()
        with _LOCK:
            while _MINUTE_WINDOW and now - _MINUTE_WINDOW[0] >= 60.0:
                _MINUTE_WINDOW.popleft()
            while _DAY_WINDOW and now - _DAY_WINDOW[0] >= 86400.0:
                _DAY_WINDOW.popleft()

            if len(_DAY_WINDOW) >= MAX_REQUESTS_PER_DAY:
                logger.warning("Đã chạm ngưỡng bảo vệ 9.500 requests/ngày của CloudVerifier.")
                return False

            since_last = now - _LAST_REQUEST_TS
            need_minute_wait = (
                (60.0 - (now - _MINUTE_WINDOW[0]) + 0.1)
                if len(_MINUTE_WINDOW) >= MAX_REQUESTS_PER_MINUTE
                else 0.0
            )
            need_pace_wait = (
                (MIN_INTERVAL_SECONDS - since_last) if since_last < MIN_INTERVAL_SECONDS else 0.0
            )
            wait_sec = max(need_minute_wait, need_pace_wait)

            if wait_sec <= 0.0:
                _LAST_REQUEST_TS = now
                _MINUTE_WINDOW.append(now)
                _DAY_WINDOW.append(now)
                return True

        if not wait_if_needed or (time.time() + wait_sec > deadline):
            return False
        time.sleep(min(wait_sec, 2.0))


# ==============================================================================
# HUẤN LUYỆN TƯ DUY ĐỌC ĐỀ 6 BƯỚC & BẢN ĐỒ KIẾN THỨC CHƯƠNG TRÌNH GDPT 2018
# ==============================================================================
SYSTEM_PROMPT_VI = """Bạn là Hội đồng Thẩm định Học liệu & Phân loại Đề thi Quốc gia theo Chương trình Giáo dục Phổ thông 2018 (GDPT 2018) của Việt Nam.
Khi đọc một đề thi hoặc tài liệu học tập, bạn PHẢI vận hành QUY TRÌNH TƯ DUY ĐỌC ĐỀ 6 BƯỚC dưới đây trước khi kết luận:

=== BƯỚC 1: TÁCH BIỆT "ĐƠN VỊ RA ĐỀ" VÀ "TÍNH CHẤT KỲ THI" (CHỐNG BẪY TRƯỜNG CHUYÊN) ===
- Đầu trang đề thi thường có Quốc hiệu và Tên đơn vị (Sở GD&ĐT / Phòng GD&ĐT / Trường THPT / Trường THCS / Trường ĐH).
- CẢNH BÁO BẪY SỐ 1: Nhiều trường có tên là "Trường THPT Chuyên ..." (ví dụ: THPT Chuyên Hà Nội - Amsterdam, THPT Chuyên Vĩnh Phúc, THPT Chuyên KHTN, THPT Chuyên Lam Sơn) nhưng họ ra đề "Thi thử Tốt nghiệp THPT", "Khảo sát chất lượng (KSCL)", "Kiểm tra Giữa kỳ / Học kỳ".
  -> Những đề này thuộc hệ Chuẩn phổ thông: exam_track PHẢI LÀ "THUONG" (Tuyệt đối KHÔNG được gán là "CHUYEN" hay "HSG" chỉ vì tên trường có chữ Chuyên!).
  -> Tương tự, "Trường THPT Chuyên Khoa học Tự nhiên" là TÊN TRƯỜNG, không phải môn Khoa học tự nhiên!
- Chỉ gán exam_track = "HSG" khi tên kỳ thi ghi rõ: "Kỳ thi chọn Học sinh giỏi", "Đề thi HSG", "Chọn đội tuyển Olympic", "Olympic truyền thống".
- Chỉ gán exam_track = "CHUYEN" khi tên kỳ thi ghi rõ: "Đề thi tuyển sinh vào lớp 10 THPT Chuyên (Môn Chuyên)", "Đề thi khảo sát đội tuyển Chuyên", "Đề thi Chuyên sâu".
- Chỉ gán exam_track = "QUOC_TE" khi là đề thi quốc tế: IMO, IPhO, IChO, IBO, IOI, SAT, AP, A-Level, IB, Kangaroo (IKMC), AMC, SASMO, TIMO, HKIMO.

=== BƯỚC 2: PHÂN ĐỊNH "TUYỂN SINH VÀO LỚP 10" VS. "HỌC SINH LỚP 10" (CHỐNG BẪY CHUYỂN CẤP) ===
- CẢNH BÁO BẪY SỐ 2: Đề ghi "Kỳ thi tuyển sinh vào lớp 10 THPT", "Thi thử vào lớp 10", "Đề ôn thi vào 10" là kỳ thi chuyển cấp dành cho HỌC SINH LỚP 9 (Cấp 2 - THCS).
  -> BẮT BUỘC gán: grade_level = "Khối 9" (TUYỆT ĐỐI KHÔNG gán "Khối 10").
  -> Nếu là đề vào 10 đại trà/công lập -> exam_track = "THUONG", detailed_exam_track = "Đề thi tuyển sinh vào lớp 10".
  -> Nếu là đề vào 10 hệ Chuyên / Môn Chuyên -> exam_track = "CHUYEN", detailed_exam_track = "Đề thi tuyển sinh vào lớp 10 Chuyên".
- Chỉ gán grade_level = "Khối 10" khi đề dành cho học sinh ĐANG HỌC LỚP 10 THPT (kiểm tra Giữa kỳ/Học kỳ Lớp 10, HSG Lớp 10).

=== BƯỚC 3: XÁC ĐỊNH MÔN HỌC TỪ BẢN CHẤT CÂU HỎI (CHỐNG BẪY CÔNG THỨC TOÁN & MÔN TÍCH HỢP) ===
- CẢNH BÁO BẪY SỐ 3: Đề Vật lí, Hóa học, Sinh học, Địa lí, Kinh tế có rất nhiều số liệu, phương trình, đạo hàm, xác suất, đồ thị. Không bao giờ thấy ký hiệu toán học mà vội kết luận môn Toán! Hãy đọc ĐỐI TƯỢNG HỎI trong câu:
  * Hỏi về dao động, sóng, dòng điện, từ trường, nhiệt học, khí lí tưởng, hạt nhân, quang học -> "PHYSICS" (Vật lí).
  * Hỏi về nguyên tử, bảng tuần hoàn, liên kết hóa học, pH, tốc độ phản ứng, ester, carbohydrate, amine, polymer, kim loại, số mol -> "CHEMISTRY" (Hóa học).
  * Hỏi về tế bào, quang hợp, hô hấp, ADN/ARN, phiên mã, dịch mã, đột biến, quy luật di truyền Mendel/Morgan, quần thể, hệ sinh thái -> "BIOLOGY" (Sinh học).
  * Hỏi về thuật toán, độ phức tạp, C++/Python/Pascal, SQL, HTML/CSS, mạng máy tính, cơ sở dữ liệu -> "INFORMATICS" (Tin học).
- CẢNH BÁO MÔN TÍCH HỢP CẤP 2 (LỚP 6, 7, 8, 9) THEO GDPT 2018:
  * Ở THCS (Lớp 6–9), Lý - Hóa - Sinh tích hợp thành môn "Khoa học tự nhiên" -> nếu đề ghi "Môn: Khoa học tự nhiên (KHTN)" hoặc kiểm tra định kỳ Cấp 2 tích hợp -> gán "NATURAL_SCIENCE".
  * Ở THCS (Lớp 6–9), Sử - Địa tích hợp thành "Lịch sử và Địa lí" -> gán "HISTORY_GEOGRAPHY".
  * Ở THCS (Lớp 6–9), Giáo dục công dân -> gán "CIVIC_EDUCATION".
  * Ở THPT (Lớp 10–12), Giáo dục kinh tế và pháp luật -> gán "ECONOMIC_LEGAL_EDU".

=== BƯỚC 4: SUY LUẬN KHỐI LỚP TỪ BẢN ĐỒ KIẾN THỨC CHƯƠNG TRÌNH (KHI ĐỀ KHÔNG GHI RÕ LỚP) ===
Nếu tên tệp và tiêu đề không ghi rõ khối lớp (hoặc chỉ ghi "Đề thi thử THPT", "Chuyên đề ôn tập"), hãy đọc nội dung câu hỏi và đối chiếu Bản đồ Kiến thức GDPT 2018:
1. MÔN TOÁN:
   - Khối 12: Khảo sát hàm số & tiệm cận đứng/xiên; Nguyên hàm - Tích phân; Vectơ & Tọa độ không gian Oxyz (mặt phẳng, mặt cầu, đường thẳng); Xác suất có điều kiện & Công thức Bayes; Đề thi thử Tốt nghiệp THPT.
   - Khối 11: Phương trình lượng giác; Dãy số - Cấp số cộng - Cấp số nhân; Giới hạn & Hàm số liên tục; Hàm số mũ & Lôgarit; Đạo hàm cơ bản; Quan hệ vuông góc trong không gian (góc nhị diện, khoảng cách).
   - Khối 10: Mệnh đề - Tập hợp; Hệ bất phương trình bậc nhất hai ẩn; Hệ thức lượng trong tam giác; Vectơ trong mặt phẳng Oxy; Đường tròn & Ba đường conic (Elip, Hypebol, Parabol).
   - Khối 9: Căn bậc hai/ba; Hệ phương trình bậc nhất hai ẩn; Phương trình bậc hai & Định lý Vi-ét; Góc với đường tròn & Tứ giác nội tiếp; Hình trụ - nón - cầu.
   - Khối 8: Đa thức nhiều biến; 7 hằng đẳng thức đáng nhớ; Phân thức đại số; Định lý Thalès; Tam giác đồng dạng; Hình chóp đều.
   - Khối 7: Số hữu tỉ - Số thực; Tỉ lệ thức - Dãy tỉ số bằng nhau; Hai tam giác bằng nhau; Các đường đồng quy trong tam giác.
   - Khối 6: Tập hợp số tự nhiên; Số nguyên; ƯCLN - BCNN; Phân số cơ bản; Hình có trục/tâm đối xứng.
2. MÔN VẬT LÍ:
   - Khối 12: Vật lí nhiệt (nội năng, nhiệt nóng chảy/hóa hơi); Khí lí tưởng (pV=nRT); Từ trường & Cảm ứng điện từ; Vật lí hạt nhân (độ hụt khối, phóng xạ).
   - Khối 11: Dao động điều hòa (con lắc lò xo/đơn); Sóng cơ & Giao thoa sóng; Điện trường (định luật Coulomb, tụ điện); Dòng điện không đổi (suất điện động, định luật Ohm).
   - Khối 10: Động học (chuyển động biến đổi đều, ném xiên); 3 định luật Newton; Công - Năng lượng - Động lượng; Chuyển động tròn đều.
3. MÔN HÓA HỌC:
   - Khối 12: Ester - Lipid; Carbohydrate (Glucose, Saccharose, Tinh bột); Amine - Amino acid - Peptide - Protein; Polymer; Pin điện & Điện phân; Đại cương Kim loại & Phức chất.
   - Khối 11: Cân bằng hóa học & pH; Nitrogen - Sulfur; Đại cương Hóa hữu cơ (phổ IR); Hydrocarbon (Alkane, Alkene, Alkyne, Arene); Alcohol - Phenol - Aldehyde - Carboxylic acid.
   - Khối 10: Cấu tạo nguyên tử (Orbital, cấu hình e); Bảng tuần hoàn; Liên kết hóa học; Phản ứng oxi hóa - khử; Enthalpy tạo thành; Tốc độ phản ứng; Nhóm Halogen.
4. MÔN SINH HỌC:
   - Khối 12: Cơ chế di truyền & biến dị (ADN, phiên mã, dịch mã, điều hòa hoạt động gen Operon Lac); Quy luật di truyền; Di truyền quần thể & Di truyền người; Tiến hóa & Sinh thái học.
   - Khối 11: Trao đổi chất & Chuyển hóa năng lượng ở thực vật/động vật (quang hợp, hô hấp, tuần hoàn, bài tiết); Cảm ứng; Sinh trưởng & Sinh sản.
   - Khối 10: Thành phần hóa học của tế bào; Cấu trúc tế bào nhân sơ/nhân thực; Chu kỳ tế bào & Nguyên phân - Giảm phân; Vi sinh vật & Virus.

=== BƯỚC 5: KIỂM TRA CẤU TRÚC ĐỀ CHUẨN BỘ GD&ĐT 2025 & PHỤ LỤC ===
- Kiểm tra xem đề có cấu trúc 3 phần mới (Phần I: Trắc nghiệm nhiều phương án lựa chọn; Phần II: Trắc nghiệm đúng sai; Phần III: Trắc nghiệm trả lời ngắn) hay không -> "moet_2025_compliant": true/false.
- Kiểm tra cuối văn bản có Bảng đáp án ("has_answer_keys": true/false) và Hướng dẫn giải chi tiết ("has_detailed_solutions": true/false) hay không.

=== BƯỚC 6: CÁC VÍ DỤ MẪU CHUẨN (FEW-SHOT GOLDEN EXEMPLARS) ===
- Ví dụ 1: "TRƯỜNG ĐH KHTN - TRƯỜNG THPT CHUYÊN KHTN | ĐỀ THI THỬ TỐT NGHIỆP THPT NĂM 2025 - MÔN: TOÁN"
  -> {"is_valid_exam": true, "subject": "MATHEMATICS", "grade_level": "Khối 12", "exam_track": "THUONG", "detailed_exam_track": "Đề thi thử tốt nghiệp THPT", "school_or_department": "Trường THPT Chuyên KHTN", "academic_year": "2024-2025", "confidence": 0.99}
- Ví dụ 2: "SỞ GD&ĐT HÀ NỘI | KỲ THI TUYỂN SINH VÀO LỚP 10 THPT NĂM HỌC 2025-2026 | MÔN THI: TIẾNG ANH (Đại trà)"
  -> {"is_valid_exam": true, "subject": "ENGLISH", "grade_level": "Khối 9", "exam_track": "THUONG", "detailed_exam_track": "Đề thi tuyển sinh vào lớp 10", "school_or_department": "Sở GD&ĐT Hà Nội", "academic_year": "2025-2026", "confidence": 0.99}
- Ví dụ 3: "SỞ GD&ĐT NGHỆ AN | KỲ THI TUYỂN SINH VÀO LỚP 10 THPT CHUYÊN PHAN BỘI CHÂU | MÔN THI: HÓA HỌC (Đề chuyên)"
  -> {"is_valid_exam": true, "subject": "CHEMISTRY", "grade_level": "Khối 9", "exam_track": "CHUYEN", "detailed_exam_track": "Đề thi tuyển sinh vào lớp 10 Chuyên", "school_or_department": "THPT Chuyên Phan Bội Châu - Nghệ An", "academic_year": null, "confidence": 0.99}
- Ví dụ 4: "PHÒNG GD&ĐT QUẬN CẦU GIẤY | ĐỀ KIỂM TRA HỌC KỲ I LỚP 8 | MÔN: KHOA HỌC TỰ NHIÊN"
  -> {"is_valid_exam": true, "subject": "NATURAL_SCIENCE", "grade_level": "Khối 8", "exam_track": "THUONG", "detailed_exam_track": "Đề thi Học kỳ 1", "school_or_department": "Phòng GD&ĐT Quận Cầu Giấy", "academic_year": null, "confidence": 0.99}

Định dạng JSON trả về cho 1 đề (CHỈ TRẢ VỀ KHỐI JSON HỢP LỆ):
{
  "is_valid_exam": true,
  "subject": "MATHEMATICS | PHYSICS | CHEMISTRY | BIOLOGY | INFORMATICS | LITERATURE | ENGLISH | HISTORY | GEOGRAPHY | NATURAL_SCIENCE | HISTORY_GEOGRAPHY | CIVIC_EDUCATION | ECONOMIC_LEGAL_EDU | TECHNOLOGY | DEFENSE_SECURITY_EDU | GENERAL",
  "grade_level": "Khối 6 | Khối 7 | Khối 8 | Khối 9 | Khối 10 | Khối 11 | Khối 12 | Đại học / Cao đẳng | Không xác định",
  "exam_track": "THUONG | CHUYEN | HSG | QUOC_TE | CHUNG",
  "detailed_exam_track": "Đề thi thử tốt nghiệp THPT | Đề thi chính thức tốt nghiệp THPT | Đề thi Học kỳ 1 | Đề thi Học kỳ 2 | Đề thi Giữa học kỳ 1 | Đề thi Giữa học kỳ 2 | Đề thi khảo sát chất lượng | Đề thi tuyển sinh vào lớp 10 | Đề thi tuyển sinh vào lớp 10 Chuyên | Đề thi Học sinh giỏi | Đề cương / Tài liệu ôn tập",
  "school_or_department": "Tên Trường hoặc Sở/Phòng GD&ĐT nếu có trong đầu đề, hoặc null",
  "academic_year": "YYYY-YYYY nếu có, hoặc null",
  "moet_2025_compliant": true,
  "has_answer_keys": true,
  "has_detailed_solutions": false,
  "curriculum_topic_detected": "Chuyên đề kiến thức trọng tâm nhận diện được (ví dụ: Hàm số & Tọa độ Oxyz Toán 12)",
  "confidence": 0.99
}"""

ARBITER_PROMPT_VI = """Bạn là Trọng tài Kiểm định Độc lập Cấp cao (Final Arbiter Agent).
Một đề thi vừa được phân tích sơ bộ nhưng có dấu hiệu dễ gây nhầm lẫn.
Hãy đọc lại văn bản đề, kết quả phân tích của Agent 1, và kiểm tra thật kỹ 5 bẫy:
1. Trường THPT Chuyên ra đề Thi thử / Học kỳ / KSCL -> exam_track PHẢI LÀ "THUONG".
2. Đề thi Tuyển sinh vào lớp 10 -> grade_level PHẢI LÀ "Khối 9".
3. Đề Cấp 2 (Lớp 6-9) môn KHTN -> "NATURAL_SCIENCE"; Lịch sử & Địa lí -> "HISTORY_GEOGRAPHY".
4. Nếu đề không ghi rõ lớp ở tiêu đề -> suy luận Khối lớp từ chuyên đề câu hỏi theo chương trình GDPT 2018.
5. Trả về DUY NHẤT 1 đối tượng JSON chuẩn xác nhất."""


def _build_model_chain(primary_model: str, fallback_model: str) -> List[str]:
    chain: List[str] = []
    for m in (
        primary_model,
        fallback_model,
        "nvidia/nemotron-3-ultra-550b-a55b",
        "nvidia/nemotron-3.5-super-vl-120b-a12b",
        "google/gemma-4-31b-it",
        "z-ai/glm-5.3-flash",
        "nvidia/nemotron-3.5-bolt-e4b",
    ):
        if m and m not in chain:
            chain.append(m)
    return chain


def _build_payload_for_model(
    model_name: str, system_prompt: str, user_prompt: str, base_tokens: int = 400
) -> Dict[str, Any]:
    is_deep_reasoning = any(
        k in model_name for k in ("ultra-550b", "glm-5.3", "kimi", "deepseek")
    )
    payload: Dict[str, Any] = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": 16384 if is_deep_reasoning else max(2048, base_tokens),
        "temperature": 0.0,
    }
    if is_deep_reasoning:
        payload["chat_template_kwargs"] = {
            "thinking": True,
            "enable_thinking": True,
        }
    else:
        payload["chat_template_kwargs"] = {
            "thinking": False,
            "enable_thinking": False,
        }
    return payload


def _deterministic_post_audit(
    file_name: str, raw_text: str, parsed: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Agent 2 (Deterministic Trap Auditor):
    Kiểm toán hậu kiểm bằng luật cứng sau khi Agent 1 (550B) trả kết quả,
    đảm bảo không bao giờ lọt bẫy Tuyển sinh vào 10 hay Trường Chuyên thi thử.
    """
    result = dict(parsed)
    head_text = f"{file_name}\n{(raw_text or '')[:1500]}".lower()

    # Kiểm toán Bẫy 2: Tuyển sinh vào lớp 10 LUÔN LUÔN là Khối 9
    if re.search(
        r"(tuyển\s*sinh\s*(?:vào\s*)?(?:lớp\s*)?10|thi\s*vào\s*(?:lớp\s*)?10|ôn\s*thi\s*vào\s*(?:lớp\s*)?10|chuyên\s*(?:anh|toán|văn|lí|lý|hóa|sinh|tin|sử|địa)\s*(?:hà\s*nội\s*amsterdam|amsterdam|sư\s*phạm|khtn|ngoại\s*ngữ))",
        head_text,
    ) and not re.search(r"(lớp\s*11|lớp\s*12|tốt\s*nghiệp\s*thpt)", head_text):
        result["grade_level"] = "Khối 9"
        if re.search(r"(chuyên|môn\s*chuyên|hệ\s*chuyên|amsterdam)", head_text):
            result["exam_track"] = "CHUYEN"
            result["detailed_exam_track"] = "Đề thi tuyển sinh vào lớp 10 Chuyên"
        else:
            result["exam_track"] = "THUONG"
            result["detailed_exam_track"] = "Đề thi tuyển sinh vào lớp 10"

    # Kiểm toán tài liệu chuyên đề / cẩm nang / sách tham khảo từ tên file
    fn_lower = (file_name or "").lower()
    if any(
        k in fn_lower
        for k in (
            "vách-ngăn-và-bó",
            "vách ngăn và bó",
            "kĩ-thuật-kế-hợp",
            "bất đẳng thức",
            "phương trình hàm",
            "tổ hợp xác suất",
        )
    ):
        result["subject"] = "MATHEMATICS"
        if not result.get("detailed_exam_track") or "thi" in str(result.get("detailed_exam_track", "")).lower():
            result["detailed_exam_track"] = "Đề cương / Tài liệu ôn tập"
            result["exam_track"] = "THUONG"
    elif any(
        k in fn_lower
        for k in ("điển-tích", "điển tích", "điển-cố", "nlxh", "nlvh", "nghị-luận", "nghị luận")
    ):
        result["subject"] = "LITERATURE"
        if any(b in fn_lower for b in ("hành-trang", "hành trang", "200-", "cẩm-nang", "cẩm nang", "sổ-tay", "tổng-hợp")):
            result["detailed_exam_track"] = "Đề cương / Tài liệu ôn tập"
            result["exam_track"] = "THUONG"
    elif any(
        k in fn_lower
        for k in ("ielts", "toeic", "idioms", "grammar", "vocabulary", "tieng anh", "tiếng anh", "chuyên-anh", "chuyên anh")
    ):
        result["subject"] = "ENGLISH"
        if any(k in fn_lower for k in ("ielts", "toeic")):
            result["exam_track"] = "QUOC_TE"
            result["detailed_exam_track"] = "Đề luyện thi Chứng chỉ Quốc tế (IELTS/TOEIC/SAT)"

    # Kiểm toán Bẫy 1: Đề thi thử TN THPT / Giữa kỳ / Học kỳ của Trường THPT Chuyên -> THUONG
    det_lower = str(result.get("detailed_exam_track") or "").lower()
    if any(
        kw in det_lower
        for kw in ("thi thử", "tốt nghiệp", "học kỳ", "giữa học kỳ", "giữa kỳ", "khảo sát")
    ):
        if str(result.get("exam_track") or "").upper() in ("CHUYEN", "HSG"):
            if not re.search(
                r"(chọn\s*học\s*sinh\s*giỏi|đề\s*thi\s*hsg|chọn\s*đội\s*tuyển|olympic)",
                head_text,
            ):
                result["exam_track"] = "THUONG"

    # Kiểm toán Bẫy 3: Khối 6, 7, 8, 9 không có môn ECONOMIC_LEGAL_EDU (đó là CIVIC_EDUCATION)
    grade_str = str(result.get("grade_level") or "")
    if any(g in grade_str for g in ("Khối 6", "Khối 7", "Khối 8", "Khối 9")):
        if result.get("subject") == "ECONOMIC_LEGAL_EDU":
            result["subject"] = "CIVIC_EDUCATION"
    elif any(g in grade_str for g in ("Khối 10", "Khối 11", "Khối 12")):
        if result.get("subject") == "NATURAL_SCIENCE" and not re.search(
            r"khoa\s*học\s*tự\s*nhiên\s*(?:6|7|8|9)", head_text
        ):
            # Nếu lỡ gán NATURAL_SCIENCE cho cấp 3 (do tên trường ĐH KHTN), suy luận lại môn thực
            if re.search(r"(dao\s*động|sóng\s*cơ|điện\s*xoay\s*chiều|hạt\s*nhân|cảm\s*ứng\s*điện\s*từ)", (raw_text or "").lower()):
                result["subject"] = "PHYSICS"
            elif re.search(r"(ester|carbohydrate|amino\s*acid|polymer|nguyên\s*tử|mol)", (raw_text or "").lower()):
                result["subject"] = "CHEMISTRY"
            elif re.search(r"(phiên\s*mã|dịch\s*mã|nhiễm\s*sắc\s*thể|quần\s*thể|di\s*truyền)", (raw_text or "").lower()):
                result["subject"] = "BIOLOGY"
            else:
                result["subject"] = "MATHEMATICS"

    return result


class CloudExamVerifier:
    """Hệ thống Multi-Agent Thẩm Định Đề Thi (Reader 550B -> Trap Auditor -> Arbiter 120B)."""

    @classmethod
    def get_quota_stats(cls) -> Dict[str, Any]:
        _ensure_disk_cache_loaded()
        now = time.time()
        with _LOCK:
            while _MINUTE_WINDOW and now - _MINUTE_WINDOW[0] >= 60.0:
                _MINUTE_WINDOW.popleft()
            while _DAY_WINDOW and now - _DAY_WINDOW[0] >= 86400.0:
                _DAY_WINDOW.popleft()
            return {
                "rpm_used": len(_MINUTE_WINDOW),
                "rpm_limit": MAX_REQUESTS_PER_MINUTE,
                "rpd_used": len(_DAY_WINDOW),
                "rpd_limit": MAX_REQUESTS_PER_DAY,
                "cache_size": len(_VERIFICATION_CACHE),
                "pending_45s_queue": len(_PENDING_45S_QUEUE),
            }

    @classmethod
    def enqueue_for_45s_batch(
        cls,
        doc_id: int | str,
        file_name: str,
        raw_text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        _ensure_disk_cache_loaded()
        effective_text = (raw_text or "").strip()
        if len(effective_text) < 10 and len((file_name or "").strip()) < 4:
            return
        fp = _make_fingerprint(file_name, effective_text)
        with _LOCK:
            key = str(doc_id or fp)
            _PENDING_45S_QUEUE[key] = {
                "doc_id": doc_id,
                "file_name": file_name,
                "raw_text": effective_text or f"Tài liệu: {file_name}",
                "fingerprint": fp,
                "metadata": metadata or {},
                "enqueued_at": time.time(),
            }

    @classmethod
    def flush_45s_batch(cls, max_items: int = 24) -> List[Dict[str, Any]]:
        _ensure_disk_cache_loaded()
        with _LOCK:
            if not _PENDING_45S_QUEUE:
                return []
            batch_entries: List[Dict[str, Any]] = []
            keys_to_pop = list(_PENDING_45S_QUEUE.keys())[:max_items]
            for k in keys_to_pop:
                batch_entries.append(_PENDING_45S_QUEUE.pop(k))

        items_input = [
            {"file_name": e["file_name"], "raw_text": e["raw_text"]} for e in batch_entries
        ]
        verified_list = cls.verify_batch(items_input, timeout_sec=50.0)

        completed: List[Dict[str, Any]] = []
        for entry, v_res in zip(batch_entries, verified_list):
            if v_res and isinstance(v_res, dict) and v_res.get("subject"):
                completed.append(
                    {
                        "doc_id": entry["doc_id"],
                        "file_name": entry["file_name"],
                        "verified": v_res,
                        "metadata": entry["metadata"],
                    }
                )
        return completed

    @classmethod
    def should_invoke_cloud(
        cls,
        file_name: str,
        raw_text: str,
        local_subject: str,
        local_grade: str,
        local_track: str,
        local_confidence: float,
        has_conflict: bool = False,
    ) -> bool:
        return bool((raw_text and len(raw_text.strip()) >= 15) or (file_name and len(file_name.strip()) >= 5))

    @classmethod
    def _call_single_model(
        cls,
        base_url: str,
        api_key: str,
        model_name: str,
        system_prompt: str,
        user_prompt: str,
        timeout_sec: float,
    ) -> Optional[Dict[str, Any]]:
        for attempt in range(2):
            try:
                payload = _build_payload_for_model(
                    model_name, system_prompt, user_prompt, base_tokens=450
                )
                req = urllib.request.Request(
                    f"{base_url}/chat/completions",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                )
                with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                    msg = body.get("choices", [{}])[0].get("message", {})
                    content = (msg.get("content") or "").strip()
                    if not content:
                        content = (msg.get("reasoning_content") or "").strip()
                    parsed = cls._extract_json(content)
                    if parsed and parsed.get("subject"):
                        return parsed
                break
            except urllib.error.HTTPError as he:
                if he.code == 429 and attempt == 0:
                    time.sleep(2.5)
                    continue
                logger.debug("CloudExamVerifier HTTP %s (%s)", he.code, model_name)
                break
            except Exception as e:
                logger.debug("CloudExamVerifier (%s) bỏ qua: %s", model_name, e)
                break
        return None

    @classmethod
    def verify_exam(
        cls,
        file_name: str,
        raw_text: str,
        timeout_sec: float = 45.0,
    ) -> Optional[Dict[str, Any]]:
        """
        Thực thi Pipeline 3-Agent:
        1. Reader Agent (550B Ultra Thinking) đọc sâu toàn bộ đề (Đầu + Giữa + Cuối).
        2. Trap Auditor Agent kiểm toán hậu kiểm 5 bẫy kinh điển.
        3. Arbiter Agent (120B / Gemma-4-31B) hội chẩn độc lập nếu kết quả còn mơ hồ (confidence < 0.90 hoặc GENERAL).
        """
        _ensure_disk_cache_loaded()
        api_key, base_url, primary_model, fallback_model = _get_nvidia_credentials()
        clean_text = (raw_text or "").strip()
        if not api_key or (len(clean_text) < 10 and len((file_name or "").strip()) < 4):
            return None

        fp = _make_fingerprint(file_name, clean_text)
        with _LOCK:
            cached = _VERIFICATION_CACHE.get(fp)
            if cached is not None:
                _VERIFICATION_CACHE.move_to_end(fp)
                return _deterministic_post_audit(file_name, clean_text, dict(cached))

        if not _acquire_rate_limit_slot(wait_if_needed=True, max_wait_sec=35.0):
            cls.enqueue_for_45s_batch(doc_id=fp, file_name=file_name, raw_text=clean_text)
            return None

        if len(clean_text) > 36000:
            mid = len(clean_text) // 2
            snippet = (
                clean_text[:18000]
                + "\n...[PHẦN GIỮA ĐỀ]...\n"
                + clean_text[mid - 5000 : mid + 5000]
                + "\n...[PHẦN CUỐI ĐỀ & ĐÁP ÁN]...\n"
                + clean_text[-8000:]
            )
        else:
            snippet = clean_text or f"(Tệp quét ảnh / dữ liệu bảng: {file_name})"

        user_prompt = (
            f"Tên tệp: {file_name}\n"
            f"Nội dung trích xuất đề thi:\n{snippet}\n\n"
            "Hãy vận dụng Quy trình Tư duy Đọc Đề 6 Bước và trả về đúng 1 JSON:"
        )

        models_chain = _build_model_chain(primary_model, fallback_model)
        primary_result: Optional[Dict[str, Any]] = None
        used_model: Optional[str] = None

        # AGENT 1: Reader & Curriculum Analyst
        for model_name in models_chain:
            res = cls._call_single_model(
                base_url, api_key, model_name, SYSTEM_PROMPT_VI, user_prompt, timeout_sec
            )
            if res:
                primary_result = res
                used_model = model_name
                break

        if not primary_result:
            return None

        # AGENT 2: Deterministic Trap Auditor
        audited_result = _deterministic_post_audit(file_name, clean_text, primary_result)

        # AGENT 3: Independent Arbiter (kích hoạt khi môn/khối còn mơ hồ hoặc confidence < 0.90)
        conf_val = float(audited_result.get("confidence") or 0.95)
        needs_arbiter = (
            conf_val < 0.90
            or audited_result.get("subject") in ("GENERAL", "UNKNOWN", None)
            or audited_result.get("grade_level") in ("Không xác định", "UNKNOWN", None)
        )
        if needs_arbiter:
            arbiter_candidates = [m for m in models_chain if m != used_model]
            if arbiter_candidates and _acquire_rate_limit_slot(
                wait_if_needed=False, max_wait_sec=2.0
            ):
                arbiter_prompt = (
                    f"Tên tệp: {file_name}\n"
                    f"Kết quả sơ bộ của Agent 1: {json.dumps(audited_result, ensure_ascii=False)}\n"
                    f"Nội dung trích xuất:\n{snippet[:16000]}\n\n"
                    "Hãy kiểm định độc lập và trả về JSON chính xác nhất:"
                )
                arb_res = cls._call_single_model(
                    base_url,
                    api_key,
                    arbiter_candidates[0],
                    ARBITER_PROMPT_VI,
                    arbiter_prompt,
                    timeout_sec=25.0,
                )
                if arb_res and arb_res.get("subject") not in ("GENERAL", None):
                    audited_result = _deterministic_post_audit(file_name, clean_text, arb_res)

        with _LOCK:
            _VERIFICATION_CACHE[fp] = dict(audited_result)
            if len(_VERIFICATION_CACHE) > _MAX_CACHE_SIZE:
                _VERIFICATION_CACHE.popitem(last=False)
        _save_to_disk_cache(fp, audited_result)

        return audited_result

    @classmethod
    def verify_batch(
        cls,
        items: List[Dict[str, str]],
        timeout_sec: float = 55.0,
    ) -> List[Optional[Dict[str, Any]]]:
        _ensure_disk_cache_loaded()
        if not items:
            return []

        api_key, base_url, primary_model, fallback_model = _get_nvidia_credentials()
        if not api_key:
            return [None] * len(items)

        results: List[Optional[Dict[str, Any]]] = [None] * len(items)
        uncached_indices: List[int] = []
        uncached_fps: List[str] = []

        with _LOCK:
            for idx, item in enumerate(items):
                fn = item.get("file_name", "")
                rt = (item.get("raw_text", "") or "").strip()
                if len(rt) < 10 and len(fn.strip()) < 4:
                    continue
                fp = _make_fingerprint(fn, rt)
                cached = _VERIFICATION_CACHE.get(fp)
                if cached is not None:
                    _VERIFICATION_CACHE.move_to_end(fp)
                    results[idx] = _deterministic_post_audit(fn, rt, dict(cached))
                else:
                    uncached_indices.append(idx)
                    uncached_fps.append(fp)

        if not uncached_indices:
            return results

        if len(uncached_indices) == 1:
            idx0 = uncached_indices[0]
            results[idx0] = cls.verify_exam(
                items[idx0].get("file_name", ""),
                items[idx0].get("raw_text", ""),
                timeout_sec=timeout_sec,
            )
            return results

        models_chain = _build_model_chain(primary_model, fallback_model)
        batch_size = 4

        for start in range(0, len(uncached_indices), batch_size):
            chunk_indices = uncached_indices[start : start + batch_size]
            chunk_fps = uncached_fps[start : start + batch_size]

            if not _acquire_rate_limit_slot(wait_if_needed=True, max_wait_sec=40.0):
                break

            blocks = []
            for local_i, orig_idx in enumerate(chunk_indices):
                fn = items[orig_idx].get("file_name", "")
                rt = (items[orig_idx].get("raw_text", "") or "").strip()
                if len(rt) > 6000:
                    mid = len(rt) // 2
                    snippet = (
                        rt[:3000]
                        + "\n...\n"
                        + rt[mid - 1000 : mid + 1000]
                        + "\n...\n"
                        + rt[-1500:]
                    )
                else:
                    snippet = rt or f"(Tài liệu: {fn})"
                blocks.append(f"--- ĐỀ SỐ {local_i} ---\nTên tệp: {fn}\nNội dung:\n{snippet}")

            batch_prompt = (
                "Vận dụng Quy trình Tư duy Đọc Đề 6 Bước để phân loại danh sách các đề thi dưới đây. "
                'Trả về DUY NHẤT 1 đối tượng JSON có dạng {"items": [ ... ]} '
                f"gồm đúng {len(chunk_indices)} phần tử theo đúng thứ tự ĐỀ SỐ 0 đến ĐỀ SỐ {len(chunk_indices) - 1}.\n\n"
                + "\n\n".join(blocks)
            )

            batch_succeeded = False
            for model_name in models_chain:
                try:
                    payload = _build_payload_for_model(
                        model_name,
                        SYSTEM_PROMPT_VI,
                        batch_prompt,
                        base_tokens=400 * len(chunk_indices),
                    )
                    req = urllib.request.Request(
                        f"{base_url}/chat/completions",
                        data=json.dumps(payload).encode("utf-8"),
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                    )
                    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                        body = json.loads(resp.read().decode("utf-8"))
                        msg = body.get("choices", [{}])[0].get("message", {})
                        content = (msg.get("content") or "").strip()
                        if not content:
                            content = (msg.get("reasoning_content") or "").strip()
                        parsed_obj = cls._extract_json(content)
                        arr = (
                            parsed_obj.get("items")
                            if isinstance(parsed_obj, dict)
                            else None
                        )
                        if isinstance(arr, list) and len(arr) == len(chunk_indices):
                            for local_i, orig_idx in enumerate(chunk_indices):
                                item_res = arr[local_i]
                                if isinstance(item_res, dict) and item_res.get("subject"):
                                    fn_i = items[orig_idx].get("file_name", "")
                                    rt_i = items[orig_idx].get("raw_text", "")
                                    audited_i = _deterministic_post_audit(
                                        fn_i, rt_i, item_res
                                    )
                                    results[orig_idx] = audited_i
                                    with _LOCK:
                                        _VERIFICATION_CACHE[chunk_fps[local_i]] = dict(
                                            audited_i
                                        )
                                    _save_to_disk_cache(chunk_fps[local_i], audited_i)
                            batch_succeeded = True
                            break
                except Exception as e:
                    logger.debug("CloudExamVerifier batch (%s) bỏ qua: %s", model_name, e)
                    continue

            if not batch_succeeded:
                for orig_idx in chunk_indices:
                    results[orig_idx] = cls.verify_exam(
                        items[orig_idx].get("file_name", ""),
                        items[orig_idx].get("raw_text", ""),
                        timeout_sec=timeout_sec,
                    )

        return results

    @staticmethod
    def _extract_json(text: str) -> Optional[Dict[str, Any]]:
        if not text:
            return None
        matches = list(re.finditer(r"\{[\s\S]*\}", text))
        if not matches:
            return None
        raw_block = matches[-1].group(0)
        try:
            obj = json.loads(raw_block)
            return obj if isinstance(obj, dict) else None
        except Exception:
            sub_matches = re.findall(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text)
            for candidate in reversed(sub_matches):
                try:
                    obj = json.loads(candidate)
                    if isinstance(obj, dict) and ("subject" in obj or "items" in obj):
                        return obj
                except Exception:
                    continue
            return None
