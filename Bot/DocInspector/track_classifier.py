"""
DocInspector - Exam Track Classifier (Phân loại Thể loại: thường / hsg / chuyên / quốc tế / chung).
Thang độ khó: đề thường < đề hsg < đề chuyên.
Đề quốc tế: các kì thi quốc tế (IMO, IOI, IPhO, AMC, Kangaroo/IKMC, SASMO, TIMO, SAT... cả tiếng Việt và quốc tế).
Đề chung: tài liệu lý thuyết, đề cương ôn tập tổng hợp, hoặc đề chung chung có thể gây hiểu lầm.
100% Deterministic, Zero AI.
"""

from __future__ import annotations

import re
from typing import List, Tuple

from .models import (
    DifficultyAssessment,
    DocumentCategory,
    ExamTrackTier,
    ExamType,
    GradeLevel,
    Pass1Report,
    Pass2Report,
    Pass3Report,
    Subject,
)


class ExamTrackClassifier:
    """
    Phân loại đề thi thành đúng 5 thể loại theo yêu cầu nghiệp vụ:
    1. 'quoc_te': Đề tham gia các kỳ thi quốc tế (IMO, IOI, IPhO, AMC, IKMC, SASMO, HKIMO, TIMO, SAT...
                  bao gồm cả bản dịch tiếng Việt và bản gốc quốc tế).
    2. 'chung'  : Đề chung (tài liệu lý thuyết, đề cương tổng hợp, hoặc chung chung dễ gây hiểu lầm).
    3. 'chuyen' : Đề chuyên (trường THPT Chuyên, vào 10 Chuyên, Olympic Quốc gia, HSGQG - cấp độ cao nhất).
    4. 'hsg'    : Đề HSG (học sinh giỏi cấp trường/quận/huyện/tỉnh/TP - cấp độ trung gian, dễ hơn Chuyên).
    5. 'thuong' : Đề thường (đại trà, phổ thông, kiểm tra định kỳ, thi thử THPT - độ khó thấp nhất).
    
    Độ khó học thuật: đề thường < đề hsg < đề chuyên.
    """

    # 1. BỘ TỪ KHÓA ĐỀ QUỐC TẾ (Quốc tế, IMO, AMC, Kangaroo/IKMC, SASMO... cả tiếng Việt và tiếng Anh)
    RE_QUOC_TE_ACRONYMS = re.compile(
        r"(?i)\b(?:imo|ioi|ipho|icho|ibo|amc\s*(?:8|10|12)?|aime|usamo|ikmc|kangaroo|sasmo|asmo|simoc|seamo|wmi|wmtc|hkimo|timo|vtmo|apmo|apio|apho|sat|act|cambridge|a-level|alevel|igcse|ielts|toefl)\b"
    )
    QUOC_TE_KEYWORDS: List[str] = [
        "quốc tế", "quoc te", "international", "kỳ thi quốc tế", "ky thi quoc te",
        "toán quốc tế", "toan quoc te", "tin học quốc tế", "tin hoc quoc te",
        "vật lý quốc tế", "vat ly quoc te", "hóa học quốc tế", "hoa hoc quoc te",
        "olympic quốc tế", "olympiad quốc tế", "cuộc thi quốc tế", "cuoc thi quoc te",
        "đề thi quốc tế", "de thi quoc te", "ikmc", "kangaroo math", "toán kangaroo",
        "sasmo", "asmo", "hkimo", "timo", "wmi", "seamo", "simoc",
    ]

    # 2. BỘ TỪ KHÓA ĐỀ CHUNG (Chung chung, lý thuyết, đề cương, dễ gây hiểu lầm)
    CHUNG_KEYWORDS: List[str] = [
        "đề chung", "de chung", "tổng hợp kiến thức", "tong hop kien thuc",
        "tài liệu tổng hợp", "tai lieu tong hop", "đề cương tổng hợp", "de cuong tong hop",
        "đề cương ôn tập", "de cuong on tap", "đề cương", "de cuong",
        "chuyên đề chung", "chuyen de chung", "ôn tập chung", "on tap chung",
        "kiến thức chung", "kien thuc chung", "tài liệu tham khảo chung",
        "chung cho các khối", "tất cả các khối", "chung cho toàn khối",
    ]

    # 3. BỘ TỪ KHÓA ĐỀ CHUYÊN (Cấp độ cao nhất: thường < hsg < chuyên)
    # Lưu ý: đã loại "quốc gia" đứng lẻ vì gây false-positive với "thpt quốc gia" (đề thường)
    CHUYEN_KEYWORDS: List[str] = [
        "chuyên", "thpt chuyên", "trường chuyên", "thi chuyên", "vào 10 chuyên",
        "tuyển sinh lớp 10 chuyên", "chuyên toán", "chuyên tin", "chuyên lý",
        "chuyên hóa", "chuyên sinh", "chuyên văn", "chuyên anh",
        "olympic", "olympiad", "hsgqg", "hsg quốc gia", "hsg quoc gia",
        "tst", "vnoi", "icpc", "competitive programming", "subtasks",
        "amsterdam", "chuyên sư phạm", "chuyên khtn", "lê hồng phong",
        "trần đại nghĩa", "năng khiếu", "lam sơn", "phan bội châu", "quốc học",
    ]

    # 4. BỘ TỪ KHÓA ĐỀ HSG (Cấp độ trung gian: thường < hsg < chuyên)
    HSG_KEYWORDS: List[str] = [
        "học sinh giỏi", "hsg", "chọn học sinh giỏi", "kỳ thi hsg",
        "hsg cấp trường", "hsg cấp huyện", "hsg cấp tỉnh", "hsg cấp thành phố",
        "hsg cấp tp", "giao lưu hsg", "bồi dưỡng hsg", "bồi dưỡng học sinh giỏi",
        "khảo sát hsg", "học sinh giỏi toán", "học sinh giỏi văn",
        "học sinh giỏi tiếng anh", "học sinh giỏi lý", "học sinh giỏi hóa",
    ]

    # 5. BỘ TỪ KHÓA ĐỀ THƯỜNG (Đại trà, phổ thông, tốt nghiệp THPT)
    THUONG_KEYWORDS: List[str] = [
        "học kì", "học kỳ", "giữa kì", "giữa kỳ", "cuối kì", "cuối kỳ",
        "kiểm tra 1 tiết", "15 phút", "kiểm tra nhanh", "định kì", "định kỳ", "thường xuyên",
        "tốt nghiệp", "thpt quốc gia", "tốt nghiệp thpt", "khảo sát chất lượng",
        "đại trà", "thường", "đề tham khảo", "đề minh họa", "ôn tập hè",
    ]

    @classmethod
    def classify(
        cls,
        raw_text: str,
        filename: str,
        category: DocumentCategory,
        exam_type: ExamType,
        subject: Subject,
        pass1: Pass1Report,
        pass2: Pass2Report,
        pass3: Pass3Report,
        diff: DifficultyAssessment,
    ) -> Tuple[ExamTrackTier, str, str]:
        """
        Phân loại chính xác 5 thể loại đề thi:
        Returns:
            - ExamTrackTier: QUOC_TE, CHUNG, CHUYEN, HSG, or THUONG
            - label_vi: "quốc tế", "chung", "chuyên", "hsg", or "thường"
            - rationale: Multi-line detailed explanation
        """
        # Normalize text sample (first 3500 chars for header clues + filename)
        search_sample = (filename + " " + raw_text[:3500]).lower()

        def _keyword_hit(keywords: list[str]) -> bool:
            """So khớp an toàn: cụm dài dùng substring, từ ngắn dùng word-boundary."""
            for kw in keywords:
                kw_l = kw.lower()
                if len(kw_l) <= 8 and " " not in kw_l:
                    if re.search(r"(?<![\wà-ỹ])" + re.escape(kw_l) + r"(?![\wà-ỹ])", search_sample):
                        return True
                else:
                    if kw_l in search_sample:
                        return True
            return False

        # Check explicit keywords
        has_quoc_te_regex = bool(cls.RE_QUOC_TE_ACRONYMS.search(search_sample))
        has_quoc_te_phrase = _keyword_hit(cls.QUOC_TE_KEYWORDS)
        has_quoc_te = has_quoc_te_regex or has_quoc_te_phrase

        has_chung_keyword = _keyword_hit(cls.CHUNG_KEYWORDS)
        has_chuyen_keyword = _keyword_hit(cls.CHUYEN_KEYWORDS)
        has_hsg_keyword = _keyword_hit(cls.HSG_KEYWORDS)
        has_thuong_keyword = _keyword_hit(cls.THUONG_KEYWORDS)

        # Quantitative factors from Pass 2 & Difficulty Assessor
        total_questions = max(1, pass2.question_count)
        cb = pass2.cognitive_breakdown
        high_app_ratio = cb.high_application_count / total_questions
        app_and_high_ratio = (cb.application_count + cb.high_application_count) / total_questions
        score = diff.score

        # Specialized features from Pass 2
        is_competitive = exam_type == ExamType.COMPETITIVE_PROGRAMMING or bool(pass2.competitive_meta)
        is_olympiad_grade = pass2.grade_level == GradeLevel.OLYMPIAD_GIFTED

        # ---------------------------------------------------------------------
        # 1. THỂ LOẠI: ĐỀ QUỐC TẾ (Kỳ thi quốc tế - tiếng Việt lẫn tiếng Anh)
        # ---------------------------------------------------------------------
        if has_quoc_te and category not in [DocumentCategory.ADMIN_CONTRACT, DocumentCategory.LESSON_PLAN]:
            # Đảm bảo đây là đề thi / tài liệu tham gia kỳ thi quốc tế
            return (
                ExamTrackTier.QUOC_TE,
                "quốc tế",
                "Đề thi thể loại 'quốc tế': Tham gia các kỳ thi quốc tế (IMO, IOI, IPhO, AMC, Kangaroo/IKMC, SASMO, HKIMO, TIMO, SAT... bao gồm cả bản dịch tiếng Việt và bản quốc tế).",
            )

        # ---------------------------------------------------------------------
        # 2. THỂ LOẠI: ĐỀ CHUNG (Tài liệu lý thuyết / đề cương / chung chung dễ gây hiểu lầm)
        # ---------------------------------------------------------------------
        if category in [DocumentCategory.ADMIN_CONTRACT, DocumentCategory.LESSON_PLAN, DocumentCategory.THEORY_SYLLABUS]:
            if category == DocumentCategory.ADMIN_CONTRACT:
                return (
                    ExamTrackTier.CHUNG,
                    "chung",
                    "Đề thi thể loại 'chung': Văn bản quy định hành chính / hợp đồng sư phạm (không phải đề thi kiểm tra).",
                )
            if category == DocumentCategory.LESSON_PLAN:
                return (
                    ExamTrackTier.CHUNG,
                    "chung",
                    "Đề thi thể loại 'chung': Kế hoạch bài dạy / Giáo án sư phạm phục vụ giảng dạy chung.",
                )
            if category == DocumentCategory.THEORY_SYLLABUS:
                return (
                    ExamTrackTier.CHUNG,
                    "chung",
                    "Đề thi thể loại 'chung': Chuyên đề lý thuyết / Đề cương tóm tắt kiến thức chung.",
                )

        if has_chung_keyword and not (has_chuyen_keyword or has_hsg_keyword):
            return (
                ExamTrackTier.CHUNG,
                "chung",
                "Đề thi thể loại 'chung': Tài liệu tổng hợp kiến thức / đề cương ôn tập chung chung (dễ gây hiểu lầm nếu coi là đề thi độc lập).",
            )

        if pass2.question_count == 0 and category == DocumentCategory.GENERAL_DOCUMENT and not is_competitive:
            return (
                ExamTrackTier.CHUNG,
                "chung",
                "Đề thi thể loại 'chung': Tài liệu học tập chung chung, không chứa cấu trúc câu hỏi đề thi kiểm tra cụ thể.",
            )

        # ---------------------------------------------------------------------
        # 3. THỂ LOẠI: ĐỀ CHUYÊN (Độ khó cao nhất: đề thường < đề hsg < đề chuyên)
        # ---------------------------------------------------------------------
        if is_competitive or is_olympiad_grade:
            return (
                ExamTrackTier.CHUYEN,
                "chuyên",
                "Đề thi thể loại 'chuyên': Cấp độ cao nhất trong thang độ khó (thường < hsg < chuyên). Định dạng Olympic Tin học / Competitive Programming hoặc cấp độ Olympic HSGQG.",
            )

        if has_chuyen_keyword and not has_thuong_keyword:
            return (
                ExamTrackTier.CHUYEN,
                "chuyên",
                "Đề thi thể loại 'chuyên': Cấp độ cao nhất trong thang độ khó (thường < hsg < chuyên). Phát hiện từ khóa trường Chuyên / thi tuyển sinh vào Chuyên.",
            )

        # Extremely hard academic profile without explicit keywords
        if score >= 8.3 or high_app_ratio >= 0.35:
            return (
                ExamTrackTier.CHUYEN,
                "chuyên",
                f"Đề thi thể loại 'chuyên': Cấp độ cao nhất trong thang độ khó (thường < hsg < chuyên). Độ khó đạt {score}/10, tỷ lệ câu hỏi Vận dụng cao chiếm {high_app_ratio*100:.1f}%, vượt ngưỡng chuẩn đề thi thông thường và HSG.",
            )

        # ---------------------------------------------------------------------
        # 4. THỂ LOẠI: ĐỀ HSG (Độ khó trung gian: đề thường < đề hsg < đề chuyên)
        # ---------------------------------------------------------------------
        if has_hsg_keyword and not has_chuyen_keyword:
            return (
                ExamTrackTier.HSG,
                "hsg",
                "Đề thi thể loại 'hsg': Cấp độ trung gian trong thang độ khó (thường < hsg < chuyên). Kỳ thi chọn Học sinh giỏi cấp trường/quận/huyện/tỉnh/thành phố.",
            )

        # Moderate-to-high difficulty (6.2 <= score < 8.3) with significant application
        if (6.2 <= score < 8.3) and (app_and_high_ratio >= 0.45 or high_app_ratio >= 0.20):
            if not (has_thuong_keyword and score < 7.0):
                return (
                    ExamTrackTier.HSG,
                    "hsg",
                    f"Đề thi thể loại 'hsg': Cấp độ trung gian trong thang độ khó (thường < hsg < chuyên). Độ khó đạt {score}/10, tỷ lệ vận dụng {app_and_high_ratio*100:.1f}%, phù hợp cấp độ thi Học sinh giỏi (dễ hơn đề Chuyên).",
                )

        # ---------------------------------------------------------------------
        # 5. THỂ LOẠI: ĐỀ THƯỜNG (Đại trà / Phổ thông - độ khó thấp nhất)
        # ---------------------------------------------------------------------
        return (
            ExamTrackTier.THUONG,
            "thường",
            f"Đề thi thể loại 'thường': Cấp độ đại trà / phổ thông tiêu chuẩn trong thang độ khó (thường < hsg < chuyên, đạt độ khó {score}/10).",
        )
