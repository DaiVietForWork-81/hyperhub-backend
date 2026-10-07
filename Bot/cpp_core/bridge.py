"""
cpp_core/bridge.py
Python Bridge with Seamless C-ABI C++ Shared Library Loading & Pure-Python Fallback.

Features:
- Dynamically loads native_core.so (Linux) or native_core.dll (Windows).
- 100% Graceful Fallback: If shared library is not found or fails to load,
  pure Python implementations execute with identical signatures and outputs.
- Provides IS_NATIVE_ACCELERATED flag for diagnostics.
"""

from __future__ import annotations

import ctypes
import logging
import math
import os
import re
import sys
from typing import Any

logger = logging.getLogger("CPPCore")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

_native_lib: ctypes.CDLL | None = None
IS_NATIVE_ACCELERATED: bool = False

# Tìm file thư viện phù hợp theo nền tảng
if sys.platform == "win32":
    _candidate_paths = [
        os.path.join(SCRIPT_DIR, "native_core.dll"),
        os.path.join(SCRIPT_DIR, "build", "native_core.dll"),
    ]
else:
    _candidate_paths = [
        os.path.join(SCRIPT_DIR, "native_core.so"),
        os.path.join(SCRIPT_DIR, "build", "native_core.so"),
    ]

for _path in _candidate_paths:
    if os.path.isfile(_path):
        try:
            _lib = ctypes.CDLL(_path)

            # Cấu hình kiểu dữ liệu các hàm C-ABI
            _lib.calculate_shannon_entropy.argtypes = [ctypes.c_char_p, ctypes.c_int]
            _lib.calculate_shannon_entropy.restype = ctypes.c_double

            _lib.fast_code_metrics.argtypes = [
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_double),
            ]
            _lib.fast_code_metrics.restype = None

            _lib.fast_token_compare.argtypes = [
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_double,
                ctypes.c_char_p,
                ctypes.c_int,
            ]
            _lib.fast_token_compare.restype = ctypes.c_int

            _lib.fast_levenshtein_similarity.argtypes = [
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_int,
            ]
            _lib.fast_levenshtein_similarity.restype = ctypes.c_double

            # Các hàm C++ tăng tốc xử lý AI
            if hasattr(_lib, "fast_clean_think_tags"):
                _lib.fast_clean_think_tags.argtypes = [
                    ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int
                ]
                _lib.fast_clean_think_tags.restype = ctypes.c_int

            if hasattr(_lib, "fast_dedup_consecutive_words"):
                _lib.fast_dedup_consecutive_words.argtypes = [
                    ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int
                ]
                _lib.fast_dedup_consecutive_words.restype = ctypes.c_int

            if hasattr(_lib, "fast_extract_json_block"):
                _lib.fast_extract_json_block.argtypes = [
                    ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int
                ]
                _lib.fast_extract_json_block.restype = ctypes.c_int

            if hasattr(_lib, "fast_sha256"):
                _lib.fast_sha256.argtypes = [
                    ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int
                ]
                _lib.fast_sha256.restype = None

            if hasattr(_lib, "fast_detect_magic_bytes"):
                _lib.fast_detect_magic_bytes.argtypes = [
                    ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int
                ]
                _lib.fast_detect_magic_bytes.restype = ctypes.c_int

            if hasattr(_lib, "fast_classify_exam"):
                _lib.fast_classify_exam.argtypes = [
                    ctypes.c_char_p, ctypes.c_int,
                    ctypes.c_char_p, ctypes.c_int,
                    ctypes.POINTER(ctypes.c_int),
                    ctypes.c_char_p, ctypes.c_int,
                    ctypes.c_char_p, ctypes.c_int,
                    ctypes.POINTER(ctypes.c_double),
                    ctypes.POINTER(ctypes.c_int),
                    ctypes.POINTER(ctypes.c_int),
                ]
                _lib.fast_classify_exam.restype = ctypes.c_int

            if hasattr(_lib, "fast_batch_cosine_similarity"):
                _lib.fast_batch_cosine_similarity.argtypes = [
                    ctypes.POINTER(ctypes.c_float),
                    ctypes.POINTER(ctypes.c_float),
                    ctypes.c_int,
                    ctypes.c_int,
                    ctypes.POINTER(ctypes.c_float),
                ]
                _lib.fast_batch_cosine_similarity.restype = None

            _native_lib = _lib
            IS_NATIVE_ACCELERATED = True
            logger.info(f"[C++ Native Core] Đã kích hoạt C++ Engine tăng tốc từ: {_path}")
            break
        except Exception as _e:
            logger.warning(f"[C++ Native Core] Không thể nạp {_path}: {_e}. Fallback về Pure Python.")

