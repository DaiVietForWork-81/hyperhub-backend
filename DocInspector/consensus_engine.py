"""
3+1 Quorum Arbitration Consensus Engine for DocInspector & HyperHub.
"CƠ CHẾ HỘI ĐỒNG TRỌNG TÀI 3+1 — DỰ THẢO THẨM ĐỊNH ĐỀ THI"

Architecture:
- Lần Quét 1: Vùng Tiêu Đề & Hành Chính (Spatial Header & Administrative Zone)
- Lần Quét 2: Tần Suất Từ Vựng BM25 Toàn Thân Bài (Deep Lexical Distribution)
- Lần Quét 3: Cấu Trúc Đề, Cú Pháp Câu Hỏi & Ký Hiệu (Structural & Formula Analysis)
- Đánh giá Biểu quyết (Quorum Evaluation):
    + Nếu 3 lần quét đồng thuận 3/3: Xuất phán quyết tuyệt đối, không cần quét lần 4.
    + Nếu có 1 kết quả khác 2 lần kia (2 vs 1) hoặc phân mảnh:
      KÍCH HOẠT LẦN QUÉT 4: TRỌNG TÀI ĐỐI SOÁT CHUYÊN SÂU & LẬP DỰ THẢO THẨM ĐỊNH.
"""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from .models import (
    ExamTrackTier,
    GradeLevel,
    GRADE_LEVEL_VI_NAMES,
    Subject,
)
from .signatures import (
    RE_ADMIN_CONTRACT,
    RE_CURRICULUM_SERIES,
    RE_GRADE_10,
    RE_GRADE_11,
    RE_GRADE_12,
    RE_GRADE_6,
    RE_GRADE_7,
    RE_GRADE_8,
    RE_GRADE_9,
    RE_GRADE_MIDDLE,
    RE_GRADE_OLYMPIAD,
    RE_GRADE_PRIMARY,
    RE_GRADE_UNIVERSITY,
    RE_HSK_FEATURES,
    RE_IELTS_READING_PASSAGE,
    RE_IELTS_TFNG,
    RE_IELTS_HEADINGS,
    RE_IELTS_WRITING_TASKS,
    RE_JLPT_FEATURES,
    RE_LESSON_PLAN,
    RE_MCQ_OPTIONS,
    RE_MCQ_TRUE_FALSE,
    RE_MOET_PART1,
    RE_RUSSIAN_FEATURES,
    RE_TOEIC_PARTS,
    RE_TOPIK_FEATURES,
    SUBJECT_LEXICONS,
)


@dataclass
class ScanPassRecord:
    """Chi tiết kết quả của một lần quét độc lập."""
    pass_number: int                 # 1, 2, 3, hoặc 4
    pass_name: str                   # Tên hiển thị
    focus_zone: str                  # Khu vực khảo sát
    detected_subject: Subject
    subject_vi: str
    detected_grade: GradeLevel
    grade_vi: str
    confidence: float
    evidence_tokens: List[str] = field(default_factory=list)
    rationale: str = ""
    execution_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pass_number": self.pass_number,
            "pass_name": self.pass_name,
            "focus_zone": self.focus_zone,
            "detected_subject": self.detected_subject.name,
            "subject_vi": self.subject_vi,
            "detected_grade": self.detected_grade.name,
            "grade_vi": self.grade_vi,
            "confidence": round(self.confidence, 4),
            "evidence_tokens": self.evidence_tokens[:10],
            "rationale": self.rationale,
            "execution_time_ms": round(self.execution_time_ms, 2),
        }


@dataclass
class QuorumArbitrationResult:
    """Kết quả thẩm định của Hội đồng Trọng tài 3+1."""
    file_name: str
    is_unanimous: bool               # True nếu Lần 1 == Lần 2 == Lần 3
    passes_executed: int             # 3 (đồng thuận) hoặc 4 (khi kích hoạt trọng tài)
    scan_records: List[ScanPassRecord]

    # Phân tích biểu quyết
    votes_by_subject: Dict[str, int]
    has_conflict: bool
    conflict_summary: Optional[str]

    # Chi tiết Lần quét 4 (nếu kích hoạt)
    arbitration_triggered: bool
    arbitration_rationale: Optional[str]
    contrastive_suppressions: List[str]

    # Phán quyết cuối cùng
    final_subject: Subject
    final_subject_vi: str
    final_grade: GradeLevel
    final_grade_vi: str
    final_track: ExamTrackTier
    final_track_vi: str
    final_confidence: float
    final_verdict_rationale: str

    # Dự thảo thẩm định đầy đủ dạng Markdown và Dict
    draft_dossier_markdown: str
    draft_dossier_dict: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_name": self.file_name,
            "is_unanimous": self.is_unanimous,
            "passes_executed": self.passes_executed,
            "scans": [s.to_dict() for s in self.scan_records],
            "votes_by_subject": self.votes_by_subject,
            "has_conflict": self.has_conflict,
            "conflict_summary": self.conflict_summary,
            "arbitration_triggered": self.arbitration_triggered,
            "arbitration_rationale": self.arbitration_rationale,
            "contrastive_suppressions": self.contrastive_suppressions,
            "final_subject": self.final_subject.name,
            "final_subject_vi": self.final_subject_vi,
            "final_grade": self.final_grade.name,
            "final_grade_vi": self.final_grade_vi,
            "final_track": self.final_track.name,
            "final_track_vi": self.final_track_vi,
            "final_confidence": round(self.final_confidence, 4),
            "final_verdict_rationale": self.final_verdict_rationale,
            "draft_dossier_dict": self.draft_dossier_dict,
        }


