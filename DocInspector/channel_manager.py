"""
Channel-Aware Document Verification & Automated Bot Routing Engine.
Inspects channel context (Discord / Telegram / Forum / Directory), automatically
determines allowed subjects for that channel, and cross-checks uploaded documents.
100% Deterministic, Zero AI.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from .models import (
    DEFAULT_SUBMISSION_CHANNEL_ID,
    DEFAULT_TARGET_CATEGORY_ID,
    ChannelComplianceResult,
    DocumentCategory,
    ExamTrackTier,
    ExamType,
    GradeLevel,
    GRADE_LEVEL_VI_NAMES,
    InspectionReport,
    Subject,
    SubmissionRoutingResult,
    VerificationVerdict,
)


@dataclass
class ChannelProfile:
    """Configuration profile for a specific educational channel."""
    channel_name: str
    channel_id: Optional[str] = None
    category_id: Optional[str] = DEFAULT_TARGET_CATEGORY_ID
    category_name: Optional[str] = None
    allowed_subjects: List[Subject] = field(default_factory=list)
    allowed_tracks: Optional[List[ExamTrackTier]] = None
    allowed_grades: Optional[List[GradeLevel]] = None
    is_wildcard: bool = False
    required_category: Optional[DocumentCategory] = None
    description: str = ""
    custom_suggested_channel: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "channel_name": self.channel_name,
            "channel_id": self.channel_id,
            "category_id": self.category_id,
            "category_name": self.category_name,
            "allowed_subjects": [s.value for s in self.allowed_subjects],
            "allowed_tracks": [t.value for t in self.allowed_tracks] if self.allowed_tracks else None,
            "allowed_grades": [g.value for g in self.allowed_grades] if self.allowed_grades else None,
            "is_wildcard": self.is_wildcard,
            "required_category": self.required_category.value if self.required_category else None,
            "description": self.description,
        }


class ChannelRegistry:
    """Pre-configured popular channel templates and persistent channel database."""

    SUBJECT_VI_NAMES: Dict[Subject, str] = {
        Subject.MATHEMATICS: "Toán học",
        Subject.INFORMATICS: "Tin học / Lập trình",
        Subject.PHYSICS: "Vật lý",
        Subject.CHEMISTRY: "Hóa học",
        Subject.BIOLOGY: "Sinh học",
        Subject.LITERATURE: "Ngữ văn",
        Subject.ENGLISH: "Tiếng Anh",
        Subject.JAPANESE: "Tiếng Nhật",
        Subject.CHINESE: "Tiếng Trung",
        Subject.KOREAN: "Tiếng Hàn",
        Subject.RUSSIAN: "Tiếng Nga",
        Subject.FRENCH: "Tiếng Pháp",
        Subject.HISTORY: "Lịch sử",
        Subject.GEOGRAPHY: "Địa lý",
        Subject.CIVIC_EDUCATION: "Giáo dục công dân / KT&PL",
        Subject.NATURAL_SCIENCE: "Khoa học tự nhiên",
        Subject.GENERAL: "Tài liệu tổng hợp",
        Subject.NON_ACADEMIC: "Tài liệu phi học thuật",
    }

    SUBJECT_DEFAULT_CHANNELS: Dict[Subject, str] = {
        Subject.MATHEMATICS: "de-toan",
        Subject.INFORMATICS: "chuyen-tin",
        Subject.PHYSICS: "de-ly",
        Subject.CHEMISTRY: "de-hoa",
        Subject.BIOLOGY: "de-sinh",
        Subject.LITERATURE: "de-van",
        Subject.ENGLISH: "tieng-anh",
        Subject.JAPANESE: "tieng-nhat",
        Subject.CHINESE: "tieng-trung",
        Subject.KOREAN: "tieng-han",
        Subject.RUSSIAN: "tieng-nga",
        Subject.FRENCH: "tieng-phap",
        Subject.HISTORY: "lich-su",
        Subject.GEOGRAPHY: "dia-ly",
        Subject.CIVIC_EDUCATION: "gdcd",
        Subject.NATURAL_SCIENCE: "khoa-hoc-tu-nhien",
        Subject.GENERAL: "tai-lieu-chung",
        Subject.NON_ACADEMIC: "van-ban-chung",
    }

    # Built-in standard channel profiles
    STANDARD_CHANNELS: Dict[str, ChannelProfile] = {
        "de-toan": ChannelProfile("de-toan", allowed_subjects=[Subject.MATHEMATICS], allowed_tracks=[ExamTrackTier.THUONG, ExamTrackTier.HSG], description="Kênh đề thi & bài tập môn Toán học (Đại trà / HSG)"),
        "chuyen-toan": ChannelProfile("chuyen-toan", allowed_subjects=[Subject.MATHEMATICS], allowed_tracks=[ExamTrackTier.CHUYEN], description="Kênh Chuyên Toán, Olympic Toán & Tuyển sinh Chuyên"),
        "chuyen-tin": ChannelProfile("chuyen-tin", allowed_subjects=[Subject.INFORMATICS], allowed_tracks=[ExamTrackTier.CHUYEN, ExamTrackTier.HSG], description="Kênh Chuyên Tin, Olympic Tin học & Lập trình thuật toán"),
        "de-tin": ChannelProfile("de-tin", allowed_subjects=[Subject.INFORMATICS], allowed_tracks=[ExamTrackTier.THUONG], description="Kênh Tin học phổ thông & Ứng dụng"),
        "de-ly": ChannelProfile("de-ly", allowed_subjects=[Subject.PHYSICS], allowed_tracks=[ExamTrackTier.THUONG, ExamTrackTier.HSG], description="Kênh đề thi & tài liệu ôn thi môn Vật lý"),
        "chuyen-ly": ChannelProfile("chuyen-ly", allowed_subjects=[Subject.PHYSICS], allowed_tracks=[ExamTrackTier.CHUYEN], description="Kênh Chuyên Vật lý & Olympic Vật lý"),
        "de-hoa": ChannelProfile("de-hoa", allowed_subjects=[Subject.CHEMISTRY], allowed_tracks=[ExamTrackTier.THUONG, ExamTrackTier.HSG], description="Kênh đề thi & bài tập Hóa học"),
        "chuyen-hoa": ChannelProfile("chuyen-hoa", allowed_subjects=[Subject.CHEMISTRY], allowed_tracks=[ExamTrackTier.CHUYEN], description="Kênh Chuyên Hóa học & Olympic"),
        "de-sinh": ChannelProfile("de-sinh", allowed_subjects=[Subject.BIOLOGY], allowed_tracks=[ExamTrackTier.THUONG, ExamTrackTier.HSG], description="Kênh đề thi & tài liệu Sinh học"),
        "chuyen-sinh": ChannelProfile("chuyen-sinh", allowed_subjects=[Subject.BIOLOGY], allowed_tracks=[ExamTrackTier.CHUYEN], description="Kênh Chuyên Sinh học & Olympic"),
        "de-van": ChannelProfile("de-van", allowed_subjects=[Subject.LITERATURE], allowed_tracks=[ExamTrackTier.THUONG, ExamTrackTier.HSG], description="Kênh đề thi, văn mẫu & tài liệu Ngữ văn"),
        "chuyen-van": ChannelProfile("chuyen-van", allowed_subjects=[Subject.LITERATURE], allowed_tracks=[ExamTrackTier.CHUYEN], description="Kênh Chuyên Ngữ văn & HSGQG"),
        "tieng-anh": ChannelProfile("tieng-anh", allowed_subjects=[Subject.ENGLISH], allowed_tracks=[ExamTrackTier.THUONG, ExamTrackTier.HSG], description="Kênh tài liệu Tiếng Anh (THPT, IELTS, TOEIC)"),
        "chuyen-anh": ChannelProfile("chuyen-anh", allowed_subjects=[Subject.ENGLISH], allowed_tracks=[ExamTrackTier.CHUYEN], description="Kênh Chuyên Tiếng Anh & Olympic Ngoại ngữ"),
        "tieng-nhat": ChannelProfile("tieng-nhat", allowed_subjects=[Subject.JAPANESE], description="Kênh đề thi & tài liệu Tiếng Nhật JLPT"),
        "tieng-trung": ChannelProfile("tieng-trung", allowed_subjects=[Subject.CHINESE], description="Kênh đề thi & tài liệu Tiếng Trung HSK"),
        "tieng-han": ChannelProfile("tieng-han", allowed_subjects=[Subject.KOREAN], description="Kênh đề thi & tài liệu Tiếng Hàn TOPIK"),
        "tieng-nga": ChannelProfile("tieng-nga", allowed_subjects=[Subject.RUSSIAN], description="Kênh đề thi & tài liệu Tiếng Nga TRKI"),
        "tieng-phap": ChannelProfile("tieng-phap", allowed_subjects=[Subject.FRENCH], description="Kênh tài liệu Tiếng Pháp"),
        "khoa-hoc-tu-nhien": ChannelProfile(
            "khoa-hoc-tu-nhien",
            allowed_subjects=[Subject.PHYSICS, Subject.CHEMISTRY, Subject.BIOLOGY, Subject.NATURAL_SCIENCE],
            description="Kênh khối môn Khoa học Tự nhiên (Lý - Hóa - Sinh - KHTN)",
        ),
        "khoa-hoc-xa-hoi": ChannelProfile(
            "khoa-hoc-xa-hoi",
            allowed_subjects=[Subject.LITERATURE, Subject.HISTORY, Subject.GEOGRAPHY, Subject.CIVIC_EDUCATION],
            description="Kênh khối môn Khoa học Xã hội (Văn - Sử - Địa - GDCD)",
        ),
        "giao-an-5512": ChannelProfile(
            "giao-an-5512",
            allowed_subjects=list(Subject),
            is_wildcard=True,
            required_category=DocumentCategory.LESSON_PLAN,
            description="Kênh trao đổi Kế hoạch bài dạy (Giáo án CV 5512)",
        ),
        "tai-lieu-chung": ChannelProfile(
            "tai-lieu-chung",
            allowed_subjects=list(Subject),
            is_wildcard=True,
            description="Kênh trao đổi tài liệu chung (Chấp nhận tất cả các môn)",
        ),
        # Grade-specific Channels (Khối lớp)
        "toan-12": ChannelProfile("toan-12", allowed_subjects=[Subject.MATHEMATICS], allowed_tracks=[ExamTrackTier.THUONG, ExamTrackTier.HSG], allowed_grades=[GradeLevel.GRADE_12], description="Kênh đề thi & tài liệu Toán Lớp 12 / Ôn thi tốt nghiệp THPT & ĐH"),
        "toan-11": ChannelProfile("toan-11", allowed_subjects=[Subject.MATHEMATICS], allowed_tracks=[ExamTrackTier.THUONG, ExamTrackTier.HSG], allowed_grades=[GradeLevel.GRADE_11], description="Kênh đề thi & bài tập Toán Lớp 11"),
        "toan-10": ChannelProfile("toan-10", allowed_subjects=[Subject.MATHEMATICS], allowed_tracks=[ExamTrackTier.THUONG, ExamTrackTier.HSG], allowed_grades=[GradeLevel.GRADE_10], description="Kênh đề thi & bài tập Toán Lớp 10"),
        "toan-9": ChannelProfile("toan-9", allowed_subjects=[Subject.MATHEMATICS], allowed_tracks=[ExamTrackTier.THUONG, ExamTrackTier.HSG], allowed_grades=[GradeLevel.GRADE_9], description="Kênh đề thi & ôn thi vào 10 môn Toán Lớp 9"),
        "ly-12": ChannelProfile("ly-12", allowed_subjects=[Subject.PHYSICS], allowed_tracks=[ExamTrackTier.THUONG, ExamTrackTier.HSG], allowed_grades=[GradeLevel.GRADE_12], description="Kênh đề thi & tài liệu Vật lý Lớp 12"),
        "hoa-12": ChannelProfile("hoa-12", allowed_subjects=[Subject.CHEMISTRY], allowed_tracks=[ExamTrackTier.THUONG, ExamTrackTier.HSG], allowed_grades=[GradeLevel.GRADE_12], description="Kênh đề thi & bài tập Hóa học Lớp 12"),
        "khoi-12": ChannelProfile("khoi-12", allowed_subjects=list(Subject), allowed_grades=[GradeLevel.GRADE_12], description="Kênh tài liệu tổng hợp Khối 12"),
        "khoi-11": ChannelProfile("khoi-11", allowed_subjects=list(Subject), allowed_grades=[GradeLevel.GRADE_11], description="Kênh tài liệu tổng hợp Khối 11"),
        "khoi-10": ChannelProfile("khoi-10", allowed_subjects=list(Subject), allowed_grades=[GradeLevel.GRADE_10], description="Kênh tài liệu tổng hợp Khối 10"),
        "khoi-thcs": ChannelProfile(
            "khoi-thcs",
            allowed_subjects=list(Subject),
            allowed_grades=[GradeLevel.GRADE_6, GradeLevel.GRADE_7, GradeLevel.GRADE_8, GradeLevel.GRADE_9, GradeLevel.MIDDLE_SCHOOL],
            description="Kênh tài liệu Khối THCS (Lớp 6, 7, 8, 9)",
        ),
    }


class ChannelAutoDetector:
    """
    Automatically inspects channel names, slugs, or forum topics
    and infers which subjects are designated for that channel.
    """

    @classmethod
    def normalize_channel_name(cls, raw_name: str) -> str:
        """Strip prefixes, emojis, punctuation and normalize to slug format."""
        s = raw_name.strip().lower()
        if s.startswith("#"):
            s = s[1:]
        # Remove emojis and non-alphanumeric except hyphens and underscores
        s = re.sub(r"[^\w\s-]", "", s)
        s = re.sub(r"[\s_]+", "-", s).strip("-")
        return s

    @classmethod
    def detect_channel_profile(cls, raw_name: str) -> ChannelProfile:
        """
        Infers the subject, track, and grade rules directly from the channel name string.
        e.g., 'toan-12' -> ChannelProfile for Subject.MATHEMATICS & GradeLevel.GRADE_12
        """
        clean_name = cls.normalize_channel_name(raw_name)
        
        # 1. Exact preset match
        if clean_name in ChannelRegistry.STANDARD_CHANNELS:
            return ChannelRegistry.STANDARD_CHANNELS[clean_name]

        # Track detection from name
        detected_tracks: Optional[List[ExamTrackTier]] = None
        if any(k in clean_name for k in ["quoc-te", "international", "imo", "amc", "ikmc", "kangaroo", "sasmo"]):
            detected_tracks = [ExamTrackTier.QUOC_TE]
        elif any(k in clean_name for k in ["chuyen", "olympic", "gifted", "tst"]):
            detected_tracks = [ExamTrackTier.CHUYEN]
        elif any(k in clean_name for k in ["hsg", "hoc-sinh-gioi"]):
            detected_tracks = [ExamTrackTier.HSG, ExamTrackTier.CHUYEN]
        elif any(k in clean_name for k in ["chung", "tong-hop", "ly-thuyet"]):
            detected_tracks = [ExamTrackTier.CHUNG]
        elif any(k in clean_name for k in ["dai-tra", "co-ban", "tot-nghiep", "pho-thong", "thuong"]):
            detected_tracks = [ExamTrackTier.THUONG]

        # Grade detection from name
        detected_grades: Optional[List[GradeLevel]] = None
        grade_matches: List[GradeLevel] = []
        if re.search(r"(?:^|[-_])(?:12|k12|khoi-12|lop-12)(?:$|[-_])", clean_name):
            grade_matches.append(GradeLevel.GRADE_12)
        if re.search(r"(?:^|[-_])(?:11|k11|khoi-11|lop-11)(?:$|[-_])", clean_name):
            grade_matches.append(GradeLevel.GRADE_11)
        if re.search(r"(?:^|[-_])(?:10|k10|khoi-10|lop-10)(?:$|[-_])", clean_name):
            grade_matches.append(GradeLevel.GRADE_10)
        if re.search(r"(?:^|[-_])(?:9|k9|khoi-9|lop-9)(?:$|[-_])", clean_name):
            grade_matches.append(GradeLevel.GRADE_9)
        if re.search(r"(?:^|[-_])(?:8|k8|khoi-8|lop-8)(?:$|[-_])", clean_name):
            grade_matches.append(GradeLevel.GRADE_8)
        if re.search(r"(?:^|[-_])(?:7|k7|khoi-7|lop-7)(?:$|[-_])", clean_name):
            grade_matches.append(GradeLevel.GRADE_7)
        if re.search(r"(?:^|[-_])(?:6|k6|khoi-6|lop-6)(?:$|[-_])", clean_name):
            grade_matches.append(GradeLevel.GRADE_6)
        if re.search(r"(?:^|[-_])(?:thcs|cap-2|cap2)(?:$|[-_])", clean_name):
            grade_matches.extend([GradeLevel.GRADE_6, GradeLevel.GRADE_7, GradeLevel.GRADE_8, GradeLevel.GRADE_9, GradeLevel.MIDDLE_SCHOOL])
        if re.search(r"(?:^|[-_])(?:thpt|cap-3|cap3)(?:$|[-_])", clean_name):
            grade_matches.extend([GradeLevel.GRADE_10, GradeLevel.GRADE_11, GradeLevel.GRADE_12, GradeLevel.HIGH_SCHOOL])
        if re.search(r"(?:^|[-_])(?:tieu-hoc|cap-1|cap1)(?:$|[-_])", clean_name):
            grade_matches.append(GradeLevel.PRIMARY_SCHOOL)
        if re.search(r"(?:^|[-_])(?:dai-hoc|dh|cao-dang|university)(?:$|[-_])", clean_name):
            grade_matches.append(GradeLevel.UNIVERSITY)
        if re.search(r"(?:^|[-_])(?:olympic|olympiad|doi-tuyen|quoc-gia|vmo|tst)(?:$|[-_])", clean_name):
            grade_matches.append(GradeLevel.OLYMPIAD_GIFTED)

        if grade_matches:
            seen_g: Set[GradeLevel] = set()
            detected_grades = [g for g in grade_matches if not (g in seen_g or seen_g.add(g))]

        grade_desc_suffix = ""
        if detected_grades:
            grade_names = [GRADE_LEVEL_VI_NAMES.get(g, g.value) for g in detected_grades[:2]]
            grade_desc_suffix = f" (Khối: {', '.join(grade_names)})"

        # 2. Check for wildcard / general channel keywords (chỉ khi kênh không chỉ định môn cụ thể)
        subject_tokens = ["toan", "math", "tin", "code", "lap-trinh", "cpp", "python", "pascal", "scratch", "dsa", "thuattoan", "ly", "physics", "vat-ly", "hoa", "chem", "sinh", "bio", "van", "literature", "anh", "english", "ielts", "toeic", "su", "history", "dia", "geo", "gdcd", "khtn"]
        parts_set = set(clean_name.split("-"))
        has_specific_subject = any(st in parts_set or st in clean_name for st in subject_tokens)
        wildcard_keywords = ["tong-hop", "chung", "general", "tai-lieu-chung", "share", "chat", "tat-ca", "all-subjects"]
        if not has_specific_subject and (any(w in clean_name for w in wildcard_keywords) or clean_name in ["tai-lieu", "kho-de"]):
            return ChannelProfile(
                channel_name=clean_name,
                allowed_subjects=list(Subject),
                allowed_tracks=detected_tracks,
                allowed_grades=detected_grades,
                is_wildcard=True,
                description=f"Kênh tổng hợp #{clean_name}{grade_desc_suffix} (Chấp nhận tất cả môn)",
            )

        # 3. Check for Lesson plan / KHBD 5512 channels
        lesson_keywords = ["giao-an", "khbd", "5512", "bai-day", "ke-hoach-bai-day"]
        if any(k in clean_name for k in lesson_keywords):
            return ChannelProfile(
                channel_name=clean_name,
                allowed_subjects=list(Subject),
                allowed_tracks=detected_tracks,
                allowed_grades=detected_grades,
                is_wildcard=True,
                required_category=DocumentCategory.LESSON_PLAN,
                description=f"Kênh Kế hoạch bài dạy / Giáo án #{clean_name}{grade_desc_suffix}",
            )

        # 4. Check for Natural Science or Social Science clusters
        if any(k in clean_name for k in ["khtn", "khoa-hoc-tu-nhien", "tu-nhien", "stem"]):
            return ChannelProfile(
                channel_name=clean_name,
                allowed_subjects=[Subject.PHYSICS, Subject.CHEMISTRY, Subject.BIOLOGY, Subject.NATURAL_SCIENCE],
                allowed_tracks=detected_tracks,
                allowed_grades=detected_grades,
                description=f"Kênh Khoa học Tự nhiên #{clean_name}{grade_desc_suffix}",
            )

        if any(k in clean_name for k in ["khxh", "khoa-hoc-xa-hoi", "xa-hoi"]):
            return ChannelProfile(
                channel_name=clean_name,
                allowed_subjects=[Subject.LITERATURE, Subject.HISTORY, Subject.GEOGRAPHY, Subject.CIVIC_EDUCATION],
                allowed_tracks=detected_tracks,
                allowed_grades=detected_grades,
                description=f"Kênh Khoa học Xã hội #{clean_name}{grade_desc_suffix}",
            )

        # 5. Keyword-to-Subject heuristics
        subject_rules: List[Tuple[List[str], Subject]] = [
            (["toan", "math", "calculus", "giai-tich", "hinh-hoc", "algebra"], Subject.MATHEMATICS),
            (["tin", "code", "lap-trinh", "algo", "pascal", "cpp", "python", "informatics", "tin-hoc"], Subject.INFORMATICS),
            (["ly", "physics", "vat-ly", "dien-xoay-chieu", "quang-hoc"], Subject.PHYSICS),
            (["hoa", "chem", "hoa-hoc", "huu-co", "vo-co"], Subject.CHEMISTRY),
            (["sinh", "bio", "sinh-hoc", "di-truyen", "te-bao"], Subject.BIOLOGY),
            (["van", "literature", "ngu-van", "van-hoc", "nghi-luan"], Subject.LITERATURE),
            (["anh", "english", "ielts", "toeic", "tieng-anh", "ngoai-ngu"], Subject.ENGLISH),
            (["nhat", "japanese", "tieng-nhat", "jlpt"], Subject.JAPANESE),
            (["trung", "chinese", "tieng-trung", "hsk"], Subject.CHINESE),
            (["han", "korean", "tieng-han", "topik"], Subject.KOREAN),
            (["nga", "russian", "tieng-nga", "trki", "torfl"], Subject.RUSSIAN),
            (["phap", "french", "tieng-phap"], Subject.FRENCH),
            (["su", "history", "lich-su"], Subject.HISTORY),
            (["dia", "geography", "dia-ly"], Subject.GEOGRAPHY),
            (["gdcd", "ktpl", "cong-dan", "kinh-te-phap-luat"], Subject.CIVIC_EDUCATION),
        ]

        matched_subjects: Set[Subject] = set()
        parts = clean_name.split("-")

        for kws, subj in subject_rules:
            for kw in kws:
                if kw in parts or kw in clean_name:
                    matched_subjects.add(subj)
                    break

        if matched_subjects:
            subjects_list = list(matched_subjects)
            subj_names = [ChannelRegistry.SUBJECT_VI_NAMES.get(s, s.value) for s in subjects_list]

            return ChannelProfile(
                channel_name=clean_name,
                allowed_subjects=subjects_list,
                allowed_tracks=detected_tracks,
                allowed_grades=detected_grades,
                description=f"Kênh tự động nhận diện môn: {', '.join(subj_names)}{grade_desc_suffix}",
            )

        # Fallback: Wildcard channel if no subject cues could be found
        return ChannelProfile(
            channel_name=clean_name,
            allowed_subjects=list(Subject),
            allowed_tracks=detected_tracks,
            allowed_grades=detected_grades,
            is_wildcard=True,
            description=f"Kênh mở #{clean_name}{grade_desc_suffix} (Tự động chấp nhận mọi môn)",
        )


class CategoryDirectoryManager:
    """
    Manages Discord Category folders (Thư mục phân loại), such as ID 1534147951797080174,
    and Ingestion Submission Channel (Kênh nộp tài liệu ID 1535278288828633138).
    Inspects channels within the folder, maps allowed subjects,
    routes submissions, and formats directory overview trees.
    """
    DEFAULT_CATEGORY_ID: str = DEFAULT_TARGET_CATEGORY_ID
    DEFAULT_SUBMISSION_ID: str = DEFAULT_SUBMISSION_CHANNEL_ID

    @classmethod
    def is_target_category(cls, category_id: Optional[Union[str, int]], target_id: Optional[str] = None) -> bool:
        """Checks if a given channel's category matches the target folder ID."""
        if category_id is None:
            return True
        expected = target_id or cls.DEFAULT_CATEGORY_ID
        return str(category_id).strip() == str(expected).strip()

    @classmethod
    def is_submission_channel(cls, channel_id: Optional[Union[str, int]], target_id: Optional[str] = None) -> bool:
        """Checks if a given channel matches the document submission channel ID (1535278288828633138)."""
        if channel_id is None:
            return False
        expected = target_id or cls.DEFAULT_SUBMISSION_ID
        return str(channel_id).strip() == str(expected).strip()

    @classmethod
    def inspect_channels_in_category(
        cls,
        channel_names: List[str],
        category_id: str = DEFAULT_CATEGORY_ID,
    ) -> List[ChannelProfile]:
        """
        Takes a list of channel names in a category, detects their profiles and binds category_id.
        """
        profiles: List[ChannelProfile] = []
        for name in channel_names:
            prof = ChannelAutoDetector.detect_channel_profile(name)
            prof.category_id = str(category_id)
            profiles.append(prof)
        return profiles

    @classmethod
    def format_category_tree(
        cls,
        channel_names: List[str],
        category_name: str = "KHO ĐỀ THI & TÀI LIỆU HỌC TẬP",
        category_id: str = DEFAULT_CATEGORY_ID,
    ) -> str:
        """
        Generates an ASCII/Unicode directory tree view of all channels in this folder
        and their auto-detected subjects for Discord bot display.
        """
        lines = [
            f"📁 **[{category_name}]** *(Thư mục ID: `{category_id}`)*",
            "──────────────────────────────────────────────",
        ]
        profiles = cls.inspect_channels_in_category(channel_names, category_id)
        for i, p in enumerate(profiles):
            is_last = (i == len(profiles) - 1)
            prefix = "└──" if is_last else "├──"
            if p.is_wildcard:
                subj_desc = "Tất cả các môn (Kênh tổng hợp)"
            else:
                subj_desc = ", ".join([ChannelRegistry.SUBJECT_VI_NAMES.get(s, s.value) for s in p.allowed_subjects])
            
            tags = []
            if p.allowed_grades:
                if len(p.allowed_grades) <= 2:
                    grades_str = "/".join([GRADE_LEVEL_VI_NAMES.get(g, g.value) for g in p.allowed_grades])
                else:
                    grades_str = f"{GRADE_LEVEL_VI_NAMES.get(p.allowed_grades[0], p.allowed_grades[0].value)}..+{len(p.allowed_grades)-1}"
                tags.append(grades_str)
            if p.allowed_tracks:
                tracks_str = "/".join([t.value for t in p.allowed_tracks])
                tags.append(tracks_str)

            tag_str = f" `[{' | '.join(tags)}]`" if tags else ""
            lines.append(f"{prefix} `#{p.channel_name}`{tag_str} ➔ **{subj_desc}**")
        lines.append("──────────────────────────────────────────────")
        lines.append(f"📥 *Kênh nộp tài liệu trung tâm:* `<#{cls.DEFAULT_SUBMISSION_ID}>` *(ID: `{cls.DEFAULT_SUBMISSION_ID}`)*")
        lines.append("💡 *Bot sẽ tự động kiểm duyệt tài liệu và phân loại đúng kênh trong thư mục.*")
        return "\n".join(lines)

    @classmethod
    def route_submission(
        cls,
        report: InspectionReport,
        category_channels: Optional[List[Union[str, ChannelProfile]]] = None,
        category_id: Optional[Union[str, int]] = None,
        submission_channel_id: Optional[Union[str, int]] = None,
        author_mention: Optional[str] = None,
        author_name: Optional[str] = None,
    ) -> SubmissionRoutingResult:
        """
        Ingests document from Submission Channel (1535278288828633138)
        and automatically classifies & routes it into the best target channel
        under Category (1534147951797080174).
        
        Zero AI, sub-millisecond execution, deterministic rule engine.
        Handles:
        - Môn học (Subject)
        - Khối lớp (GradeLevel: Lớp 12, 11, 10, 9, 8, 7, 6, THCS, THPT, Đội tuyển...)
        - Thể loại (Exam track: thường / hsg / chuyên, where hsg < chuyên)
        - 4 trạng thái xác minh:
          1. Xác minh (thấy ổn)
          2. Chưa rõ ràng (xác minh nhưng chưa chắc là đúng đề)
          3. Không rõ ràng (xem được đề nhưng không biết là đề nào)
          4. Không xác minh (không được gì hết / nếu web chặn bot thì báo 'không rõ nguồn gốc')
        """
        resolved_cat_id = str(category_id) if category_id is not None else cls.DEFAULT_CATEGORY_ID
        resolved_sub_id = str(submission_channel_id) if submission_channel_id is not None else cls.DEFAULT_SUBMISSION_ID

        author_display = ""
        if author_mention and author_name:
            author_display = f"{author_mention} ({author_name})"
        elif author_mention:
            author_display = f"{author_mention}"
        elif author_name:
            author_display = f"**{author_name}**"

        author_line_reply = f"• Người nộp: {author_display}\n" if author_display else ""
        author_line_post = f"• Người đóng góp: {author_display}\n" if author_display else ""

        subj = report.detected_subject
        subj_vi = ChannelRegistry.SUBJECT_VI_NAMES.get(subj, subj.value)
        track = report.exam_track
        track_vi = report.exam_track_label_vi
        grade = report.grade_level
        grade_vi = report.grade_level_label_vi or GRADE_LEVEL_VI_NAMES.get(grade, grade.value)
        verdict = report.verdict
        verdict_vi = report.verdict_label_vi
        track_hierarchy_detail = "thường < hsg < chuyên (hsg là cấp độ dễ hơn của chuyên)"

        # Check for blocked / unverifiable / unknown origin
        if verdict == VerificationVerdict.UNVERIFIABLE_FAILED:
            sub_reply = (
                f"❌ **[KÊNH NỘP TÀI LIỆU | ID: `{resolved_sub_id}`] THẨM ĐỊNH THẤT BẠI: KHÔNG RÕ NGUỒN GỐC!**\n"
                f"{author_line_reply}"
                f"• Tệp / Liên kết: `{report.file_name}`\n"
                f"• Trạng thái: **{verdict_vi}**\n"
                f"• Lý do: {report.verdict_rationale or 'Tài liệu không đọc được hoặc link web chặn bot / không rõ nguồn gốc.'}\n"
                f"⚠️ Bot **không chuyển tiếp** vào Thư mục Phân loại `{resolved_cat_id}` để tránh lưu trữ tài liệu hỏng hoặc rác kênh.\n"
                f"👉 Vui lòng mở quyền truy cập chia sẻ công khai hoặc tải trực tiếp file .pdf/.docx lên kênh!"
            )
            return SubmissionRoutingResult(
                submission_channel_id=resolved_sub_id,
                target_category_id=resolved_cat_id,
                target_channel_name="unverified",
                detected_subject=subj,
                detected_subject_vi=subj_vi,
                detected_grade=grade,
                detected_grade_vi=grade_vi,
                exam_track=track,
                exam_track_label_vi=track_vi,
                verdict=verdict,
                verdict_label_vi=verdict_vi,
                is_blocked_or_unverifiable=True,
                routing_reason="Tài liệu bị chặn bot hoặc không rõ nguồn gốc/không xác minh được.",
                submission_reply_message=sub_reply,
                forwarded_post_message="",
            )

        # Build candidate channels (loại trừ kênh nộp tài liệu và kênh hệ thống)
        def is_valid_destination(cand_name: str) -> bool:
            cn = cand_name.lower().replace("・", "-").replace("_", "-")
            return not any(x in cn for x in [
                "nop-tai-lieu", "nộp-tài-liệu", "tra-cuu", "tra-cứu",
                "verify-link", "bot-log", "intake"
            ])

        candidates: List[ChannelProfile] = []
        if category_channels:
            for ch in category_channels:
                c_name = ch if isinstance(ch, str) else getattr(ch, "channel_name", "")
                if not is_valid_destination(c_name):
                    continue
                if isinstance(ch, ChannelProfile):
                    candidates.append(ch)
                else:
                    candidates.append(ChannelAutoDetector.detect_channel_profile(str(ch)))

        if not candidates:
            candidates = [c for c in ChannelRegistry.STANDARD_CHANNELS.values() if is_valid_destination(c.channel_name)]

        for c in candidates:
            c.category_id = resolved_cat_id

        # Deterministic scoring
        def score_candidate(cand: ChannelProfile) -> float:
            score = 0.0

            # A. Lesson Plan rule
            if report.document_category == DocumentCategory.LESSON_PLAN:
                if cand.required_category == DocumentCategory.LESSON_PLAN:
                    score += 200.0
                else:
                    score -= 80.0
            else:
                if cand.required_category is not None:
                    score -= 150.0

            # B. Subject matching
            if subj in cand.allowed_subjects:
                if len(cand.allowed_subjects) == 1:
                    score += 70.0
                else:
                    score += 40.0
            elif cand.is_wildcard:
                score += 15.0
            else:
                score -= 100.0

            # C. Track matching (thuong < hsg < chuyên)
            if cand.allowed_tracks:
                if track in cand.allowed_tracks:
                    score += 55.0 if track == ExamTrackTier.CHUYEN else 50.0  # Chuyên gets high priority
                else:
                    score -= 40.0  # Channel restricted to other tracks
            else:
                score += 10.0      # Generic track channel

            # D. Grade level matching (Lớp 12, 11, 10, 9, ...)
            if cand.allowed_grades:
                if grade in cand.allowed_grades:
                    score += 45.0  # Exact grade match (e.g. Lớp 12 -> #toan-12)
                elif grade != GradeLevel.UNKNOWN:
                    score -= 45.0  # Channel restricted to other grades
            else:
                score += 2.0       # Generic grade channel (safe fallback)

            # E. Non-wildcard preference
            if not cand.is_wildcard:
                score += 10.0

            return score

        scored = [(score_candidate(c), c) for c in candidates]
        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best_channel = scored[0]

        if best_score <= 10.0:
            wildcards = [c for c in candidates if c.is_wildcard]
            best_channel = wildcards[0] if wildcards else ChannelRegistry.STANDARD_CHANNELS["tai-lieu-chung"]

        target_name = best_channel.channel_name
        target_id = best_channel.channel_id

        diff = report.difficulty_assessment
        if diff.score % 1 == 0:
            diff_score_str = f"{int(diff.score)}/10"
        else:
            diff_score_str = f"{diff.score:.1f}/10"
        diff_str = f"{diff_score_str} ({diff.tier_label_vi})"

        q_count = report.pass2.question_count if hasattr(report, "pass2") and hasattr(report.pass2, "question_count") else 0
        keys_str = "Có đáp án" if hasattr(report, "pass2") and report.pass2.has_answer_keys else "Chưa kèm đáp án"

        # Kiểu loại môn học (Programming Language / Specialized Sub-type)
        lang_band = getattr(report, "language_proficiency_band", None)
        sub_type = getattr(report, "programming_language", None)
        if not sub_type:
            from .hybrid_classifier import detect_programming_language
            sub_type = detect_programming_language(getattr(report, "full_text", "") or "", report.file_name)
        if not sub_type and lang_band:
            sub_type = lang_band

        if sub_type:
            display_sub = sub_type if any(k in sub_type.upper() for k in ["IELTS", "TOEIC", "TRKI", "HSK", "JLPT", "TOPIK", "DELF"]) else sub_type.lower()
            sub_type_line = f"- Kiểu loại môn học : {display_sub}\n"
        else:
            sub_type_line = ""

        # Khối lớp hiển thị
        if grade in (GradeLevel.UNKNOWN, GradeLevel.GENERAL_ACADEMIC):
            grade_display = "Chung / Chưa rõ lớp"
        else:
            grade_display = grade_vi

        # Thể loại đề thi phong phú
        detailed_track = getattr(report, "detailed_exam_track", None)
        if not detailed_track:
            from .core import detect_detailed_exam_track
            raw_t = getattr(report, "full_text", "") or ""
            if not raw_t and hasattr(report, "pass1"):
                raw_t = getattr(report.pass1, "raw_text_sample", "") or ""
            detailed_track = detect_detailed_exam_track(
                file_name=report.file_name,
                text=raw_t,
                base_track=track,
                grade=grade,
                doc_cat=report.document_category,
            )

        year_line = f"• Năm học: **{report.academic_year}**\n" if getattr(report, "academic_year", None) else ""
        school_line = f"• Đơn vị ra đề: **{report.school_or_department}**\n" if getattr(report, "school_or_department", None) else ""

        # Hình thức trình bày đề thi
        format_display = None
        if hasattr(report, "pass2") and report.pass2:
            p2 = report.pass2
            if getattr(p2, "curriculum", None) and getattr(p2.curriculum, "moet_2025_compliant", False):
                format_display = "Chuẩn Bộ GD&ĐT 2025 (Trắc nghiệm + Đúng/Sai + Điền khuyết)"
            elif ExamType.COMPETITIVE_PROGRAMMING in getattr(p2, "candidate_exam_types", []):
                format_display = "Tự luận lập trình / Giải thuật CP (I/O: stdin/stdout)"
            elif getattr(p2, "options_count", 0) > 0 and getattr(p2, "question_count", 0) > 0:
                format_display = f"Trắc nghiệm khách quan ({p2.question_count} câu hỏi)"
            elif getattr(p2, "question_count", 0) > 0:
                format_display = f"Đề thi tự luận / Bài tập ôn luyện ({p2.question_count} bài)"
            elif report.document_category == DocumentCategory.LESSON_PLAN:
                format_display = "Kế hoạch bài dạy / Giáo án (Chuẩn CV 5512)"

        format_line = f"• Hình thức: **{format_display}**\n" if format_display else ""

        # Tình trạng đáp án & lời giải
        has_ans = getattr(report.pass2, "has_answer_keys", False) if hasattr(report, "pass2") and report.pass2 else False
        has_sol = getattr(report.pass2, "has_detailed_solutions", False) if hasattr(report, "pass2") and report.pass2 else False
        if has_sol:
            answer_line = "• Lời giải: **Có đáp án & Hướng dẫn giải chi tiết ✅**\n"
        elif has_ans:
            answer_line = "• Lời giải: **Có kèm bảng đáp án ✅**\n"
        else:
            answer_line = "• Lời giải: **Đề bài độc lập (chưa kèm đáp án)**\n"

        # Quy mô tệp & số trang
        p_count = getattr(report.pass1, "page_count", 0) if hasattr(report, "pass1") and report.pass1 else 0
        raw_type = getattr(report.pass1, "raw_file_type", "TỆP") if hasattr(report, "pass1") and report.pass1 else "TỆP"
        size_bytes = getattr(report, "file_size_bytes", 0)
        size_str = f"{size_bytes / 1024:.1f} KB" if size_bytes < 1024 * 1024 else f"{size_bytes / (1024 * 1024):.1f} MB"
        if p_count > 1:
            scale_line = f"• Quy mô tệp: **{raw_type} ({p_count} trang • {size_str})**\n"
        elif size_bytes > 0:
            scale_line = f"• Quy mô tệp: **{raw_type} ({size_str})**\n"
        else:
            scale_line = ""

        # Message posted back to SUBMISSION CHANNEL (1535278288828633138)
        # (bot gửi RIÊNG QUA DM cho người nộp — kèm verdict + độ tin cậy quét kỹ)
        try:
            conf_pct = f"{float(report.confidence_score) * 100:.0f}%" if getattr(report, "confidence_score", None) is not None else "?"
        except (TypeError, ValueError):
            conf_pct = "?"
        verdict_line = f"• Thẩm định: **{verdict_vi}** (độ tin cậy {conf_pct}, quét kỹ)\n"
        sub_reply = (
            f"📥 **[KÊNH NỘP TÀI LIỆU | ID: `{resolved_sub_id}`] TIẾP NHẬN & PHÂN LOẠI THÀNH CÔNG**\n"
            f"{author_line_reply}"
            f"• Tệp / Liên kết: `{report.file_name}`\n"
            f"{verdict_line}"
            f"• Môn học: **{subj_vi}**\n"
            f"{sub_type_line}"
            f"• Khối lớp: **{grade_display}**\n"
            f"{year_line}"
            f"{school_line}"
            f"• Thể loại: **{detailed_track}**\n"
            f"• Độ khó: **{diff_str}**\n"
            f"{format_line}"
            f"{answer_line}"
            f"{scale_line}"
            f"──────────────────────────────────────────────\n"
            f"👉 **ĐÃ TỰ ĐỘNG PHÂN LOẠI & CHUYỂN TIẾP:**\n"
            f"Tài liệu đã được lưu trữ sang kênh: **#{target_name}** trong Thư mục Phân Loại [ID: `{resolved_cat_id}`]!"
        )

        # Message posted to TARGET CHANNEL in CATEGORY (1534147951797080174)
        target_mention_sub = f"<#{resolved_sub_id}>" if resolved_sub_id.isdigit() else f"#{resolved_sub_id}"
        target_post = (
            f"📁 **[TÀI LIỆU ĐÃ PHÂN LOẠI | THƯ MỤC `{resolved_cat_id}`]**\n"
            f"*(Chuyển tiếp tự động từ Kênh Nộp Tài Liệu: {target_mention_sub})*\n"
            f"{author_line_post}"
            f"• Tệp / Link: `{report.file_name}`\n"
            f"• Môn học: **{subj_vi}**\n"
            f"{sub_type_line}"
            f"• Khối lớp: **{grade_display}**\n"
            f"{year_line}"
            f"{school_line}"
            f"• Thể loại: **{detailed_track}**\n"
            f"• Độ khó: **{diff_str}**\n"
            f"{format_line}"
            f"{answer_line}"
            f"{scale_line}"
        ).rstrip()

        grade_str_part = f", khối '{grade_vi}'" if grade != GradeLevel.UNKNOWN else ""
        reason = f"Khớp môn {subj_vi}{grade_str_part} và thể loại '{track_vi}' với kênh #{target_name}"

        return SubmissionRoutingResult(
            submission_channel_id=resolved_sub_id,
            target_category_id=resolved_cat_id,
            target_channel_name=target_name,
            target_channel_id=target_id,
            detected_subject=subj,
            detected_subject_vi=subj_vi,
            detected_grade=grade,
            detected_grade_vi=grade_vi,
            exam_track=track,
            exam_track_label_vi=track_vi,
            verdict=verdict,
            verdict_label_vi=verdict_vi,
            is_blocked_or_unverifiable=False,
            routing_reason=reason,
            language_proficiency_band=lang_band,
            submission_reply_message=sub_reply,
            forwarded_post_message=target_post,
        )