if not IS_NATIVE_ACCELERATED:
    logger.info("[C++ Native Core] Shared library chưa được biên dịch. Đang sử dụng Pure-Python Fallback Engine.")


# ==============================================================================
# PURE PYTHON IMPLEMENTATIONS (FALLBACK 100%)
# ==============================================================================

def _py_calculate_entropy(text: str) -> float:
    """Tính Shannon Entropy bằng Python thuần."""
    if not text:
        return 0.0
    filtered = [ord(c) for c in text if c not in ("\r", "\n") and ord(c) < 256]
    if not filtered:
        return 0.0

    counts: dict[int, int] = {}
    for b in filtered:
        counts[b] = counts.get(b, 0) + 1

    total = len(filtered)
    entropy = 0.0
    for count in counts.values():
        p = count / total
        entropy -= p * math.log2(p)
    return entropy


def _py_code_metrics(code: str) -> dict[str, Any]:
    """Phân tích cấu trúc mã nguồn bằng Python thuần."""
    if not code:
        return {
            "lines": 0,
            "comment_lines": 0,
            "blank_lines": 0,
            "entropy": 0.0,
            "comment_ratio": 0.0,
        }

    lines = code.splitlines()
    total_lines = len(lines)
    comment_lines = 0
    blank_lines = 0

    for line in lines:
        stripped = line.strip()
        if not stripped:
            blank_lines += 1
        elif stripped.startswith(("#", "//", "/*", "*")):
            comment_lines += 1

    entropy = _py_calculate_entropy(code)
    comment_ratio = comment_lines / max(1, total_lines)

    return {
        "lines": total_lines,
        "comment_lines": comment_lines,
        "blank_lines": blank_lines,
        "entropy": round(entropy, 4),
        "comment_ratio": round(comment_ratio, 4),
    }


def _py_compare_output(
    actual: str,
    expected: str,
    float_epsilon: float = 1e-6,
) -> tuple[bool, str, str]:
    """So khớp token và số thực bằng Python thuần."""
    actual_tokens = actual.strip().split()
    expected_tokens = expected.strip().split()

    if len(actual_tokens) != len(expected_tokens):
        if len(actual_tokens) < len(expected_tokens):
            details = (
                f"Thiếu dữ liệu đầu ra: Nhận được ít hơn số lượng giá trị kỳ vọng "
                f"(dừng tại token #{len(actual_tokens) + 1})."
            )
        else:
            details = (
                f"Thừa dữ liệu đầu ra: Nhận được nhiều hơn số lượng giá trị kỳ vọng "
                f"(thừa từ token #{len(expected_tokens) + 1})."
            )
        return False, "Kết quả sai (Wrong Answer)", details

    for i, (act_tok, exp_tok) in enumerate(zip(actual_tokens, expected_tokens), start=1):
        if act_tok == exp_tok:
            continue

        try:
            act_val = float(act_tok)
            exp_val = float(exp_tok)
            diff = abs(act_val - exp_val)
            denom = max(1.0, abs(exp_val))
            if diff / denom <= float_epsilon:
                continue
            else:
                return (
                    False,
                    "Kết quả sai (Wrong Answer)",
                    f"Sai số thực tại token #{i}: Kỳ vọng `{exp_tok}`, nhận được `{act_tok}` "
                    f"(Độ lệch: {diff:g} > {float_epsilon}).",
                )
        except ValueError:
            return (
                False,
                "Kết quả sai (Wrong Answer)",
                f"Giá trị không khớp tại token #{i}: Kỳ vọng `{exp_tok}`, nhận được `{act_tok}`.",
            )

    return True, "Chấp nhận (Accepted)", "Toàn bộ kết quả đầu ra đều khớp chính xác."