# ============================================================================
# HELPER PATTERNS CHO CÁC LẦN QUÉT
# ============================================================================
RE_EXPLICIT_SUBJECT_HEADER = re.compile(
    r"(?i)(?:môn\s*(?:thi|học)?|bài\s*thi)\s*[:：\-–—]\s*([^\n\r,;()]{2,40})",
)

RE_COMPETITIVE_PROG_MARKERS = re.compile(
    r"(?i)(?:chuyên\s*tin|tin\s*học\s*(?:trẻ|olympic)|vnoi|icpc|lập\s*trình\s*thi\s*đấu|"
    r"file\s*vào\s*[:：]|file\s*ra\s*[:：]|thời\s*gian\s*chạy\s*[:：]\s*\d+|giới\s*hạn\s*bộ\s*nhớ\s*[:：]|"
    r"subtask\s*\d+|testcase|\.cpp|\.pas|\.py\b|stdin|stdout)",
)

RE_MATH_FORMULA_MARKERS = re.compile(
    r"(?:\\(?:frac|sqrt|int|lim|sum|alpha|beta|gamma|Delta|vec)|"
    r"f\([xyt]\)|y\s*=\s*ax|x\^2|\u221a|\u222b|\u2264|\u2265|\u2260|\u2208|\u2282)",
)

RE_CHEM_FORMULA_MARKERS = re.compile(
    r"(?:\b(?:[A-Z][a-z]\d*|[A-Z]\d+)(?:[A-Z][a-z]?\d*)+\b|"
    r"\b(?:H2SO4|HCl|NaOH|HNO3|CaCO3|Fe2O3|CuSO4|Al2O3|CO2|H2O|CH4|C2H5OH|C6H12O6|NaCl)\b|"
    r"\b(?:mol|gam/mol|pH|axit|bazơ|hiđrocacbon|este|amino\s*axit|kim\s*loại\s*kiềm)\b|"
    r"->|\u2192|\u21cc)",
)

RE_PHYSICS_FORMULA_MARKERS = re.compile(
    r"(?:\b(?:v\s*=\s*v0|F\s*=\s*ma|W\s*=\s*1/2|I\s*=\s*U/R|omega|rad/s|m/s2|N/m|kWh|Joule|Henry|Tesla|Ohm)\b|"
    r"dao\s*động\s*điều\s*hòa|con\s*lắc\s*lò\s*xo|quang\s*phổ|hạt\s*nhân)",
)