class ChannelComplianceValidator:
    """Validates an InspectionReport against a channel's designated subject rules."""

    @classmethod
    def validate(
        cls,
        report: InspectionReport,
        channel_input: Union[str, ChannelProfile],
        category_id: Optional[Union[str, int]] = None,
    ) -> ChannelComplianceResult:
        """
        Checks whether the inspected document conforms to the designated channel.
        Generates bot-friendly warnings and channel relocation suggestions.
        """
        if isinstance(channel_input, ChannelProfile):
            profile = channel_input
        else:
            profile = ChannelAutoDetector.detect_channel_profile(str(channel_input))

        ch_name = profile.channel_name
        resolved_cat_id = str(category_id) if category_id is not None else (profile.category_id or DEFAULT_TARGET_CATEGORY_ID)
        actual_subj = report.detected_subject
        actual_subj_vi = ChannelRegistry.SUBJECT_VI_NAMES.get(actual_subj, actual_subj.value)

        # 0. Check for unverifiable or blocked document
        from .models import VerificationVerdict
        if report.verdict == VerificationVerdict.UNVERIFIABLE_FAILED:
            bot_msg = (
                f"❌ **[KÊNH #{ch_name} | THƯ MỤC `{resolved_cat_id}`] THẨM ĐỊNH THẤT BẠI!**\n"
                f"• Tệp / Liên kết: `{report.file_name}`\n"
                f"• Trạng thái: **{report.verdict_label_vi}**\n"
                f"• Chi tiết: Không thể đọc được nội dung hoặc tài liệu bị chặn ('không rõ nguồn gốc').\n"
                f"👉 Vui lòng kiểm tra lại quyền truy cập hoặc tải tệp trực tiếp lên kênh!"
            )
            return ChannelComplianceResult(
                channel_name=ch_name,
                category_id=resolved_cat_id,
                is_compliant=False,
                expected_subjects=profile.allowed_subjects,
                actual_subject=actual_subj,
                suggested_channels=[],
                warning_message=f"Tài liệu không xác minh được hoặc không rõ nguồn gốc trong kênh #{ch_name}",
                bot_reply_formatted=bot_msg,
            )

        # 1. Category-specific check (e.g. #giao-an-5512)
        if profile.required_category is not None:
            if report.document_category != profile.required_category:
                suggested_ch = "de-toan" if actual_subj == Subject.MATHEMATICS else ChannelRegistry.SUBJECT_DEFAULT_CHANNELS.get(actual_subj, "tai-lieu-chung")
                warning = (
                    f"CẢNH BÁO ĐĂNG SAI KÊNH: Kênh '#{ch_name}' (Thư mục {resolved_cat_id}) chỉ dành cho "
                    f"'{profile.required_category.value}', nhưng tệp tải lên là dạng "
                    f"'{report.document_category.value}' (Môn {actual_subj_vi})!"
                )
                bot_msg = (
                    f"⚠️ **[CẢNH BÁO ĐĂNG SAI KÊNH #{ch_name}]**\n"
                    f"• Tệp tải lên: `{report.file_name}`\n"
                    f"• Định dạng thực tế: **{report.document_category.value}** ({actual_subj_vi})\n"
                    f"• Yêu cầu của kênh: Kênh này chỉ tiếp nhận **{profile.required_category.value}**.\n"
                    f"👉 **Gợi ý:** Vui lòng chuyển bài đăng sang kênh `#{suggested_ch}` trong thư mục!"
                )
                return ChannelComplianceResult(
                    channel_name=ch_name,
                    category_id=resolved_cat_id,
                    is_compliant=False,
                    expected_subjects=profile.allowed_subjects,
                    actual_subject=actual_subj,
                    suggested_channels=[suggested_ch],
                    warning_message=warning,
                    bot_reply_formatted=bot_msg,
                )

        # 1b. Track-specific check (e.g. #chuyen-toan vs đề thường)
        if profile.allowed_tracks and report.exam_track not in profile.allowed_tracks:
            expected_tracks_str = ", ".join([t.value for t in profile.allowed_tracks])
            suggested_ch = "de-toan" if actual_subj == Subject.MATHEMATICS else ChannelRegistry.SUBJECT_DEFAULT_CHANNELS.get(actual_subj, "tai-lieu-chung")
            warning = (
                f"CẢNH BÁO THỂ LOẠI: Kênh '#{ch_name}' chỉ dành cho thể loại '{expected_tracks_str}', "
                f"nhưng đề tải lên là thể loại '{report.exam_track_label_vi}' (Môn {actual_subj_vi})!"
            )
            bot_msg = (
                f"⚠️ **[CẢNH BÁO THỂ LOẠI ĐỀ #{ch_name}]**\n"
                f"• Tệp tải lên: `{report.file_name}`\n"
                f"• Môn học: **{actual_subj_vi}**\n"
                f"• Thể loại đề: **{report.exam_track_label_vi}**\n"
                f"• Yêu cầu của kênh: Kênh này chỉ tiếp nhận thể loại **{expected_tracks_str}**.\n"
                f"👉 **Gợi ý:** Vui lòng chuyển bài đăng sang kênh `#{suggested_ch}`!"
            )
            return ChannelComplianceResult(
                channel_name=ch_name,
                category_id=resolved_cat_id,
                is_compliant=False,
                expected_subjects=profile.allowed_subjects,
                actual_subject=actual_subj,
                expected_grades=profile.allowed_grades,
                actual_grade=report.grade_level,
                suggested_channels=[suggested_ch],
                warning_message=warning,
                bot_reply_formatted=bot_msg,
            )

        # 1c. Grade-specific check (e.g. #toan-12 vs Lớp 10)
        grade = report.grade_level
        grade_vi = report.grade_level_label_vi or GRADE_LEVEL_VI_NAMES.get(grade, grade.value)
        if (
            profile.allowed_grades
            and grade != GradeLevel.UNKNOWN
            and grade not in profile.allowed_grades
        ):
            expected_grades_str = ", ".join([GRADE_LEVEL_VI_NAMES.get(g, g.value) for g in profile.allowed_grades])
            suggested_ch = "de-toan" if actual_subj == Subject.MATHEMATICS else ChannelRegistry.SUBJECT_DEFAULT_CHANNELS.get(actual_subj, "tai-lieu-chung")
            warning = (
                f"CẢNH BÁO KHỐI LỚP: Kênh '#{ch_name}' chỉ dành cho khối '{expected_grades_str}', "
                f"nhưng đề tải lên là khối '{grade_vi}' (Môn {actual_subj_vi})!"
            )
            bot_msg = (
                f"⚠️ **[CẢNH BÁO KHỐI LỚP #{ch_name}]**\n"
                f"• Tệp tải lên: `{report.file_name}`\n"
                f"• Môn học: **{actual_subj_vi}**\n"
                f"• Khối lớp thực tế: **{grade_vi}**\n"
                f"• Yêu cầu của kênh: Kênh này chỉ tiếp nhận khối **{expected_grades_str}**.\n"
                f"👉 **Gợi ý:** Vui lòng chuyển bài đăng sang kênh `#{suggested_ch}` hoặc gửi qua Kênh Nộp Tài Liệu (<#{DEFAULT_SUBMISSION_CHANNEL_ID}>)!"
            )
            return ChannelComplianceResult(
                channel_name=ch_name,
                category_id=resolved_cat_id,
                is_compliant=False,
                expected_subjects=profile.allowed_subjects,
                actual_subject=actual_subj,
                expected_grades=profile.allowed_grades,
                actual_grade=grade,
                suggested_channels=[suggested_ch],
                warning_message=warning,
                bot_reply_formatted=bot_msg,
            )

        detailed_track = getattr(report, "detailed_exam_track", None)
        if not detailed_track:
            detailed_track = report.exam_track_label_vi

        # 2. Wildcard channel check -> Always passes
        if profile.is_wildcard:
            bot_msg = (
                f"✅ **[KÊNH TỔNG HỢP #{ch_name} | THƯ MỤC `{resolved_cat_id}`]** Tệp tin được chấp nhận!\n"
                f"• Tài liệu: `{report.file_name}`\n"
                f"• Môn học: **{actual_subj_vi}**\n"
                f"• Khối lớp: **{grade_vi}**\n"
                f"• Thể loại: **{detailed_track}**\n"
                f"• Định dạng: **{report.document_category.value}**"
            )
            return ChannelComplianceResult(
                channel_name=ch_name,
                category_id=resolved_cat_id,
                is_compliant=True,
                expected_subjects=profile.allowed_subjects,
                actual_subject=actual_subj,
                expected_grades=profile.allowed_grades,
                actual_grade=grade,
                bot_reply_formatted=bot_msg,
            )

        # 3. Specific Subject match check
        if actual_subj in profile.allowed_subjects:
            diff_score = f"{report.difficulty_assessment.score:.1f}/10" if report.difficulty_assessment.score % 1 != 0 else f"{int(report.difficulty_assessment.score)}/10"
            bot_msg = (
                f"✅ **[KÊNH #{ch_name} | THƯ MỤC `{resolved_cat_id}`] HỢP LỆ VÀ ĐÚNG KÊNH!**\n"
                f"• Tài liệu: `{report.file_name}`\n"
                f"• Môn học: **{actual_subj_vi}** (Khớp với danh sách môn của kênh)\n"
                f"• Khối lớp: **{grade_vi}**\n"
                f"• Thể loại: **{detailed_track}**\n"
                f"• Độ khó: **{diff_score}** ({report.difficulty_assessment.tier_label_vi})"
            )
            return ChannelComplianceResult(
                channel_name=ch_name,
                category_id=resolved_cat_id,
                is_compliant=True,
                expected_subjects=profile.allowed_subjects,
                actual_subject=actual_subj,
                expected_grades=profile.allowed_grades,
                actual_grade=grade,
                bot_reply_formatted=bot_msg,
            )

        # 4. MISMATCH: Document subject does NOT match channel's designated subjects!
        expected_names = [ChannelRegistry.SUBJECT_VI_NAMES.get(s, s.value) for s in profile.allowed_subjects]
        expected_str = ", ".join(expected_names)

        suggested_ch = ChannelRegistry.SUBJECT_DEFAULT_CHANNELS.get(actual_subj, "tai-lieu-chung")
        warning = (
            f"CẢNH BÁO ĐĂNG SAI KÊNH: Kênh '#{ch_name}' (Thư mục {resolved_cat_id}) chỉ tiếp nhận môn: {expected_str}, "
            f"nhưng tài liệu tải lên thực tế 100% là môn {actual_subj_vi} (Thể loại: {report.exam_track_label_vi})!"
        )
        bot_msg = (
            f"🚨 **[CẢNH BÁO ĐĂNG SAI KÊNH #{ch_name} | THƯ MỤC `{resolved_cat_id}`]**\n"
            f"• Tệp tải lên: `{report.file_name}`\n"
            f"• Môn thực tế: **{actual_subj_vi}** ({actual_subj.value})\n"
            f"• Thể loại: **{report.exam_track_label_vi}**\n"
            f"• Danh sách môn của kênh: Chỉ nhận **{expected_str}**.\n"
            f"👉 **Gợi ý tự động:** Vui lòng chuyển bài đăng sang đúng kênh `#{suggested_ch}` trong thư mục này, hoặc gửi qua Kênh Nộp Tài Liệu (<#{DEFAULT_SUBMISSION_CHANNEL_ID}>) để được bot tự động phân loại!"
        )

        return ChannelComplianceResult(
            channel_name=ch_name,
            category_id=resolved_cat_id,
            is_compliant=False,
            expected_subjects=profile.allowed_subjects,
            actual_subject=actual_subj,
            suggested_channels=[suggested_ch],
            warning_message=warning,
            bot_reply_formatted=bot_msg,
        )