def _py_levenshtein_similarity(s1: str, s2: str) -> float:
    """Tính độ tương đồng Levenshtein bằng Python thuần."""
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0

    s1 = s1[:4096]
    s2 = s2[:4096]

    if s1 == s2:
        return 1.0

    if len(s1) < len(s2):
        s1, s2 = s2, s1

    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1, start=1):
        curr = [i] * (len(s2) + 1)
        for j, c2 in enumerate(s2, start=1):
            cost = 0 if c1 == c2 else 1
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
        prev = curr

    distance = prev[-1]
    max_len = max(len(s1), len(s2))
    return max(0.0, min(1.0, 1.0 - (distance / max_len)))


def _py_clean_think_tags(text: str) -> str:
    """Lọc bỏ toàn bộ khối suy luận <think>...</think> bằng Python."""
    import re
    if not text:
        return ""
    cleaned = re.sub(r"(?is)<think>.*?(?:</think>|$)", "", text)
    cleaned = re.sub(r"(?i)</?think[^>]*>", "", cleaned)
    cleaned = re.sub(r"</?>", "", cleaned)
    return cleaned


def _py_dedup_words(text: str) -> str:
    """Khử lặp từ liên tiếp bằng Python."""
    import re
    if not text:
        return ""
    dup_word = re.compile(r"(?i)\b(\w+)\s+\1\b")
    cleaned = text
    for _ in range(5):
        new_cleaned = dup_word.sub(r"\1", cleaned)
        if new_cleaned == cleaned:
            break
        cleaned = new_cleaned
    return cleaned


def _py_extract_json(text: str) -> str:
    """Trích xuất khối JSON {...} bằng Python."""
    import re
    if not text:
        return ""
    cleaned = text.strip()
    if "```" in cleaned:
        code_block = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
        if code_block:
            cleaned = code_block.group(1).strip()
    s = cleaned.find("{")
    e = cleaned.rfind("}")
    if s != -1 and e != -1 and e > s:
        cleaned = cleaned[s : e + 1]
    cleaned = re.sub(r',\s*([}\]])', r'\1', cleaned)
    return cleaned


# ==============================================================================
# PUBLIC API (TỰ ĐỘNG CHỌN C++ NATIVE HOẶC PYTHON FALLBACK)
# ==============================================================================

def calculate_entropy(text: str) -> float:
    """
    Tính Shannon Entropy của chuỗi văn bản/mã nguồn.
    Sử dụng C++ nếu khả dụng, fallback về Pure Python.
    """
    if not text:
        return 0.0

    if IS_NATIVE_ACCELERATED and _native_lib is not None:
        try:
            b_text = text.encode("utf-8", errors="ignore")
            val = _native_lib.calculate_shannon_entropy(b_text, len(b_text))
            return float(val)
        except Exception:
            pass

    return _py_calculate_entropy(text)