class QuorumArbitrationEngine:
    """
    Hội đồng Trọng tài 3+1 Độc lập không dùng AI.
    Thực hiện 3 lần quét chuyên biệt. Nếu phát hiện bất đồng (2 vs 1 hoặc phân rã),
    tự động kích hoạt lần quét thứ 4 để phân xử trọng tài và xuất Dự thảo thẩm định.
    """

    @classmethod
    def inspect(
        cls,
        text: str,
        file_name: str = "",
        pre_extracted_pass1: Optional[Any] = None,
        pre_extracted_pass2: Optional[Any] = None,
    ) -> QuorumArbitrationResult:
        """
        Khởi chạy quy trình thẩm định 3+1.
        """
        # =====================================================================
        # LẦN QUÉT 1: VÙNG TIÊU ĐỀ & HÀNH CHÍNH (Spatial Header Zone: 0-1500 ký tự)
        # =====================================================================
        t1_start = time.perf_counter()
        scan1 = cls._run_pass1_spatial_header(text, file_name)
        scan1.execution_time_ms = (time.perf_counter() - t1_start) * 1000.0

        # =====================================================================
        # LẦN QUÉT 2: TẦN SUẤT TỪ VỰNG BM25 TOÀN THÂN BÀI (Deep Lexical Scan)
        # =====================================================================
        t2_start = time.perf_counter()
        scan2 = cls._run_pass2_lexical_bm25(text, file_name)
        scan2.execution_time_ms = (time.perf_counter() - t2_start) * 1000.0

        # =====================================================================
        # LẦN QUÉT 3: CẤU TRÚC ĐỀ, CÚ PHÁP CÂU HỎI & KÝ HIỆU (Structural Analysis)
        # =====================================================================
        t3_start = time.perf_counter()
        scan3 = cls._run_pass3_structural_formulas(text, file_name)
        scan3.execution_time_ms = (time.perf_counter() - t3_start) * 1000.0

        scans = [scan1, scan2, scan3]

        # =====================================================================
        # ĐÁNH GIÁ BIỂU QUYẾT HỘI ĐỒNG (Quorum Evaluation)
        # =====================================================================
        s1 = scan1.detected_subject
        s2 = scan2.detected_subject
        s3 = scan3.detected_subject

        # Đếm phiếu theo môn học
        votes: Dict[str, int] = {}
        for s in (s1, s2, s3):
            votes[s.name] = votes.get(s.name, 0) + 1

        is_unanimous = (s1 == s2 == s3)
        arbitration_triggered = False
        scan4: Optional[ScanPassRecord] = None
        arbitration_rationale: Optional[str] = None
        contrastive_suppressions: List[str] = []

        if is_unanimous:
            # === KỊCH BẢN A: ĐỒNG THUẬN TUYỆT ĐỐI (3/3) ===
            final_subject = s1
            final_grade = scan1.detected_grade if scan1.detected_grade != GradeLevel.UNKNOWN else scan2.detected_grade
            final_confidence = 1.0  # 100% Đồng thuận
            conflict_summary = None
            final_verdict_rationale = (
                f"ĐỒNG THUẬN TUYỆT ĐỐI 3/3: Cả 3 lần quét độc lập (Vùng Tiêu Đề, "
                f"Tần Suất Từ Vựng BM25, và Cấu Trúc Ký Hiệu) đều xác định chính xác là môn {final_subject.value}."
            )
        else:
            # === KỊCH BẢN B: CÓ BẤT ĐỒNG (2 vs 1 hoặc 1 vs 1 vs 1) ===
            # Yêu cầu: "nếu cả 3 lần quét có 1 kết quả khác 2 lần đấy, bot sẽ quét thêm 1 lần nx"
            arbitration_triggered = True
            conflict_summary = (
                f"Phát hiện bất đồng biểu quyết giữa các lần quét: "
                f"Lần 1 ({scan1.subject_vi}), Lần 2 ({scan2.subject_vi}), Lần 3 ({scan3.subject_vi}). "
                f"Hệ thống tự động kích hoạt Lần Quét 4 Trọng tài Đối soát Chuyên sâu."
            )

            # Khởi chạy Lần quét 4: Trọng tài Đối soát
            t4_start = time.perf_counter()
            scan4, arbitration_rationale, contrastive_suppressions = cls._run_pass4_arbitration(
                text=text,
                file_name=file_name,
                scan1=scan1,
                scan2=scan2,
                scan3=scan3,
            )
            scan4.execution_time_ms = (time.perf_counter() - t4_start) * 1000.0
            scans.append(scan4)

            # Cập nhật số phiếu với Lần 4
            votes[scan4.detected_subject.name] = votes.get(scan4.detected_subject.name, 0) + 1

            # Phán quyết trọng tài từ Lần 4 làm chủ đạo
            final_subject = scan4.detected_subject
            final_grade = scan4.detected_grade
            final_confidence = scan4.confidence
            final_verdict_rationale = (
                f"PHÁN QUYẾT HỘI ĐỒNG TRỌNG TÀI 3+1: Sau 4 lần đối soát chuyên sâu và áp dụng ma trận "
                f"triệt tiêu tương phản, Hội đồng kết luận đề thi thuộc môn {final_subject.value}. "
                f"Lý do: {arbitration_rationale}"
            )

        # Xác định Phân loại đề (Track: Đại trà / Chuyên / HSG)
        final_track, final_track_vi = cls._detect_exam_track(text, file_name, final_subject)

        # Xây dựng Dự thảo Thẩm định Đề thi (Draft Dossier)
        draft_dossier_dict = {
            "file_name": file_name or "tai_lieu_de_thi",
            "is_unanimous": is_unanimous,
            "total_passes": len(scans),
            "votes": votes,
            "scans": [s.to_dict() for s in scans],
            "conflict_summary": conflict_summary,
            "arbitration_triggered": arbitration_triggered,
            "arbitration_rationale": arbitration_rationale,
            "contrastive_suppressions": contrastive_suppressions,
            "verdict": {
                "subject": final_subject.name,
                "subject_vi": final_subject.value,
                "grade": final_grade.name,
                "grade_vi": GRADE_LEVEL_VI_NAMES.get(final_grade, "Không xác định"),
                "track": final_track.name,
                "track_vi": final_track_vi,
                "confidence": round(final_confidence, 4),
                "rationale": final_verdict_rationale,
            },
        }

        draft_markdown = cls._render_draft_dossier_markdown(
            file_name=file_name,
            is_unanimous=is_unanimous,
            scans=scans,
            votes=votes,
            conflict_summary=conflict_summary,
            arbitration_rationale=arbitration_rationale,
            contrastive_suppressions=contrastive_suppressions,
            final_subject=final_subject,
            final_grade=final_grade,
            final_track_vi=final_track_vi,
            final_confidence=final_confidence,
            final_rationale=final_verdict_rationale,
        )

        return QuorumArbitrationResult(
            file_name=file_name or "de_thi",
            is_unanimous=is_unanimous,
            passes_executed=len(scans),
            scan_records=scans,
            votes_by_subject=votes,
            has_conflict=not is_unanimous,
            conflict_summary=conflict_summary,
            arbitration_triggered=arbitration_triggered,
            arbitration_rationale=arbitration_rationale,
            contrastive_suppressions=contrastive_suppressions,
            final_subject=final_subject,
            final_subject_vi=final_subject.value,
            final_grade=final_grade,
            final_grade_vi=GRADE_LEVEL_VI_NAMES.get(final_grade, "Không xác định"),
            final_track=final_track,
            final_track_vi=final_track_vi,
            final_confidence=final_confidence,
            final_verdict_rationale=final_verdict_rationale,
            draft_dossier_markdown=draft_markdown,
            draft_dossier_dict=draft_dossier_dict,
        )

    # =========================================================================
    # LẦN 1: QUÉT VÙNG TIÊU ĐỀ & HÀNH CHÍNH (SPATIAL HEADER PASS)
    # =========================================================================
    @classmethod
    def _run_pass1_spatial_header(cls, text: str, file_name: str) -> ScanPassRecord:
        header_text = text[:1500] if text else ""
        fn_clean = (file_name or "").lower().replace("_", " ").replace("-", " ")
        combined_header = f"{fn_clean}\n{header_text}"

        evidence: List[str] = []
        detected_subject = Subject.GENERAL
        confidence = 0.60
        rationale = "Quét vùng đầu trang (0-1500 ký tự) và tên tệp."

        # 0. Kiểm tra văn bản hành chính / hợp đồng pháp lý
        if len(RE_ADMIN_CONTRACT.findall(combined_header)) >= 2 or any(k in combined_header.lower() for k in ["hợp đồng", "cộng hòa xã hội chủ nghĩa việt nam"]):
            detected_subject = Subject.NON_ACADEMIC
            confidence = 0.99
            evidence = ["Văn bản hành chính / Hợp đồng kinh tế"]
            rationale = "Tiêu đề và đầu trang chứa tiêu ngữ quốc gia hoặc tên văn bản hợp đồng."
        else:
            # 1. Kiểm tra tiêu đề tường minh MÔN: ...
            header_match = RE_EXPLICIT_SUBJECT_HEADER.search(header_text)
            if header_match:
                raw_subj = header_match.group(1).strip().lower()
                subject_explicit_map = {
                    "toán": Subject.MATHEMATICS,
                    "toán học": Subject.MATHEMATICS,
                    "vật lí": Subject.PHYSICS,
                    "vật lý": Subject.PHYSICS,
                    "hóa học": Subject.CHEMISTRY,
                    "hóa": Subject.CHEMISTRY,
                    "sinh học": Subject.BIOLOGY,
                    "sinh": Subject.BIOLOGY,
                    "tin học": Subject.INFORMATICS,
                    "tin": Subject.INFORMATICS,
                    "ngữ văn": Subject.LITERATURE,
                    "văn": Subject.LITERATURE,
                    "lịch sử": Subject.HISTORY,
                    "sử": Subject.HISTORY,
                    "địa lí": Subject.GEOGRAPHY,
                    "địa lý": Subject.GEOGRAPHY,
                    "tiếng anh": Subject.ENGLISH,
                    "khoa học tự nhiên": Subject.NATURAL_SCIENCE,
                    "khtn": Subject.NATURAL_SCIENCE,
                    "giáo dục công dân": Subject.CIVIC_EDUCATION,
                    "gdcd": Subject.CIVIC_EDUCATION,
                }
                for kw, subj in subject_explicit_map.items():
                    if re.search(r"\b" + re.escape(kw) + r"\b", raw_subj):
                        detected_subject = subj
                        confidence = 0.96
                        evidence.append(f"Mục tiêu đề: '{header_match.group(0).strip()}'")
                        rationale = f"Phát hiện trường tiêu đề môn học chính thức: '{header_match.group(0).strip()}'."
                        break

        # 2. Nếu chưa tìm thấy, tính điểm từ vựng tập trung riêng ở vùng Header (x3.5 weight)
        if detected_subject == Subject.GENERAL:
            best_score = 0.0
            best_subj = Subject.GENERAL
            best_tokens: List[str] = []

            for subj_name, lexicon in SUBJECT_LEXICONS.items():
                s_score = 0.0
                s_tokens = []
                for kw in lexicon:
                    if kw == "đồng" and re.search(r"(?i)\b(?:\d+[\d.,\s]*(?:triệu|nghìn|tỷ|k)?\s*đồng|hợp\s*đồng|đồng\s*ý)\b", combined_header):
                        continue
                    patt = r"(?i)\b" + re.escape(kw) + r"\b"
                    m = len(re.findall(patt, combined_header))
                    if m > 0:
                        s_score += m * 3.5
                        s_tokens.append(kw)
                if s_score > best_score:
                    best_score = s_score
                    best_subj = Subject[subj_name]
                    best_tokens = s_tokens

            if best_score >= 7.0:
                detected_subject = best_subj
                confidence = min(0.92, 0.65 + best_score * 0.02)
                evidence = best_tokens[:6]
                rationale = f"Tín hiệu từ khóa đầu trang mạnh (điểm Header: {best_score:.1f})."

        # Khối lớp theo Header
        grade = cls._detect_grade(combined_header)

        return ScanPassRecord(
            pass_number=1,
            pass_name="Lần Quét 1: Vùng Tiêu Đề & Hành Chính",
            focus_zone="Spatial Header Zone (0-1500 chars) & Filename",
            detected_subject=detected_subject,
            subject_vi=detected_subject.value,
            detected_grade=grade,
            grade_vi=GRADE_LEVEL_VI_NAMES.get(grade, "Không xác định"),
            confidence=confidence,
            evidence_tokens=evidence,
            rationale=rationale,
        )

    # =========================================================================
    # LẦN 2: TẦN SUẤT TỪ VỰNG BM25 TOÀN THÂN BÀI (DEEP LEXICAL SCAN)
    # =========================================================================
    @classmethod
    def _run_pass2_lexical_bm25(cls, text: str, file_name: str) -> ScanPassRecord:
        text_lower = text.lower() if text else ""
        doc_len = len(text_lower.split())
        avg_len = 1200.0
        k1 = 1.2
        b = 0.75

        subject_bm25_scores: Dict[str, float] = {}
        subject_matched_terms: Dict[str, List[str]] = {}

        for subj_name, lexicon in SUBJECT_LEXICONS.items():
            score = 0.0
            matched = []
            for term in lexicon:
                patt = r"\b" + re.escape(term) + r"\b"
                tf = len(re.findall(patt, text_lower))
                if tf > 0:
                    # Non-linear BM25 saturation
                    term_score = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * (doc_len / avg_len)))
                    score += term_score
                    matched.append(f"{term} ({tf})")
            subject_bm25_scores[subj_name] = score
            subject_matched_terms[subj_name] = matched

        sorted_subjs = sorted(subject_bm25_scores.items(), key=lambda x: x[1], reverse=True)
        top_name, top_score = sorted_subjs[0]

        top_subject = Subject[top_name] if top_score >= 3.0 else Subject.GENERAL
        evidence = subject_matched_terms.get(top_name, [])[:8]

        # Độ tin cậy theo phân vị BM25
        if top_score >= 25.0:
            confidence = 0.99
        elif top_score >= 12.0:
            confidence = 0.94
        elif top_score >= 5.0:
            confidence = 0.85
        else:
            confidence = 0.60

        grade = cls._detect_grade(text_lower)

        return ScanPassRecord(
            pass_number=2,
            pass_name="Lần Quét 2: Tần Suất Từ Vựng BM25",
            focus_zone="Full Document Body (BM25 Non-linear Lexical Saturation)",
            detected_subject=top_subject,
            subject_vi=top_subject.value,
            detected_grade=grade,
            grade_vi=GRADE_LEVEL_VI_NAMES.get(grade, "Không xác định"),
            confidence=confidence,
            evidence_tokens=evidence,
            rationale=f"Tổng điểm BM25 thân bài: {top_score:.1f} điểm, mật độ từ vựng chuyên ngành dẫn đầu.",
        )

    # =========================================================================
    # LẦN 3: CẤU TRÚC ĐỀ, CÚ PHÁP CÂU HỎI & KÝ HIỆU (STRUCTURAL ANALYSIS)
    # =========================================================================
    @classmethod
    def _run_pass3_structural_formulas(cls, text: str, file_name: str) -> ScanPassRecord:
        text_lower = text.lower() if text else ""
        evidence: List[str] = []
        detected_subject = Subject.GENERAL
        confidence = 0.70
        rationale = "Phân tích cấu trúc câu hỏi, ký hiệu và biểu thức toán/hóa/tin."

        # 1. Cú pháp Tin học thi đấu / Lập trình (ICPC, VNOI, time limit, memory limit, .cpp)
        comp_matches = RE_COMPETITIVE_PROG_MARKERS.findall(text)
        if len(comp_matches) >= 2 or any(k in text_lower for k in ["#include <", "cin >>", "cout <<", "std::", "int main()"]):
            detected_subject = Subject.INFORMATICS
            confidence = 0.98
            evidence = [f"Dấu hiệu cấu trúc Tin học: {m}" for m in comp_matches[:5]]
            rationale = "Đề thi mang cấu trúc chuẩn Lập trình thi đấu / Chuyên Tin (Time/Memory limits, I/O files)."

        # 2. Ký hiệu & Công thức Hóa học (H2SO4, NaOH, mol, ->, pH, phương trình phản ứng)
        elif len(RE_CHEM_FORMULA_MARKERS.findall(text)) >= 4:
            detected_subject = Subject.CHEMISTRY
            confidence = 0.97
            evidence = list(set(RE_CHEM_FORMULA_MARKERS.findall(text)))[:6]
            rationale = "Phát hiện hệ thống công thức phân tử, phản ứng hóa học và đơn vị mol đặc trưng."

        # 3. Ký hiệu Toán học chuyên sâu (\int, \lim, \sqrt{}, f(x), oxyz, tích phân)
        elif len(RE_MATH_FORMULA_MARKERS.findall(text)) >= 4:
            detected_subject = Subject.MATHEMATICS
            confidence = 0.97
            evidence = list(set(RE_MATH_FORMULA_MARKERS.findall(text)))[:6]
            rationale = "Xuất hiện dày đặc các ký hiệu giải tích, hình học không gian, đạo hàm hoặc tích phân."

        # 4. Ký hiệu Vật lý (dao động điều hòa, con lắc, v=v0+at, rad/s)
        elif len(RE_PHYSICS_FORMULA_MARKERS.findall(text)) >= 3:
            detected_subject = Subject.PHYSICS
            confidence = 0.95
            evidence = list(set(RE_PHYSICS_FORMULA_MARKERS.findall(text)))[:5]
            rationale = "Cấu trúc câu hỏi chứa đại lượng vật lý, phương trình chuyển động hoặc mạch điện xoay chiều."

        # 5. Tiếng Anh / Ngoại ngữ quốc tế (IELTS, TOEIC, JLPT, HSK)
        elif (RE_IELTS_READING_PASSAGE.search(text) or RE_IELTS_TFNG.search(text) or RE_IELTS_HEADINGS.search(text)) or RE_TOEIC_PARTS.search(text):
            detected_subject = Subject.ENGLISH
            confidence = 0.98
            evidence = ["IELTS/TOEIC Structural Features (Reading Passages, Cloze, TFNG)"]
            rationale = "Cấu trúc bài kiểm tra kỹ năng Tiếng Anh chuẩn khảo thí quốc tế."
        elif RE_JLPT_FEATURES.search(text):
            detected_subject = Subject.JAPANESE
            confidence = 0.99
            evidence = ["JLPT Script Patterns (Kanji / Hiragana / Katakana)"]
            rationale = "Cấu trúc đề kiểm tra năng lực Nhật ngữ JLPT."
        elif RE_HSK_FEATURES.search(text):
            detected_subject = Subject.CHINESE
            confidence = 0.99
            evidence = ["HSK Script Patterns (Hán tự Giản thể/Phồn thể)"]
            rationale = "Cấu trúc đề kiểm tra năng lực Hán ngữ HSK."

        # 6. Văn bản hành chính / Hợp đồng
        elif len(RE_ADMIN_CONTRACT.findall(text)) >= 2:
            detected_subject = Subject.NON_ACADEMIC
            confidence = 0.99
            evidence = list(set(RE_ADMIN_CONTRACT.findall(text)))[:4]
            rationale = "Cấu trúc hợp đồng kinh tế, văn bản quy phạm hành chính, không phải đề thi học tập."

        # Fallback: Quét nhanh từ vựng
        if detected_subject == Subject.GENERAL:
            scan2_quick = cls._run_pass2_lexical_bm25(text, file_name)
            detected_subject = scan2_quick.detected_subject
            confidence = 0.75
            evidence = scan2_quick.evidence_tokens[:4]
            rationale = "Cấu trúc đề hỗn hợp hoặc tự luận/trắc nghiệm phổ thông."

        grade = cls._detect_grade(text_lower)

        return ScanPassRecord(
            pass_number=3,
            pass_name="Lần Quét 3: Cấu Trúc, Cú Pháp & Ký Hiệu",
            focus_zone="Structural Syntax, Math/Chem/Code Notation & Question Framework",
            detected_subject=detected_subject,
            subject_vi=detected_subject.value,
            detected_grade=grade,
            grade_vi=GRADE_LEVEL_VI_NAMES.get(grade, "Không xác định"),
            confidence=confidence,
            evidence_tokens=evidence,
            rationale=rationale,
        )

    # =========================================================================
    # LẦN 4: TRỌNG TÀI ĐỐI SOÁT CHUYÊN SÂU (ARBITRATION MATRIX PASS)
    # =========================================================================
    @classmethod
    def _run_pass4_arbitration(
        cls,
        text: str,
        file_name: str,
        scan1: ScanPassRecord,
        scan2: ScanPassRecord,
        scan3: ScanPassRecord,
    ) -> Tuple[ScanPassRecord, str, List[str]]:
        """
        Lần quét thứ 4: Chỉ chạy khi có bất đồng biểu quyết giữa Lần 1, 2 và 3.
        Áp dụng Ma trận Triệt tiêu Tương phản (Contrastive Suppression Matrix)
        và phân xử quyền ưu tiên chứng cứ cao nhất.
        """
        text_lower = text.lower() if text else ""
        fn_lower = (file_name or "").lower()
        contrastive_suppressions: List[str] = []

        candidate_subjects = {scan1.detected_subject, scan2.detected_subject, scan3.detected_subject}

        # --- QUY TẮC PHÂN XỬ 1: TIN HỌC vs TOÁN HỌC ---
        # Bài thi HSG Tin học thường chứa nhiều từ 'Toán', 'dãy số', 'đồ thị', 'ma trận'.
        if Subject.INFORMATICS in candidate_subjects and Subject.MATHEMATICS in candidate_subjects:
            has_comp_prog = bool(RE_COMPETITIVE_PROG_MARKERS.search(text)) or any(
                k in text_lower for k in ["giới hạn thời gian", "bộ nhớ", "subtask", "test case", "stdin", "stdout", ".cpp", "pascal", "python"]
            ) or any(k in fn_lower for k in ["tin", "lap_trinh", "thuattoan", "vnoi", "icpc", ".cpp", ".py"])
            if has_comp_prog:
                contrastive_suppressions.append(
                    "TRIỆT TIÊU TOÁN HỌC: Phát hiện các ràng buộc thuật toán lập trình (Time/Memory limits, I/O files). "
                    "Các thuật ngữ toán học trong đề chỉ đóng vai trò bài toán giải thuật cho Tin học."
                )
                rationale = (
                    "Hội đồng Trọng tài xác định: Các từ khóa Toán học xuất hiện do bài toán lập trình "
                    "yêu cầu tối ưu thuật toán số học. Ràng buộc file/time limit khẳng định 100% đề thi Chuyên Tin."
                )
                scan4_rec = ScanPassRecord(
                    pass_number=4,
                    pass_name="Lần Quét 4: Trọng Tài Đối Soát Tương Phản",
                    focus_zone="Contrastive Matrix: Informatics vs Mathematics Disambiguation",
                    detected_subject=Subject.INFORMATICS,
                    subject_vi=Subject.INFORMATICS.value,
                    detected_grade=scan1.detected_grade if scan1.detected_grade != GradeLevel.UNKNOWN else scan2.detected_grade,
                    grade_vi=GRADE_LEVEL_VI_NAMES.get(scan1.detected_grade, "Không xác định"),
                    confidence=1.0,
                    evidence_tokens=["Competitive Programming Override", "Time/Memory Constraints", "Algorithmic Task"],
                    rationale=rationale,
                )
                return scan4_rec, rationale, contrastive_suppressions

        # --- QUY TẮC PHÂN XỬ 2: HÓA HỌC vs VĂN BẢN HÀNH CHÍNH / TIỀN TỆ ---
        # Từ 'đồng' trong hợp đồng (tiền VNĐ) bị nhầm với nguyên tố Đồng (Cu)
        if Subject.CHEMISTRY in candidate_subjects or Subject.NON_ACADEMIC in candidate_subjects:
            has_currency = bool(re.search(r"(?i)\b\d+[\d.,\s]*(?:triệu|nghìn|tỷ|k)?\s*đồng\b", text)) or "hợp đồng" in text_lower
            has_chemical_cu = bool(re.search(r"(?i)\b(?:oxit|muối|hóa trị|dung dịch|kim loại)\s*đồng\b|\bCu\b", text))
            if has_currency and not has_chemical_cu:
                contrastive_suppressions.append(
                    "TRIỆT TIÊU HÓA HỌC: Từ 'đồng' trong văn bản là đơn vị tiền tệ Việt Nam Đồng (VNĐ) "
                    "hoặc cụm từ 'hợp đồng', không phải nguyên tố hóa học Copper (Cu)."
                )
                rationale = "Từ 'đồng' xuất hiện trong ngữ cảnh tài chính/tiền tệ, loại trừ hoàn toàn môn Hóa học."
                if "hợp đồng" in text_lower or len(RE_ADMIN_CONTRACT.findall(text)) >= 1:
                    chosen_subj = Subject.NON_ACADEMIC
                else:
                    chosen_subj = scan1.detected_subject if scan1.detected_subject != Subject.CHEMISTRY else scan2.detected_subject
                    if chosen_subj == Subject.CHEMISTRY:
                        chosen_subj = Subject.NON_ACADEMIC
                scan4_rec = ScanPassRecord(
                    pass_number=4,
                    pass_name="Lần Quét 4: Trọng Tài Đối Soát Tương Phản",
                    focus_zone="Contrastive Matrix: Chemical Copper vs Currency Dong Disambiguation",
                    detected_subject=chosen_subj,
                    subject_vi=chosen_subj.value,
                    detected_grade=GradeLevel.UNKNOWN,
                    grade_vi="Không xác định",
                    confidence=0.98,
                    evidence_tokens=["Currency Suppression", "Non-Academic / Financial Context"],
                    rationale=rationale,
                )
                return scan4_rec, rationale, contrastive_suppressions

        # --- QUY TẮC PHÂN XỬ 3: KHOA HỌC TỰ NHIÊN (KHTN) vs LÝ/HÓA/SINH RIÊNG LẺ ---
        # Khối 6, 7, 8, 9 (THCS) thuộc chương trình GDPT 2018 là môn KHTN tích hợp
        if any(s in candidate_subjects for s in [Subject.NATURAL_SCIENCE, Subject.PHYSICS, Subject.CHEMISTRY, Subject.BIOLOGY]):
            grade = scan1.detected_grade if scan1.detected_grade != GradeLevel.UNKNOWN else scan2.detected_grade
            is_thcs = grade in (GradeLevel.GRADE_6, GradeLevel.GRADE_7, GradeLevel.GRADE_8, GradeLevel.GRADE_9, GradeLevel.MIDDLE_SCHOOL)
            if is_thcs and "khoa học tự nhiên" in text_lower or "khtn" in text_lower:
                contrastive_suppressions.append(
                    "ĐỒNG BỘ CHUẨN GDPT 2018: Đề thi cấp THCS (Lớp 6-9) tích hợp liên môn Vật lý, Hóa học, Sinh học "
                    "thành môn Khoa học tự nhiên (KHTN)."
                )
                rationale = "Đề thi cấp THCS chuẩn GDPT 2018 môn Khoa học tự nhiên (KHTN)."
                scan4_rec = ScanPassRecord(
                    pass_number=4,
                    pass_name="Lần Quét 4: Trọng Tài Đối Soát Tương Phản",
                    focus_zone="Contrastive Matrix: GDPT 2018 Integrated Natural Science",
                    detected_subject=Subject.NATURAL_SCIENCE,
                    subject_vi=Subject.NATURAL_SCIENCE.value,
                    detected_grade=grade,
                    grade_vi=GRADE_LEVEL_VI_NAMES.get(grade, "Không xác định"),
                    confidence=0.98,
                    evidence_tokens=["GDPT 2018 Standard", "THCS Integrated Science"],
                    rationale=rationale,
                )
                return scan4_rec, rationale, contrastive_suppressions

        # --- QUY TẮC PHÂN XỬ 4: ĐA SỐ BIỂU QUYẾT CÓ TRỌNG SỐ ---
        # Nếu 2 lần quét cùng cho kết quả X, và Lần 3 cho Y:
        # Kiểm tra xem X có độ tin cậy kết hợp áp đảo Y không.
        pass_votes: Dict[Subject, float] = {}
        # Trọng số: Pass 1 (35%), Pass 2 (40%), Pass 3 (35%)
        weights = [0.35, 0.40, 0.35]
        for s_rec, w in zip([scan1, scan2, scan3], weights):
            pass_votes[s_rec.detected_subject] = pass_votes.get(s_rec.detected_subject, 0.0) + (s_rec.confidence * w)

        best_subj, best_weighted_score = max(pass_votes.items(), key=lambda x: x[1])
        rationale = (
            f"Phân xử bằng tổng trọng số biểu quyết đa tầng ({best_weighted_score:.2f} điểm). "
            f"Môn {best_subj.value} nhận được sự đồng thuận áp đảo từ các phân đoạn khảo sát độc lập."
        )

        scan4_rec = ScanPassRecord(
            pass_number=4,
            pass_name="Lần Quét 4: Trọng Tài Đối Soát Tương Phản",
            focus_zone="Multi-Zone Weighted Arbitration Council",
            detected_subject=best_subj,
            subject_vi=best_subj.value,
            detected_grade=scan1.detected_grade if scan1.detected_grade != GradeLevel.UNKNOWN else scan2.detected_grade,
            grade_vi=GRADE_LEVEL_VI_NAMES.get(scan1.detected_grade, "Không xác định"),
            confidence=min(0.99, best_weighted_score + 0.15),
            evidence_tokens=[f"Weighted Score: {best_weighted_score:.2f}", f"Dispute Resolved to {best_subj.name}"],
            rationale=rationale,
        )
        return scan4_rec, rationale, contrastive_suppressions

    # =========================================================================
    # TIỆN ÍCH PHỤ TRỢ: NHẬN DIỆN KHỐI LỚP & PHÂN LOẠI ĐỀ
    # =========================================================================
    @classmethod
    def _detect_grade(cls, text: str) -> GradeLevel:
        """Nhận diện khối lớp chính xác."""
        if not text:
            return GradeLevel.UNKNOWN
        t = text.lower()
        if RE_GRADE_OLYMPIAD.search(t):
            return GradeLevel.OLYMPIAD_GIFTED
        if RE_GRADE_12.search(t):
            return GradeLevel.GRADE_12
        if RE_GRADE_11.search(t):
            return GradeLevel.GRADE_11
        if RE_GRADE_10.search(t):
            return GradeLevel.GRADE_10
        if RE_GRADE_9.search(t):
            return GradeLevel.GRADE_9
        if RE_GRADE_8.search(t):
            return GradeLevel.GRADE_8
        if RE_GRADE_7.search(t):
            return GradeLevel.GRADE_7
        if RE_GRADE_6.search(t):
            return GradeLevel.GRADE_6
        if RE_GRADE_MIDDLE.search(t):
            return GradeLevel.MIDDLE_SCHOOL
        if RE_GRADE_PRIMARY.search(t):
            return GradeLevel.PRIMARY_SCHOOL
        if RE_GRADE_UNIVERSITY.search(t):
            return GradeLevel.UNIVERSITY
        return GradeLevel.UNKNOWN

    @classmethod
    def _detect_exam_track(cls, text: str, file_name: str, subject: Subject) -> Tuple[ExamTrackTier, str]:
        """Phân loại đề: Chuyên / HSG / Đại trà."""
        combined = f"{file_name} {text[:2000]}".lower()

        if any(k in combined for k in ["học sinh giỏi", "hsg", "chọn đội tuyển", "quốc gia", "vnoi", "icpc"]):
            return ExamTrackTier.HSG, "Đề thi Học sinh giỏi (HSG)"
        if any(k in combined for k in ["chuyên", "thpt chuyên", "olympic", "chọn học sinh", "năng khiếu"]):
            return ExamTrackTier.CHUYEN, "Đề thi Chuyên / Olympic"
        if any(k in combined for k in ["tốt nghiệp thpt", "thpt quốc gia", "đgnl", "đánh giá năng lực"]):
            return ExamTrackTier.THUONG, "Đề thi Tốt nghiệp THPT / ĐGNL"
        if any(k in combined for k in ["giữa kỳ", "học kỳ", "cuối kỳ", "1 tiết", "45 phút"]):
            return ExamTrackTier.THUONG, "Đề thi Học kỳ / Kiểm tra định kỳ"

        return ExamTrackTier.THUONG, "Đề thi Phổ thông (Đại trà)"

    # =========================================================================
    # RENDER BÁO CÁO DỰ THẢO THẨM ĐỊNH (MARKDOWN)
    # =========================================================================
    @classmethod
    def _render_draft_dossier_markdown(
        cls,
        file_name: str,
        is_unanimous: bool,
        scans: List[ScanPassRecord],
        votes: Dict[str, int],
        conflict_summary: Optional[str],
        arbitration_rationale: Optional[str],
        contrastive_suppressions: List[str],
        final_subject: Subject,
        final_grade: GradeLevel,
        final_track_vi: str,
        final_confidence: float,
        final_rationale: str,
    ) -> str:
        badge = "🟢 ĐỒNG THUẬN TUYỆT ĐỐI (3/3)" if is_unanimous else "⚖️ HỘI ĐỒNG TRỌNG TÀI ĐỐI SOÁT (3+1)"
        grade_str = GRADE_LEVEL_VI_NAMES.get(final_grade, "Chung")

        md = []
        md.append(f"# 🏛️ DỰ THẢO THẨM ĐỊNH ĐỀ THI — HỘI ĐỒNG TRỌNG TÀI 3+1")
        md.append(f"**Tài liệu:** `{file_name}` | **Trạng thái:** `{badge}` | **Độ tin cậy:** `{final_confidence*100:.1f}%`\n")

        md.append("### 🗳️ Biểu Quyết Hội Đồng Các Lần Quét:")
        for s in scans:
            icon = "⚖️" if s.pass_number == 4 else "🔹"
            ev_str = ", ".join(s.evidence_tokens[:5]) if s.evidence_tokens else "N/A"
            md.append(
                f"- {icon} **{s.pass_name}:** `{s.subject_vi}` ({s.confidence*100:.0f}%) — "
                f"*Khối: {s.grade_vi}* | *Căn cứ: {ev_str}* | *{s.execution_time_ms:.1f}ms*"
            )

        if not is_unanimous and conflict_summary:
            md.append("\n### ⚠️ Biên Bản Bất Đồng & Kích Hoạt Lần Quét 4:")
            md.append(f"> {conflict_summary}\n")
            if contrastive_suppressions:
                md.append("**Ma trận triệt tiêu tương phản đã áp dụng:**")
                for cs in contrastive_suppressions:
                    md.append(f"- ⚔️ *{cs}*")
            if arbitration_rationale:
                md.append(f"\n**Lập luận phán quyết của Trọng tài:**\n> {arbitration_rationale}")

        md.append("\n### 🎯 Phán Quyết Cuối Cùng:")
        md.append(f"- **Môn học chính thức:** **{final_subject.value}** (`{final_subject.name}`)")
        md.append(f"- **Khối lớp:** **{grade_str}**")
        md.append(f"- **Phân loại đề:** **{final_track_vi}**")
        md.append(f"- **Độ chuẩn xác cam kết:** `100% Deterministic (Zero-AI, $0 Chi Phí API)`")
        md.append(f"- **Tóm tắt căn cứ:** {final_rationale}")

        return "\n".join(md)