class BotInspectorAdapter:
    """
    High-level bot adapter for Discord bots, Telegram bots, or Slack apps.
    Allows 1-line integration with channel and folder (category) auto-inspection.
    """

    @classmethod
    def inspect_in_channel(
        cls,
        file_path_or_bytes: Union[str, bytes],
        channel_name: str,
        category_id: Optional[Union[str, int]] = DEFAULT_TARGET_CATEGORY_ID,
        file_name: Optional[str] = None,
    ) -> InspectionReport:
        """
        Inspects document with automatic channel and category binding and compliance verification.
        """
        from .core import DocumentInspector

        return DocumentInspector.inspect(
            file_path_or_bytes=file_path_or_bytes,
            file_name=file_name,
            channel=channel_name,
            category_id=category_id,
        )

    @classmethod
    def inspect_and_route_submission(
        cls,
        file_path_or_bytes: Union[str, bytes],
        category_channels: Optional[List[Union[str, ChannelProfile]]] = None,
        category_id: Optional[Union[str, int]] = DEFAULT_TARGET_CATEGORY_ID,
        submission_channel_id: Optional[Union[str, int]] = DEFAULT_SUBMISSION_CHANNEL_ID,
        file_name: Optional[str] = None,
        author_mention: Optional[str] = None,
        author_name: Optional[str] = None,
        deep: bool = False,
    ) -> Tuple[InspectionReport, SubmissionRoutingResult]:
        """
        1-Line Bot Integration for Submission Channel (1535278288828633138):
        Inspects document/URL and immediately routes to Category (1534147951797080174).
        deep=True: quét kỹ chính xác tối đa (khuyên dùng cho nộp đề).
        """
        from .core import DocumentInspector

        report = DocumentInspector.inspect(
            file_path_or_bytes=file_path_or_bytes,
            file_name=file_name,
            category_id=category_id,
            deep=deep,
        )
        routing = CategoryDirectoryManager.route_submission(
            report=report,
            category_channels=category_channels,
            category_id=category_id,
            submission_channel_id=submission_channel_id,
            author_mention=author_mention,
            author_name=author_name,
        )
        return report, routing