def fast_code_metrics(code: str) -> dict[str, Any]:
    """
    Trích xuất nhanh các chỉ số dòng, dòng comment, dòng trống và entropy.
    """
    if not code:
        return {
            "lines": 0,
            "comment_lines": 0,
            "blank_lines": 0,
            "entropy": 0.0,
            "comment_ratio": 0.0,
        }

    if IS_NATIVE_ACCELERATED and _native_lib is not None:
        try:
            b_code = code.encode("utf-8", errors="ignore")
            c_lines = ctypes.c_int(0)
            c_comments = ctypes.c_int(0)
            c_blanks = ctypes.c_int(0)
            c_entropy = ctypes.c_double(0.0)

            _native_lib.fast_code_metrics(
                b_code,
                len(b_code),
                ctypes.byref(c_lines),
                ctypes.byref(c_comments),
                ctypes.byref(c_blanks),
                ctypes.byref(c_entropy),
            )

            total_l = c_lines.value
            comm_l = c_comments.value
            ratio = comm_l / max(1, total_l)

            return {
                "lines": total_l,
                "comment_lines": comm_l,
                "blank_lines": c_blanks.value,
                "entropy": round(c_entropy.value, 4),
                "comment_ratio": round(ratio, 4),
            }
        except Exception:
            pass

    return _py_code_metrics(code)


def fast_compare_output(
    actual: str,
    expected: str,
    float_epsilon: float = 1e-6,
) -> tuple[bool, str, str]:
    """
    So khớp kết quả đầu ra giữa actual và expected.
    Trả về: (passed: bool, verdict: str, details: str).
    """
    if IS_NATIVE_ACCELERATED and _native_lib is not None:
        try:
            b_act = actual.encode("utf-8", errors="ignore")
            b_exp = expected.encode("utf-8", errors="ignore")
            err_buf = ctypes.create_string_buffer(1024)

            ret = _native_lib.fast_token_compare(
                b_act,
                len(b_act),
                b_exp,
                len(b_exp),
                float(float_epsilon),
                err_buf,
                len(err_buf),
            )

            details = err_buf.value.decode("utf-8", errors="replace")
            if ret == 0:
                return True, "Chấp nhận (Accepted)", details
            else:
                return False, "Kết quả sai (Wrong Answer)", details
        except Exception:
            pass

    return _py_compare_output(actual, expected, float_epsilon)


def fast_similarity(s1: str, s2: str) -> float:
    """
    Tính độ tương đồng chuỗi Levenshtein (0.0 -> 1.0).
    """
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0

    if IS_NATIVE_ACCELERATED and _native_lib is not None:
        try:
            b_s1 = s1.encode("utf-8", errors="ignore")
            b_s2 = s2.encode("utf-8", errors="ignore")
            val = _native_lib.fast_levenshtein_similarity(
                b_s1, len(b_s1), b_s2, len(b_s2)
            )
            return float(val)
        except Exception:
            pass

    return _py_levenshtein_similarity(s1, s2)


def clean_think_tags(text: str) -> str:
    """Lọc bỏ toàn bộ khối suy luận <think>...</think> của LLM (C++ hoặc Python)."""
    if not text:
        return ""
    if IS_NATIVE_ACCELERATED and _native_lib is not None and hasattr(_native_lib, "fast_clean_think_tags"):
        try:
            b_text = text.encode("utf-8", errors="ignore")
            buf_size = max(len(b_text) + 256, 1024)
            out_buf = ctypes.create_string_buffer(buf_size)
            ret = _native_lib.fast_clean_think_tags(b_text, len(b_text), out_buf, buf_size)
            if ret >= 0:
                return out_buf.value.decode("utf-8", errors="replace")
        except Exception:
            pass
    return _py_clean_think_tags(text)


def dedup_words(text: str) -> str:
    """Khử lặp từ liên tiếp chống nói lắp của LLM (C++ hoặc Python)."""
    if not text:
        return ""
    if IS_NATIVE_ACCELERATED and _native_lib is not None and hasattr(_native_lib, "fast_dedup_consecutive_words"):
        try:
            b_text = text.encode("utf-8", errors="ignore")
            buf_size = max(len(b_text) + 256, 1024)
            out_buf = ctypes.create_string_buffer(buf_size)
            ret = _native_lib.fast_dedup_consecutive_words(b_text, len(b_text), out_buf, buf_size)
            if ret >= 0:
                return out_buf.value.decode("utf-8", errors="replace")
        except Exception:
            pass
    return _py_dedup_words(text)


