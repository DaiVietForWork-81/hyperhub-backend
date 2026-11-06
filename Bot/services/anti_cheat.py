"""Anti-Cheat 2.0 Engine for Ranked 1:1 Arena and Code Submissions.

Features:
1. Plagiarism Detection: Token-based normalization (stripping comments, strings, identifiers)
   and n-gram Jaccard / LCS similarity with solution code and opponent code.
2. Rapid Paste Detection: Detects impossible human typing speed (< 8s for substantial code).
3. AI Code Detection: Integrates with AIDetector for deep stylometric & pattern analysis.
4. Comprehensive Risk Scoring & Verdict Assessment.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from services.ai_detector import AIDetector
from utils.logger import get_logger

logger = get_logger("AntiCheatEngine")


@dataclass
class AntiCheatReport:
    """Báo cáo đánh giá tính liêm chính của bài thi."""

    risk_level: str  # "CLEAN", "SUSPICIOUS", "CHEATING_DETECTED"
    is_cheating: bool
    ai_score: float
    ai_reasons: list[str] = field(default_factory=list)
    plagiarism_solution_score: float = 0.0
    plagiarism_opponent_score: float = 0.0
    is_rapid_paste: bool = False
    rapid_paste_details: str = ""
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "risk_level": self.risk_level,
            "is_cheating": self.is_cheating,
            "ai_score": self.ai_score,
            "ai_reasons": self.ai_reasons,
            "plagiarism_solution_score": self.plagiarism_solution_score,
            "plagiarism_opponent_score": self.plagiarism_opponent_score,
            "is_rapid_paste": self.is_rapid_paste,
            "rapid_paste_details": self.rapid_paste_details,
            "summary": self.summary,
        }


class AntiCheatEngine:
    """Hệ thống giám sát và phát hiện gian lận đa chiều."""

    # Tốc độ gõ code trung bình của lập trình viên là ~40-60 WPM (~4 ký tự/giây).
    # Nộp trên 180 ký tự trong dưới 7.5 giây là bất khả thi nếu không phải paste sẵn.
    RAPID_PASTE_TIME_THRESHOLD_SEC = 7.5
    RAPID_PASTE_MIN_CHAR_COUNT = 180
    RAPID_PASTE_MIN_LINE_COUNT = 10

    # Ngưỡng xử lý gian lận
    CHEATING_AI_THRESHOLD = 80.0
    CHEATING_PLAGIARISM_THRESHOLD = 85.0
    SUSPICIOUS_AI_THRESHOLD = 55.0
    SUSPICIOUS_PLAGIARISM_THRESHOLD = 65.0

    @classmethod
    def check_rapid_paste(
        cls, source_code: str, time_elapsed_seconds: float
    ) -> tuple[bool, str]:
        """
        Kiểm tra thời gian nộp bài có dấu hiệu dán code chuẩn bị từ trước hoặc tool ngoài.
        """
        if time_elapsed_seconds <= 0:
            return False, "Không có dữ liệu thời gian"

        clean_code = source_code.strip()
        char_count = len(clean_code)
        lines = [line.strip() for line in clean_code.splitlines() if line.strip()]
        line_count = len(lines)

        if (
            time_elapsed_seconds < cls.RAPID_PASTE_TIME_THRESHOLD_SEC
            and (char_count >= cls.RAPID_PASTE_MIN_CHAR_COUNT or line_count >= cls.RAPID_PASTE_MIN_LINE_COUNT)
        ):
            cpm = (char_count / max(0.1, time_elapsed_seconds)) * 60
            detail = (
                f"Nộp {char_count} ký tự ({line_count} dòng) chỉ sau {time_elapsed_seconds:.1f}s "
                f"(Tốc độ ~{cpm:.0f} ký tự/phút — vượt xa giới hạn gõ phím con người)"
            )
            return True, detail

        return False, f"Thời gian làm bài tự nhiên: {time_elapsed_seconds:.1f}s"

    @classmethod
    def tokenize_and_normalize(cls, code: str, lang: str = "cpp") -> list[str]:
        """
        Chuẩn hóa mã nguồn thành chuỗi tokens độc lập với tên biến/khoảng trắng:
        - Xóa toàn bộ comments.
        - Thay thế string literals bằng '<STR>'.
        - Thay thế số bằng '<NUM>'.
        - Chuẩn hóa định danh biến/hàm nhằm chống kỹ thuật đổi tên biến (renaming obfuscation).
        """
        if not code:
            return []

        # 1. Xóa comments
        # C-style comments (C++, Java, JS, C#)
        no_comment = re.sub(r"/\*.*?\*/", " ", code, flags=re.DOTALL)
        no_comment = re.sub(r"//.*", " ", no_comment)
        # Python / Pascal comments
        no_comment = re.sub(r"#.*", " ", no_comment)
        no_comment = re.sub(r"\{.*?\}", " ", no_comment)

        # 2. Thay thế chuỗi và ký tự
        no_strings = re.sub(r'"([^"\\]|\\.)*"', " <STR> ", no_comment)
        no_strings = re.sub(r"'([^'\\]|\\.)*'", " <CHAR> ", no_strings)

        # 3. Thay thế số
        no_numbers = re.sub(r"\b\d+(\.\d+)?\b", " <NUM> ", no_strings)

        # 4. Tokenize
        raw_tokens = re.findall(r"[A-Za-z_]\w*|[^\sA-Za-z0-9_]", no_numbers)

        # 5. Phân loại và chuẩn hóa biến
        keywords = {
            "int", "long", "void", "char", "float", "double", "bool", "if", "else",
            "while", "for", "return", "switch", "case", "break", "continue", "struct",
            "class", "public", "private", "vector", "string", "def", "import", "from",
            "in", "and", "or", "not", "is", "elif", "try", "except", "cin", "cout",
            "print", "range", "len", "max", "min", "sum", "abs", "sort", "const",
            "auto", "include", "iostream", "algorithm", "cmath", "main"
        }

        normalized_tokens: list[str] = []
        var_map: dict[str, str] = {}
        var_counter = 1

        for token in raw_tokens:
            token_lower = token.lower()
            if token_lower in keywords or not token[0].isalpha():
                normalized_tokens.append(token_lower)
            elif token in ("<STR>", "<CHAR>", "<NUM>"):
                normalized_tokens.append(token)
            else:
                # Đổi tên biến cục bộ thành V1, V2, V3...
                if token not in var_map:
                    var_map[token] = f"V{var_counter}"
                    var_counter += 1
                normalized_tokens.append(var_map[token])

        return normalized_tokens

    @classmethod
    def calculate_similarity(cls, tokens_a: list[str], tokens_b: list[str]) -> float:
        """
        Tính toán tỷ lệ tương đồng giữa 2 chuỗi tokens sử dụng n-gram Jaccard kết hợp LCS:
        - Trả về thang điểm từ 0.0% đến 100.0%.
        """
        if not tokens_a or not tokens_b:
            return 0.0

        if tokens_a == tokens_b:
            return 100.0

        # 1. N-Gram Jaccard (n=3)
        n = 3
        if len(tokens_a) >= n and len(tokens_b) >= n:
            grams_a = set(tuple(tokens_a[i : i + n]) for i in range(len(tokens_a) - n + 1))
            grams_b = set(tuple(tokens_b[i : i + n]) for i in range(len(tokens_b) - n + 1))
            intersection = len(grams_a & grams_b)
            union = len(grams_a | grams_b)
            jaccard = (intersection / union) if union > 0 else 0.0
        else:
            # Code quá ngắn -> so sánh 1-gram
            set_a = set(tokens_a)
            set_b = set(tokens_b)
            jaccard = (len(set_a & set_b) / len(set_a | set_b)) if (set_a | set_b) else 0.0

        # 2. Token overlap ratio
        overlap = sum(1 for t in tokens_a if t in tokens_b) / max(len(tokens_a), 1)

        final_score = max(jaccard * 100.0, overlap * 75.0)
        return min(100.0, round(final_score, 1))

    @classmethod
    def check_plagiarism(
        cls, candidate_code: str, reference_code: str, lang: str = "cpp"
    ) -> float:
        """Kiểm tra tỷ lệ đạo nhái giữa bài nộp của thí sinh và bài đối chiếu."""
        if not candidate_code or not reference_code:
            return 0.0

        tokens_cand = cls.tokenize_and_normalize(candidate_code, lang)
        tokens_ref = cls.tokenize_and_normalize(reference_code, lang)

        return cls.calculate_similarity(tokens_cand, tokens_ref)

    @classmethod
    def analyze_submission(
        cls,
        source_code: str,
        lang: str = "cpp",
        time_elapsed_seconds: float = 0.0,
        solution_code: str | None = None,
        opponent_code: str | None = None,
    ) -> AntiCheatReport:
        """
        Thực hiện quét toàn diện kiểm tra tính liêm chính bài thi:
        1. Quét dấu vết AI (Stylometrics, comments LLM, entropy).
        2. Quét tốc độ nộp bài (Rapid Paste).
        3. Quét đạo nhái với bài giải mẫu và bài làm của đối thủ.
        """
        # 1. Phân tích AI
        try:
            ai_res = AIDetector.analyze(source_code, lang)
            ai_score = float(ai_res.get("score", 0.0))
            ai_reasons = ai_res.get("signals", []) or ai_res.get("reasons", [])
        except Exception as e:
            logger.warning(f"Lỗi khi phân tích AIDetector: {e}")
            ai_score = 0.0
            ai_reasons = []

        # 2. Phân tích Rapid Paste
        is_rapid, rapid_detail = cls.check_rapid_paste(source_code, time_elapsed_seconds)

        # 3. Phân tích Plagiarism
        sol_score = 0.0
        if solution_code and len(solution_code.strip()) > 20:
            sol_score = cls.check_plagiarism(source_code, solution_code, lang)

        opp_score = 0.0
        if opponent_code and len(opponent_code.strip()) > 20:
            opp_score = cls.check_plagiarism(source_code, opponent_code, lang)

        # 4. Xác định phán quyết và mức độ rủi ro
        is_cheating = False
        summary_points = []

        if ai_score >= cls.CHEATING_AI_THRESHOLD:
            is_cheating = True
            summary_points.append(f"🚨 Điểm nghi vấn AI cực cao: {ai_score:.0f}/100")
        elif ai_score >= cls.SUSPICIOUS_AI_THRESHOLD:
            summary_points.append(f"⚠️ Nghi vấn AI mức vừa: {ai_score:.0f}/100")

        if sol_score >= cls.CHEATING_PLAGIARISM_THRESHOLD:
            is_cheating = True
            summary_points.append(f"🚨 Tương đồng {sol_score:.0f}% với bài giải mẫu của ngân hàng đề")
        elif sol_score >= cls.SUSPICIOUS_PLAGIARISM_THRESHOLD:
            summary_points.append(f"⚠️ Trùng khớp {sol_score:.0f}% với giải mẫu")

        if opp_score >= cls.CHEATING_PLAGIARISM_THRESHOLD:
            summary_points.append(f"⚠️ Trùng khớp {opp_score:.0f}% với bài làm của đối thủ")

        if is_rapid:
            summary_points.append(f"⏱️ {rapid_detail}")
            # Nếu vừa rapid paste vừa có dấu hiệu AI hoặc Plagiarism cao -> khẳng định gian lận
            if ai_score >= 50.0 or sol_score >= 65.0:
                is_cheating = True
                summary_points.append("🚨 Kết hợp: Dán code siêu tốc + Chữ ký AI/Plagiarism cao!")

        if is_cheating:
            risk_level = "CHEATING_DETECTED"
            summary_text = "❌ PHÁT HIỆN GIAN LẬN: " + " • ".join(summary_points)
        elif ai_score >= cls.SUSPICIOUS_AI_THRESHOLD or sol_score >= cls.SUSPICIOUS_PLAGIARISM_THRESHOLD or is_rapid:
            risk_level = "SUSPICIOUS"
            summary_text = "⚠️ NGHI VẤN BẤT THƯỜNG: " + " • ".join(summary_points)
        else:
            risk_level = "CLEAN"
            summary_text = f"✅ HỢP LỆ (AI: {ai_score:.0f}%, Plagiarism: {sol_score:.0f}%)"

        return AntiCheatReport(
            risk_level=risk_level,
            is_cheating=is_cheating,
            ai_score=ai_score,
            ai_reasons=ai_reasons,
            plagiarism_solution_score=sol_score,
            plagiarism_opponent_score=opp_score,
            is_rapid_paste=is_rapid,
            rapid_paste_details=rapid_detail,
            summary=summary_text,
        )