def fast_extract_json(text: str) -> str:
    """Trích xuất và làm sạch khối JSON {...} từ output AI (C++ hoặc Python)."""
    if not text:
        return ""
    if IS_NATIVE_ACCELERATED and _native_lib is not None and hasattr(_native_lib, "fast_extract_json_block"):
        try:
            b_text = text.encode("utf-8", errors="ignore")
            buf_size = max(len(b_text) + 256, 1024)
            out_buf = ctypes.create_string_buffer(buf_size)
            ret = _native_lib.fast_extract_json_block(b_text, len(b_text), out_buf, buf_size)
            if ret > 0:
                return out_buf.value.decode("utf-8", errors="replace")
        except Exception:
            pass
    return _py_extract_json(text)


def fast_sha256(data: bytes) -> str:
    """Tính SHA-256 hash của dữ liệu nhị phân (C++ hoặc Python hashlib fallback)."""
    if not data:
        return ""
    if IS_NATIVE_ACCELERATED and _native_lib is not None and hasattr(_native_lib, "fast_sha256"):
        try:
            out_hex = ctypes.create_string_buffer(65)
            _native_lib.fast_sha256(data, len(data), out_hex, 65)
            result = out_hex.value.decode("ascii", errors="replace")
            if len(result) == 64:
                return result
        except Exception:
            pass
    import hashlib
    return hashlib.sha256(data).hexdigest()


def fast_detect_magic(data: bytes) -> str:
    """Nhận dạng loại file bằng Magic Bytes header (C++ hoặc Python fallback)."""
    if not data or len(data) < 4:
        return "UNKNOWN"
    if IS_NATIVE_ACCELERATED and _native_lib is not None and hasattr(_native_lib, "fast_detect_magic_bytes"):
        try:
            out_type = ctypes.create_string_buffer(32)
            ret = _native_lib.fast_detect_magic_bytes(data, len(data), out_type, 32)
            if ret > 0:
                return out_type.value.decode("ascii", errors="replace")
        except Exception:
            pass
    # Pure Python fallback
    if data[:4] == b'%PDF':
        return 'PDF'
    if data[:4] == b'PK\x03\x04':
        header_str = data[:2000].decode('latin-1', errors='ignore')
        if 'word/' in header_str:
            return 'DOCX'
        if 'xl/' in header_str:
            return 'XLSX'
        if 'ppt/' in header_str:
            return 'PPTX'
        return 'ZIP'
    if data[:4] == b'\xD0\xCF\x11\xE0':
        return 'DOC_OLE2'
    if data[:4] == b'\x89PNG':
        return 'PNG'
    if data[:3] == b'\xFF\xD8\xFF':
        return 'JPEG'
    if data[:2] == b'MZ':
        return 'EXE_PE'
    return 'UNKNOWN'


def _py_classify_exam(text: str) -> dict:
    """Pure-Python fallback phân loại đề thi (Đầy đủ trọng số & độ chính xác cao)."""
    if not text:
        return {
            'subject': 'GENERAL', 'grade': 0, 'track': 'thuong',
            'exam_type': 'ON_TAP', 'confidence': 0.0, 'question_count': 0,
            'has_answers': False, 'engine': 'python_fallback'
        }
    t = text.lower()

    # 1. Phân loại Môn học (Subject Scoring)
    SUBJ_WEIGHTS = {
        'MATH': [('môn toán', 15), ('toán học', 12), ('toán', 10), ('toan hoc', 12), ('toanhoc', 10), ('tich phan', 5), ('dao ham', 5), ('đạo hàm', 5), ('tích phân', 6), ('nguyên hàm', 5), ('hàm số', 4), ('logarit', 5), ('tiệm cận', 4), ('bất đẳng thức', 4), ('vectơ', 4), ('tọa độ', 3), ('oxyz', 5), ('mặt cầu', 4), ('phương trình', 2), ('sin(', 3), ('cos(', 3), ('f(x)', 3), ('lim ', 3)],
        'PHYSICS': [('môn vật lí', 15), ('môn vật lý', 15), ('vật lý', 12), ('vật lí', 12), ('vat ly', 15), ('vat lí', 15), ('vatly', 10), ('vatli', 10), ('dao động', 8), ('dao dong', 7), ('bien do', 5), ('con lắc', 7), ('sóng cơ', 6), ('sóng ánh sáng', 6), ('điện xoay chiều', 7), ('quang phổ', 5), ('thấu kính', 5), ('động năng', 4), ('thế năng', 4), ('hạt nhân', 5), ('phóng xạ', 5), ('bước sóng', 4), ('vôn kế', 4), ('ampe kế', 4)],
        'CHEMISTRY': [('môn hóa học', 15), ('môn hóa', 12), ('hóa học', 12), ('hoa hoc', 15), ('hoahoc', 10), ('hoa', 8), ('este', 8), ('amin', 7), ('ancol', 6), ('axit cacboxylic', 7), ('cacbohiđrat', 6), ('kim loại', 5), ('kết tủa', 5), ('phản ứng', 3), ('đồng phân', 5), ('h2so4', 5), ('naoh', 5), ('hcl', 5), ('mol', 4)],
        'BIOLOGY': [('môn sinh học', 15), ('môn sinh', 12), ('sinh học', 12), ('sinh hoc', 15), ('sinhhoc', 10), ('nhiễm sắc thể', 8), ('đột biến', 8), ('di truyền', 7), ('menden', 6), ('hệ sinh thái', 6), ('quần thể', 6), ('adn', 6), ('arn', 6), ('tế bào', 4), ('quang hợp', 4), ('chuỗi thức ăn', 5)],
        'INFORMATICS': [
            ('môn tin học', 15), ('môn tin', 12), ('tin học', 12), ('tin hoc', 15), ('tinhoc', 10), ('thuật toán', 8), ('quy hoạch động', 8),
            ('đồ thị', 7), ('cây nhị phân', 7), ('độ phức tạp', 6), ('subtask', 8),
            ('time limit', 7), ('memory limit', 7), ('test case', 6),
            ('c++', 8), ('cpp', 7), ('#include', 8), ('std::', 7), ('vector<', 7), ('iostream', 7),
            ('python', 8), ('def ', 7), ('import ', 6), ('print(', 6),
            ('pascal', 8), ('program ', 7), ('begin', 5), ('writeln', 7),
            ('java', 8), ('public class', 8), ('system.out', 7),
            ('sql', 8), ('cơ sở dữ liệu', 8), ('csdl', 8),
            ('dsa', 8), ('cấu trúc dữ liệu', 8), ('segment tree', 8), ('dijkstra', 8),
            ('hsg tin', 12), ('tin học trẻ', 12), ('olympic tin', 12), ('vnoi', 8), ('codeforces', 8)
        ],
        'ENGLISH': [('môn tiếng anh', 15), ('english', 10), ('ielts', 14), ('toeic', 14), ('reading passage', 10), ('mark the letter', 10), ('pronunciation', 8), ('closest in meaning', 8), ('opposite in meaning', 8), ('word formation', 8), ('cloze test', 8), ('passage', 6)],
        'LITERATURE': [('môn ngữ văn', 15), ('ngữ văn', 12), ('ngu van', 15), ('nguvan', 10), ('văn học', 10), ('nghị luận xã hội', 8), ('nghị luận văn học', 8), ('đọc hiểu', 6), ('tác giả', 4), ('tác phẩm', 4), ('nhà thơ', 5), ('truyện kiều', 6), ('hình tượng', 5)],
        'HISTORY': [('môn lịch sử', 15), ('lịch sử', 12), ('lich su', 15), ('lichsu', 10), ('lịch sử việt nam', 12), ('cách mạng', 8), ('chiến dịch', 8), ('hiệp định', 8), ('thực dân pháp', 6), ('đảng cộng sản', 6), ('kháng chiến', 5)],
        'GEOGRAPHY': [('môn địa lí', 15), ('môn địa lý', 15), ('địa lý', 12), ('địa lí', 12), ('dia ly', 15), ('dia lí', 15), ('dialy', 10), ('atlat', 8), ('gió mùa', 7), ('đồng bằng', 7), ('chuyển dịch cơ cấu', 6), ('khí hậu', 5)],
        'CIVIC_EDUCATION': [('giáo dục công dân', 15), ('giao duc cong dan', 15), ('gdcd', 12), ('quyền bình đẳng', 8), ('vi phạm pháp luật', 8), ('trách nhiệm pháp lí', 7), ('nghĩa vụ của công dân', 6)],
    }

    best_subj = 'GENERAL'
    max_score = 0.0
    for subj, keywords in SUBJ_WEIGHTS.items():
        score = 0.0
        for kw, weight in keywords:
            if len(kw) <= 4:
                matches = len(re.findall(r'\b' + re.escape(kw) + r'\b', t))
            else:
                matches = t.count(kw)
            if matches > 0:
                score += weight * min(matches, 5)
        if score > max_score:
            max_score = score
            best_subj = subj

    # 2. Phân loại Khối lớp (Grade)
    grade = 0
    for g in range(12, 5, -1):
        if f'lớp {g}' in t or f'khối {g}' in t or f'k{g}' in t or f'{best_subj.lower()} {g}' in t:
            grade = g
            break
    if grade == 0:
        if any(k in t for k in ['tích phân', 'nguyên hàm', 'số phức', 'este', 'thpt quốc gia', 'tốt nghiệp thpt']):
            grade = 12
        elif any(k in t for k in ['cấp số cộng', 'cấp số nhân', 'thấu kính']):
            grade = 11
        elif any(k in t for k in ['mệnh đề', 'bảng tuần hoàn']):
            grade = 10
        elif any(k in t for k in ['căn bậc hai', 'vào lớp 10', 'tuyển sinh 10']):
            grade = 9

    # 3. Phân loại Thể loại (Track)
    track = 'thuong'
    if any(k in t for k in ['chuyên', 'olympic', 'hsgqg', 'amsterdam', 'vnoi', 'icpc', 'ielts', 'subtask']):
        track = 'chuyen'
    elif any(k in t for k in ['học sinh giỏi', 'hsg', 'chọn hsg']):
        track = 'hsg'

    # 4. Phân loại Dạng đề (Exam Type)
    exam_type = 'ON_TAP'
    if any(k in t for k in ['15 phút', '15p', 'thường xuyên']):
        exam_type = '15_PHUT'
    elif any(k in t for k in ['1 tiết', '45 phút', 'định kì', 'định kỳ']):
        exam_type = '1_TIET'
    elif any(k in t for k in ['giữa kì', 'giữa kỳ', 'giữa hk']):
        exam_type = 'GIUA_KY'
    elif any(k in t for k in ['cuối kì', 'cuối kỳ', 'học kì 1', 'học kì 2']):
        exam_type = 'CUOI_KY'
    elif any(k in t for k in ['thi thử', 'tốt nghiệp thpt', 'thpt quốc gia']):
        exam_type = 'THI_THU_THPT'
    elif any(k in t for k in ['tuyển sinh vào 10', 'tuyển sinh lớp 10', 'vào lớp 10']):
        exam_type = 'TUYEN_SINH_10'
    elif track in ('hsg', 'chuyen'):
        exam_type = 'HSG'

    # 5. Đếm số câu hỏi thực tế
    q_matches = [int(m) for m in re.findall(r'(?i)\b(?:câu|bài|question)\s+(\d+)\b', t)]
    question_count = max(q_matches) if q_matches else 0

    has_ans = any(k in t for k in ['đáp án', 'hướng dẫn chấm', 'lời giải chi tiết', '1.a', '1.b', '1-a', '1-b'])

    conf = 0.50
    if max_score > 30.0:
        conf = 0.99
    elif max_score > 15.0:
        conf = 0.95
    elif max_score > 6.0:
        conf = 0.88
    elif max_score > 0.0:
        conf = 0.75

    return {
        'subject': best_subj,
        'grade': grade,
        'track': track,
        'exam_type': exam_type,
        'confidence': conf,
        'question_count': question_count,
        'has_answers': has_ans,
        'engine': 'python_fallback'
    }


def fast_classify_exam(text: str) -> dict:
    """
    Phân loại đề thi siêu tốc (C++ Native Engine hoặc Pure-Python fallback).
    Thời gian thực thi: < 1 mili-giây.
    """
    if not text:
        return _py_classify_exam("")

    if IS_NATIVE_ACCELERATED and _native_lib is not None and hasattr(_native_lib, "fast_classify_exam"):
        try:
            text_bytes = text.encode('utf-8', errors='replace')
            out_subject = ctypes.create_string_buffer(32)
            out_grade = ctypes.c_int(0)
            out_track = ctypes.create_string_buffer(16)
            out_exam_type = ctypes.create_string_buffer(32)
            out_confidence = ctypes.c_double(0.0)
            out_qcount = ctypes.c_int(0)
            out_has_ans = ctypes.c_int(0)

            ret = _native_lib.fast_classify_exam(
                text_bytes, len(text_bytes),
                out_subject, 32,
                ctypes.byref(out_grade),
                out_track, 16,
                out_exam_type, 32,
                ctypes.byref(out_confidence),
                ctypes.byref(out_qcount),
                ctypes.byref(out_has_ans),
            )
            if ret > 0:
                return {
                    'subject': out_subject.value.decode('utf-8', errors='replace'),
                    'grade': int(out_grade.value),
                    'track': out_track.value.decode('utf-8', errors='replace'),
                    'exam_type': out_exam_type.value.decode('utf-8', errors='replace'),
                    'confidence': round(float(out_confidence.value), 2),
                    'question_count': int(out_qcount.value),
                    'has_answers': bool(out_has_ans.value),
                    'engine': 'cpp'
                }
        except Exception as e:
            logger.debug(f"[C++ Native Core] fast_classify_exam C++ call failed: {e}")

    return _py_classify_exam(text)


def fast_batch_cosine(query_vec, doc_vectors) -> list[float]:
    """
    Tính batch cosine similarity giữa 1 query vector (kích thước D)
    và N doc vectors (kích thước N x D).
    Trả về danh sách N float scores (phạm vi -1.0 đến 1.0).
    Sử dụng C++ SIMD hoặc NumPy fallback.
    """
    import numpy as np

    q = np.ascontiguousarray(query_vec, dtype=np.float32)
    docs = np.ascontiguousarray(doc_vectors, dtype=np.float32)

    if q.ndim != 1 or docs.ndim != 2:
        return []

    count, dim = docs.shape
    if count == 0 or dim == 0 or q.shape[0] != dim:
        return []

    if IS_NATIVE_ACCELERATED and _native_lib is not None and hasattr(_native_lib, "fast_batch_cosine_similarity"):
        try:
            q_ptr = q.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            docs_ptr = docs.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            out_scores = np.empty(count, dtype=np.float32)
            out_ptr = out_scores.ctypes.data_as(ctypes.POINTER(ctypes.c_float))

            _native_lib.fast_batch_cosine_similarity(q_ptr, docs_ptr, count, dim, out_ptr)
            return out_scores.tolist()
        except Exception as e:
            logger.debug(f"[C++ Native Core] fast_batch_cosine_similarity call failed: {e}")

    # NumPy fallback
    q_norm = float(np.linalg.norm(q))
    if q_norm < 1e-9:
        return [0.0] * count
    docs_norm = np.linalg.norm(docs, axis=1)
    dots = np.dot(docs, q)
    scores = dots / (docs_norm * q_norm + 1e-9)
    return scores.tolist()

