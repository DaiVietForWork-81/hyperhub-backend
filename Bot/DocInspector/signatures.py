"""
Comprehensive Structural signatures, Regex patterns, Unicode blocks,
and Weighted Domain Lexicons for DocInspector.
100% Deterministic, Zero AI, Multi-disciplinary & Multi-language.
"""

from __future__ import annotations

import re
from typing import Dict, List, Pattern

# ============================================================================
# UNICODE SCRIPTS & LANGUAGE REGEX
# ============================================================================

RE_JAPANESE_KANA: Pattern = re.compile(r"[\u3040-\u309f\u30a0-\u30ff]")
RE_KOREAN_HANGUL: Pattern = re.compile(r"[\uac00-\ud7af]")
RE_CHINESE_CJK: Pattern = re.compile(r"[\u4e00-\u9fa5]")
RE_VIETNAMESE_ACCENTS: Pattern = re.compile(
    r"[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]",
    re.IGNORECASE,
)
RE_FRENCH_ACCENTS: Pattern = re.compile(r"[àâæçéèêëîïôœùûüÿ]", re.IGNORECASE)
RE_GERMAN_UMLAUTS: Pattern = re.compile(r"[äöüß]", re.IGNORECASE)
RE_CYRILLIC: Pattern = re.compile(r"[\u0400-\u04ff]")

# Legacy Vietnamese font mojibake signatures (TCVN3 / VNI-Windows)
RE_TCVN3_MOJIBAKE: Pattern = re.compile(r"[\x80-\xff]{2,}|(?:¸|µ|¶|·|¹|â|ª|«|¬|­|®|¯|±)")
RE_VNI_MOJIBAKE: Pattern = re.compile(r"\b[a-zA-Z]+(?:ù|ú|û|ü|ý|ÿ|ñ)[a-zA-Z]*\b")

# ============================================================================
# PASS 2: STRUCTURAL EXAM & CURRICULUM FINGERPRINTS
# ============================================================================

# MOET 2025 New 3-Part Exam Structure (Thông tư mới Bộ GD&ĐT)
RE_MOET_PART1: Pattern = re.compile(
    r"(?i)\b(?:phần\s+i|phần\s+1|part\s+1)\s*[:.]\s*(?:câu\s*trắc\s*nghiệm\s*nhiều\s*phương\s*án|trắc\s*nghiệm\s*nhiều\s*lựa\s*chọn|multiple\s*choice)",
)
RE_MOET_PART2: Pattern = re.compile(
    r"(?i)\b(?:phần\s+ii|phần\s+2|part\s+2)\s*[:.]\s*(?:câu\s*trắc\s*nghiệm\s*đúng\s*sai|trắc\s*nghiệm\s*đúng\s*[-/]?\s*sai|true\s*[-/]?\s*false)",
)
RE_MOET_PART3: Pattern = re.compile(
    r"(?i)\b(?:phần\s+iii|phần\s+3|part\s+3)\s*[:.]\s*(?:câu\s*trắc\s*nghiệm\s*trả\s*lời\s*ngắn|trả\s*lời\s*ngắn|điền\s*khuyết|short\s*answer)",
)

# Textbooks & Curriculum Series
RE_CURRICULUM_SERIES: Pattern = re.compile(
    r"(?i)\b(?:kết\s*nối\s*tri\s*thức\s*với\s*cuộc\s*sống|cánh\s*diều|chân\s*trời\s*sáng\s*tạo|cùng\s*khám\s*phá|cv\s*5512|công\s*văn\s*5512)\b",
)

# Grade Level Patterns (hỗ trợ cả có dấu & không dấu cho OCR/scan mất dấu)
RE_GRADE_12: Pattern = re.compile(
    r"(?i)\b(?:lớp\s*12|lop\s*12|khối\s*12|khoi\s*12|k12|thpt\s*quốc\s*gia|thpt\s*quoc\s*gia|tốt\s*nghiệp\s*thpt|tot\s*nghiep\s*thpt|ôn\s*thi\s*đại\s*học|on\s*thi\s*dai\s*hoc|kỳ\s*thi\s*thpt|ky\s*thi\s*thpt|toán\s*12|toan\s*12|vật\s*lý\s*12|vat\s*ly\s*12|hóa\s*học\s*12|hoa\s*hoc\s*12|sinh\s*học\s*12|sinh\s*hoc\s*12|ngữ\s*văn\s*12|ngu\s*van\s*12|tiếng\s*anh\s*12|tieng\s*anh\s*12|tin\s*(?:học\s*)?12|tin\s*hoc\s*12)\b",
)
RE_GRADE_11: Pattern = re.compile(
    r"(?i)\b(?:lớp\s*11|lop\s*11|khối\s*11|khoi\s*11|k11|toán\s*11|toan\s*11|vật\s*lý\s*11|vat\s*ly\s*11|hóa\s*học\s*11|hoa\s*hoc\s*11|sinh\s*học\s*11|sinh\s*hoc\s*11|ngữ\s*văn\s*11|ngu\s*van\s*11|tiếng\s*anh\s*11|tieng\s*anh\s*11|tin\s*(?:học\s*)?11|tin\s*hoc\s*11)\b",
)
RE_GRADE_10: Pattern = re.compile(
    r"(?i)\b(?:lớp\s*10|lop\s*10|khối\s*10|khoi\s*10|k10|tuyển\s*sinh\s*(?:vào\s*)?10|tuyen\s*sinh\s*(?:vao\s*)?10|vào\s*lớp\s*10|vao\s*lop\s*10|toán\s*10|toan\s*10|vật\s*lý\s*10|vat\s*ly\s*10|hóa\s*học\s*10|hoa\s*hoc\s*10|sinh\s*học\s*10|sinh\s*hoc\s*10|ngữ\s*văn\s*10|ngu\s*van\s*10|tiếng\s*anh\s*10|tieng\s*anh\s*10|tin\s*(?:học\s*)?10|tin\s*hoc\s*10)\b",
)
RE_GRADE_9: Pattern = re.compile(
    r"(?i)\b(?:lớp\s*9|lop\s*9|khối\s*9|khoi\s*9|k9|toán\s*9|toan\s*9|ngữ\s*văn\s*9|ngu\s*van\s*9|tiếng\s*anh\s*9|tieng\s*anh\s*9|khtn\s*9|ôn\s*thi\s*(?:vào\s*)?10|on\s*thi\s*(?:vao\s*)?10)\b",
)
RE_GRADE_8: Pattern = re.compile(
    r"(?i)\b(?:lớp\s*8|lop\s*8|khối\s*8|khoi\s*8|k8|toán\s*8|toan\s*8|ngữ\s*văn\s*8|ngu\s*van\s*8|khtn\s*8)\b",
)
RE_GRADE_7: Pattern = re.compile(
    r"(?i)\b(?:lớp\s*7|lop\s*7|khối\s*7|khoi\s*7|k7|toán\s*7|toan\s*7|ngữ\s*văn\s*7|ngu\s*van\s*7|khtn\s*7)\b",
)
RE_GRADE_6: Pattern = re.compile(
    r"(?i)\b(?:lớp\s*6|lop\s*6|khối\s*6|khoi\s*6|k6|toán\s*6|toan\s*6|ngữ\s*văn\s*6|ngu\s*van\s*6|khtn\s*6)\b",
)
RE_GRADE_MIDDLE: Pattern = re.compile(
    r"(?i)\b(?:lớp\s*[6-9]|lop\s*[6-9]|khối\s*[6-9]|khoi\s*[6-9]|thcs|cấp\s*2|cap\s*2|trung\s*học\s*cơ\s*sở|trung\s*hoc\s*co\s*so)\b",
)
RE_GRADE_PRIMARY: Pattern = re.compile(
    r"(?i)\b(?:lớp\s*[1-5]|lop\s*[1-5]|khối\s*[1-5]|khoi\s*[1-5]|tiểu\s*học|tieu\s*hoc|cấp\s*1|cap\s*1)\b",
)
RE_GRADE_OLYMPIAD: Pattern = re.compile(
    r"(?i)\b(?:học\s*sinh\s*giỏi\s*quốc\s*gia|hoc\s*sinh\s*gioi\s*quoc\s*gia|hsg\s*quốc\s*gia|hsg\s*quoc\s*gia|olympic|chuyên\s*(?:toán|tin|lý|hóa|sinh|anh|văn)|chuyen\s*(?:toan|tin|ly|hoa|sinh|anh|van)|hsg\s*tỉnh|hsg\s*tinh|vnoi|icpc|chọn\s*đội\s*tuyển|chon\s*doi\s*tuyen|tst)\b",
)
RE_GRADE_UNIVERSITY: Pattern = re.compile(
    r"(?i)\b(?:đại\s*học|dai\s*hoc|cao\s*đẳng|cao\s*dang|sinh\s*viên|sinh\s*vien|học\s*phần|hoc\s*phan|tín\s*chỉ|tin\s*chi|giáo\s*trình\s*đại\s*học|giao\s*trinh\s*dai\s*hoc)\b",
)


# Question and Option Extraction Patterns (hỗ trợ không dấu cho OCR)
RE_QUESTION_HEADING: Pattern = re.compile(
    r"(?i)(?:^|\n)\s*(?:câu|cau|bài|bai|question|problem|task)\s+(\d+)[\s*.:\)]+",
)
RE_MCQ_FOUR_OPTIONS: Pattern = re.compile(
    r"(?:^|[\s\t\n])([A-D])[.:)]\s*(.*?)(?=(?:[\s\t]+[A-D][.:)]\s+)|\n\s*[A-D][.:)]\s*|\n\s*(?:câu|cau|bài|bai|question|\d+[\.\)])|$)",
    re.DOTALL,
)
RE_TRUE_FALSE_SUBITEMS: Pattern = re.compile(
    r"(?i)(?:^|[\s\t\n])([a-d])[\.\)]\s*(.*?)(?=(?:[\s\t]+[a-d][\.\)]\s*)|\n\s*[a-d][\.\)]\s*|\n\s*(?:câu|cau|bài|bai|question|\d+[\.\)])|$)",
    re.DOTALL,
)

# Competitive Programming (Chuyên Tin / Olympic)
RE_COMP_TIME_LIMIT: Pattern = re.compile(
    r"(?i)\b(?:giới\s*hạn\s*thời\s*gian|thời\s*gian\s*chạy|time\s*limit)\s*[:：]\s*(\d+(?:\.\d+)?)\s*(?:s|giây|second|ms)",
)
RE_COMP_MEM_LIMIT: Pattern = re.compile(
    r"(?i)\b(?:giới\s*hạn\s*bộ\s*nhớ|bộ\s*nhớ|memory\s*limit)\s*[:：]\s*(\d+)\s*(?:mb|megabyte|gb|kb)",
)
RE_COMP_IO_FILES: Pattern = re.compile(
    r"(?i)(?:\b[a-zA-Z0-9_]+\.(?:inp|out|cpp|pas|in)\b|standard\s+(?:input|output)|stdin|stdout|file\s+vào\s*[:：]|file\s+ra\s*[:：])",
)
RE_COMP_SUBTASKS: Pattern = re.compile(
    r"(?i)\b(?:subtask\s*\d+|testcase|test\s*chấm|ràng\s*buộc\s*dữ\s*liệu|ràng\s*buộc|độ\s*phức\s*tạp\s*thuật\s*toán|o\([nmlogk\^2\+ ]+\))",
)
RE_COMP_CODE_TOKENS: Pattern = re.compile(
    r"(?:#include\s*<bits/stdc\+\+\.h>|#include\s*<iostream>|std::vector|int\s+main\(\)|fast_io|cin\.tie|sys\.stdin\.readline|def\s+solve\(\)|program\s+[a-zA-Z0-9_]+;|long\s+long|freopen)",
)

# IELTS & Cambridge Tests
RE_IELTS_READING_PASSAGE: Pattern = re.compile(r"(?i)\breading\s+passage\s+[123]\b")
RE_IELTS_TFNG: Pattern = re.compile(r"(?i)\b(?:true\s*/\s*false\s*/\s*not\s*given|yes\s*/\s*no\s*/\s*not\s*given)\b")
RE_IELTS_QUESTION_RANGE: Pattern = re.compile(r"(?i)\bquestions?\s+\d+\s*(?:[-–—]|to)\s*\d+\b")
RE_IELTS_HEADINGS: Pattern = re.compile(r"(?i)\b(?:list\s+of\s+headings|matching\s+information|write\s+no\s+more\s+than)\b")
RE_IELTS_WRITING_TASKS: Pattern = re.compile(r"(?i)\b(?:ielts\s+)?writing\s+task\s+[12]\b|\byou\s+should\s+spend\s+about\s+(?:20|40)\s+minutes\b")

# Specialized English / Chuyên Anh / HSG
RE_ENG_WORD_FORMATION: Pattern = re.compile(
    r"(?i)\b(?:word\s*form(?:ation)?|give\s+(?:the\s+)?correct\s+form|supply\s+(?:the\s+)?correct\s+form|"
    r"use\s+(?:the\s+)?correct\s+form|put\s+(?:the\s+)?words?\s+in(?:to)?\s+(?:the\s+)?correct\s+form|"
    r"form\s+of\s+the\s+words?|bài\s*tập\s*word\s*form|bai\s*tap\s*wordform)\b"
)
RE_ENG_SENTENCE_TRANSFORM: Pattern = re.compile(r"(?i)\b(?:sentence\s+transformation|rewrite\s+the\s+following\s+sentences?|finish\s+each\s+of\s+the\s+following\s+sentences?)\b")
RE_ENG_CLOZE_TEST: Pattern = re.compile(r"(?i)\b(?:cloze\s+test|open\s+cloze|guided\s+cloze|fill\s+(?:in\s+)?each\s+(?:numbered\s+)?blank)\b")
RE_ENG_ERROR_IDENTIFY: Pattern = re.compile(r"(?i)\b(?:error\s+identification|identify\s+the\s+one\s+underlined\s+word|find\s+(?:and\s+correct\s+)?(?:the\s+)?errors?)\b")
RE_ENG_PHONETICS_STRESS: Pattern = re.compile(r"(?i)\b(?:underlined\s+part\s+differs|position\s+of\s+(?:the\s+)?(?:primary\s+)?stress)\b")

# TOEIC Tests
RE_TOEIC_PARTS: Pattern = re.compile(r"(?i)\bpart\s+[1-7]\s*[:.]\s*(?:photographs|question-response|conversations|short\s+talks|incomplete\s+sentences|text\s+completion|reading\s+comprehension)\b")

# JLPT / HSK / TOPIK / TRKI (Nga) / DELF (Pháp)
RE_JLPT_FEATURES: Pattern = re.compile(r"問題\s*[1-9]|正解|聴解|読解|文字・語彙|文法|第[1-5]問|次の文章を読んで|JLPT")
RE_HSK_FEATURES: Pattern = re.compile(r"听力|阅读|书写|第一部分|第二部分|第三部分|选择题|判断对错|HSK\s*[1-6]")
RE_TOPIK_FEATURES: Pattern = re.compile(r"듣기|읽기|쓰기|문항|다음을\s*읽고|맞ng\s*것을\s*고르십시오|TOPIK\s*[I|II]?")
RE_RUSSIAN_FEATURES: Pattern = re.compile(r"(?i)(?:русский\s+язык|тест|задание|упражнение|трки|torfl|trki|вариант\s*\d+|ответы)")
RE_FRENCH_FEATURES: Pattern = re.compile(r"(?i)(?:delf|dalf|compréhension\s+écrite|production\s+écrite|langue\s+française|exercice\s*\d+)")

# Exercise & Worksheet Headings (có dấu + không dấu)
RE_EXERCISE_HEADER: Pattern = re.compile(
    r"(?i)(?:^|\n)\s*(?:exercise|task|part|section|activity|bài\s*tập|bai\s*tap)\s+(\d+|[A-ZIVX]+)[\s*.:\)]+"
)

# Standard Multiple Choice & True/False (có dấu + không dấu)
RE_QUESTION_NUM: Pattern = re.compile(r"(?i)\b(?:câu|cau|bài|bai|question)\s+(\d+)[:.]")
RE_MCQ_OPTIONS: Pattern = re.compile(r"\b([A-D])[.:)]\s+")
RE_MCQ_TRUE_FALSE: Pattern = re.compile(r"(?i)\b(?:[a-d]\)\s*(?:đúng|dung|sai)|(?:đúng|dung|sai)\s*[:：])\b")

# Lesson Plan / Giáo Án (KHBD chuẩn Công văn 5512)
RE_LESSON_PLAN: Pattern = re.compile(
    r"(?i)(?:kế\s*hoạch\s*bài\s*dạy|tiến\s*trình\s*dạy\s*học|mục\s*tiêu\s*bài\s*học|chuẩn\s*kiến\s*thức\s*kỹ\s*năng|"
    r"thiết\s*bị\s*dạy\s*học\s*và\s*học\s*liệu|hoạt\s*động\s*khởi\s*động|hoạt\s*động\s*hình\s*thành\s*kiến\s*thức|"
    r"hoạt\s*động\s*luyện\s*tập|hoạt\s*động\s*vận\s*dụng|yêu\s*cầu\s*cần\s*đạt|giáo\s*án\s*tiết)",
)

# Admin & Contracts
RE_ADMIN_CONTRACT: Pattern = re.compile(
    r"(?i)(?:cộng\s*hòa\s*xã\s*hội\s*chủ\s*nghĩa\s*việt\s*nam|độc\s*lập\s*-\s*tự\s*do\s*-\s*hạnh\s*phúc|"
    r"hợp\s*đồng\s*(?:kinh\s*tế|lao\s*động|dịch\s*vụ|mua\s*bán)|điều\s*\d+\s*[:.]|bên\s*a\s*[:：]|bên\s*b\s*[:：]|căn\s*cứ\s*nghị\s*định)",
)

# Solutions & Answer Keys
RE_SOLUTIONS_BLOCK: Pattern = re.compile(
    r"(?i)(?:lời\s*giải\s*chi\s*tiết|hướng\s*dẫn\s*giải|đáp\s*án\s*chi\s*tiết|bảng\s*đáp\s*án|đáp\s*án\s*và\s*thang\s*điểm|marking\s*scheme|answer\s*keys?)",
)
RE_ANSWER_MATRIX: Pattern = re.compile(
    r"(?:\b\d{1,3}\s*[-.:/]\s*[A-D]\b|\b\d{1,3}[A-D]\b)",
)

# Cognitive Level Cue Patterns
RE_COG_RECOGNITION: Pattern = re.compile(
    r"(?i)\b(?:nêu|chỉ\s*ra|công\s*thức\s*nào|khái\s*niệm|kí\s*hiệu\s*nào|định\s*nghĩa|cho\s*biết|phát\s*biểu\s*nào\s*sau\s*đây\s*đúng)\b",
)
RE_COG_COMPREHENSION: Pattern = re.compile(
    r"(?i)\b(?:tại\s*sao|giải\s*thích|ý\s*nghĩa|so\s*sánh|phân\s*biệt|nhận\s*xét|mối\s*quan\s*hệ|biểu\s*diễn|suy\s*ra)\b",
)
RE_COG_APPLICATION: Pattern = re.compile(
    r"(?i)\b(?:tính|xác\s*định|tìm\s*giá\s*trị|áp\s*dụng|tính\s*thể\s*tích|tính\s*khối\s*lượng|tọa\s*độ|phương\s*trình\s*có\s*nghiệm)\b",
)
RE_COG_HIGH_APPLICATION: Pattern = re.compile(
    r"(?i)\b(?:giá\s*trị\s*lớn\s*nhất|giá\s*trị\s*nhỏ\s*nhất|cực\s*trị|tham\s*số\s*m|bất\s*đẳng\s*thức|tối\s*ưu|chứng\s*minh\s*rằng|số\s*nghiệm\s*phân\s*biệt|bài\s*toán\s*thực\s*tế)\b",
)

# ============================================================================
# PASS 3: EXPANDED DEEP DOMAIN SUBJECT LEXICONS (16 SUBJECTS / DOMAINS)
# ============================================================================

SUBJECT_LEXICONS: Dict[str, Dict[str, float]] = {
    # TOÁN HỌC (CHUYÊN TOÁN & THPTQG)
    "MATHEMATICS": {
        "đạo hàm": 3.5, "tích phân": 4.0, "nguyên hàm": 3.5, "hàm số": 2.5, "tiệm cận": 3.0,
        "hình chóp": 3.0, "lăng trụ": 3.0, "mặt cầu": 3.0, "số phức": 3.5, "bất đẳng thức": 3.0,
        "cauchy": 3.5, "schwarz": 3.5, "đồng dư": 4.0, "phương trình hàm": 4.5, "tổ hợp": 2.5,
        "xác suất": 2.5, "nhị thức newton": 3.0, "cấp số cộng": 2.5, "cấp số nhân": 2.5,
        "tứ giác nội tiếp": 3.0, "trực tâm": 2.5, "đường tròn euler": 4.5, "tỉ số kép": 4.5,
        "vectơ": 2.5, "oxz": 3.0, "oxyz": 3.0, "bảng biến thiên": 3.5, "cực trị": 3.0,
        "giá trị lớn nhất": 2.5, "giá trị nhỏ nhất": 2.5, "nghiệm nguyên": 3.0, "diophantine": 4.5,
        "dirichlet": 4.0, "nguyên lý bù trừ": 4.0, "bất biến": 4.0, "hệ phương trình": 2.5,
        "hình nón": 2.5, "hình trụ": 2.5, "khối đa diện": 3.5, "phép tịnh tiến": 3.0,
        "lượng giác": 2.5, "cosin": 2.0, "sin": 1.5, "logarit": 3.0, "mũ và logarit": 3.5,
        "ma trận": 3.5, "định thức": 3.5, "không gian vectơ": 4.0, "tích vô hướng": 2.5,
    },

    # TIN HỌC (CHUYÊN TIN, THUẬT TOÁN, OLYMPIC)
    "INFORMATICS": {
        "quy hoạch động": 4.5, "đồ thị": 3.5, "dijkstra": 4.5, "floyd": 4.0, "cây khung": 4.0,
        "kruskal": 4.5, "segment tree": 5.0, "fenwick tree": 5.0, "bitmask": 4.5, "bfs": 3.5,
        "dfs": 3.5, "thuật toán": 3.0, "độ phức tạp": 3.5, "mảng": 2.0, "xâu kí tự": 2.5,
        "xâu con": 2.5, "chặt nhị phân": 4.5, "tham lam": 3.5, "quay lui": 3.5, "nhánh cận": 4.0,
        "tập hợp": 1.5, "hàng đợi": 3.0, "ngăn xếp": 3.0, "thời gian chạy": 3.0, "bộ nhớ": 2.5,
        "testcase": 3.5, "subtask": 4.5, "c++": 3.0, "python": 2.5, "pascal": 3.0,
        "file vào": 3.5, "file ra": 3.5, "stdin": 4.0, "stdout": 4.0, "ước số": 1.5,
        "bội số": 1.5, "sàng eratosthenes": 4.5, "bignum": 4.5, "modulo": 3.0, "chữ số": 1.5,
        "khử gauss": 4.0, "bao lồi": 4.5, "cây tiền tố": 4.5, "trie": 4.5, "hashing": 3.5,
        "luồng cực đại": 4.5, "cặp ghép": 4.5, "tarjan": 5.0, "khớp và cầu": 4.5,
        "binary lifting": 5.0, "lca": 4.5, "disjoint set": 4.5, "dsu": 4.5,
    },

    # TIẾNG ANH (IELTS, TOEIC, CHUYÊN ANH, THPTQG)
    "ENGLISH": {
        "reading passage": 4.5, "writing task": 4.5, "true/false/not given": 5.0,
        "yes/no/not given": 5.0, "word formation": 4.5, "sentence transformation": 4.5,
        "cloze test": 4.5, "mark the letter a, b, c": 3.5, "underlined part": 3.5,
        "primary stress": 4.0, "pronunciation": 3.5, "closest in meaning": 3.5,
        "opposite in meaning": 3.5, "phrasal verb": 3.5, "idiom": 3.0, "vocabulary": 2.5,
        "grammar": 2.5, "listening comprehension": 4.0, "multiple choice questions": 2.5,
        "photographs": 3.0, "incomplete sentences": 3.5, "ielts": 4.5, "toeic": 4.5,
        "collocation": 3.5, "conditional sentence": 3.0, "reported speech": 3.0,
        "passive voice": 3.0, "relative clause": 3.0, "inversion": 4.0, "subjunctive": 4.0,
    },

    # VẬT LÝ (CHUYÊN LÝ & THPTQG)
    "PHYSICS": {
        "dao động điều hòa": 4.0, "con lắc lò xo": 4.0, "con lắc đơn": 4.0, "tần số góc": 3.5,
        "biên độ dao động": 3.5, "bước sóng": 3.5, "sóng cơ": 3.5, "giao thoa sóng": 4.0,
        "sóng dừng": 4.0, "dòng điện xoay chiều": 4.0, "cuộn cảm": 3.5, "tụ điện": 3.0,
        "hệ số công suất": 4.0, "máy biến áp": 3.5, "quang điện": 4.0, "quang phổ": 3.5,
        "lượng tử ánh sáng": 4.0, "photon": 4.0, "bán rã": 4.0, "hạt nhân": 3.5,
        "phóng xạ": 4.0, "khối lượng nghỉ": 3.5, "thấu kính": 3.0, "khúc xạ": 3.0,
        "từ trường": 3.0, "cảm ứng từ": 3.5, "lực lorenxơ": 4.5, "suất điện động": 3.5,
        "mạch dao động": 3.5, "sóng điện từ": 3.5, "năng lượng liên kết": 4.0,
        "phản ứng hạt nhân": 4.0, "nhiệt động lực học": 4.0, "động lượng": 3.0,
    },

    # HÓA HỌC (CHUYÊN HÓA & THPTQG)
    "CHEMISTRY": {
        "este": 4.0, "lipit": 3.5, "gluxit": 3.5, "cacbohiđrat": 4.0, "glucozơ": 3.5,
        "saccarozơ": 3.5, "amin": 3.5, "amino axit": 4.0, "peptit": 4.5, "protein": 3.5,
        "polime": 3.5, "kim loại kiềm": 4.0, "kim loại kiềm thổ": 4.0, "nhôm": 2.5,
        "nhiệt nhôm": 4.0, "sắt": 2.5, "crôm": 3.5, "đồng": 2.5, "kết tủa": 3.0,
        "dung dịch": 2.5, "chất béo": 3.0, "xà phòng hóa": 4.0, "điện phân": 4.0,
        "bảo toàn e": 4.0, "bảo toàn khối lượng": 3.5, "mol": 2.5, "axit": 2.5,
        "bazơ": 2.5, "muối": 2.0, "ancol": 3.5, "anđehit": 4.0, "hiđrocacbon": 4.0,
        "cân bằng hóa học": 3.5, "chuẩn độ": 4.0, "hằng số điện ly": 4.0,
        "hiệu ứng nhiệt": 3.5, "tinh thể": 3.0, "phức chất": 4.5, "đồng phân": 3.5,
    },

    # SINH HỌC (CHUYÊN SINH & THPTQG)
    "BIOLOGY": {
        "adn": 4.0, "arn": 4.0, "phiên mã": 4.5, "dịch mã": 4.5, "tái bản": 4.0,
        "đột biến gen": 4.0, "nhiễm sắc thể": 4.0, "nguyên phân": 4.0, "giảm phân": 4.0,
        "quy luật di truyền": 4.0, "menđen": 4.5, "alen": 4.0, "kiểu gen": 4.0,
        "kiểu hình": 3.5, "phả hệ": 4.5, "di truyền học quần thể": 4.5,
        "hacđi-vanbec": 5.0, "chọn giống": 3.5, "tiến hóa": 3.5, "sinh thái học": 3.5,
        "chuỗi thức ăn": 3.5, "lưới thức ăn": 3.5, "quần xã": 3.5, "hệ sinh thái": 3.5,
        "quang hợp": 3.5, "hô hấp tế bào": 3.5, "enzim": 3.5, "clo-rô-phin": 4.0,
        "hoán vị gen": 4.5, "liên kết gen": 4.0, "đột biến cấu trúc": 4.0,
        "đa bội": 4.0, "tam bội": 4.0, "mã di truyền": 4.5, "ribôxôm": 4.0,
    },

    # NGỮ VĂN (CHUYÊN VĂN & THPTQG)
    "LITERATURE": {
        "đọc hiểu": 3.0, "ngữ liệu": 3.5, "nghị luận xã hội": 4.5, "nghị luận văn học": 5.0,
        "lý luận văn học": 5.0, "tác giả": 3.0, "tác phẩm": 3.0, "nhân vật": 3.0,
        "hình tượng": 3.5, "cảm hứng lãng mạn": 4.0, "hiện thực": 3.0, "biện pháp tu từ": 4.0,
        "nhân hóa": 3.5, "so sánh": 2.5, "ẩn dụ": 4.0, "hoán dụ": 4.0, "điệp từ": 3.5,
        "phong cách nghệ thuật": 4.5, "tư tưởng nhân đạo": 4.0, "thông điệp": 3.0,
        "nhận định": 3.5, "đoạn trích": 3.0, "bài thơ": 3.0, "nhà thơ": 3.0, "nhà văn": 3.0,
        "thi phẩm": 3.5, "tứ thơ": 4.0, "cốt truyện": 3.5, "kịch tính": 3.5,
    },

    # LỊCH SỬ (CHUYÊN SỬ & THPTQG)
    "HISTORY": {
        "cách mạng tháng tám": 4.5, "chiến dịch điện biên phủ": 4.5, "chiến dịch hồ chí minh": 4.5,
        "hiệp định giơ-ne-vơ": 5.0, "hiệp định pari": 5.0, "thực dân pháp": 3.5, "đế quốc mỹ": 3.5,
        "chiến tranh thế giới": 4.0, "liên hợp quốc": 4.0, "chiến tranh lạnh": 4.5, "asean": 3.5,
        "công cuộc đổi mới": 4.0, "đảng cộng sản việt nam": 4.0, "mặt trận việt minh": 4.5,
        "toàn quốc kháng chiến": 4.5, "chiến tranh đặc biệt": 4.5, "chiến tranh cục bộ": 4.5,
        "việt nam hóa chiến tranh": 4.5, "thắng lợi": 3.0, "ý nghĩa lịch sử": 3.5,
        "phong trào cần vương": 4.5, "khởi nghĩa yên thế": 4.5, "đông kinh nghĩa thục": 4.5,
    },

    # ĐỊA LÝ (CHUYÊN ĐỊA & THPTQG)
    "GEOGRAPHY": {
        "atlat địa lí việt nam": 5.0, "nhiệt đới ẩm gió mùa": 4.5, "đồng bằng sông hồng": 4.0,
        "đồng bằng sông cửu long": 4.0, "trung du và miền núi bắc bộ": 4.0, "duyên hải nam trung bộ": 4.0,
        "tây nguyên": 3.5, "đông nam bộ": 4.0, "chuyển dịch cơ cấu kinh tế": 4.5, "đô thị hóa": 3.5,
        "công nghiệp chế biến": 3.5, "vùng kinh tế trọng điểm": 4.0, "biển đông": 3.5,
        "gió mùa tây nam": 4.5, "gió mùa đông bắc": 4.5, "bão": 2.5, "biểu đồ": 3.5,
        "bảng số liệu": 3.5, "xuất nhập khẩu": 3.0, "tổng sản phẩm": 3.0, "mật độ dân số": 3.5,
        "thềm lục địa": 3.5, "tài nguyên khoáng sản": 3.5, "thủy năng": 3.5,
    },

    # GIÁO DỤC CÔNG DÂN / KINH TẾ & PHÁP LUẬN
    "CIVIC_EDUCATION": {
        "quy phạm pháp luật": 5.0, "vi phạm pháp luật": 4.5, "trách nhiệm pháp lý": 4.5,
        "vi phạm hình sự": 4.5, "vi phạm dân sự": 4.5, "vi phạm hành chính": 4.5,
        "vi phạm kỷ luật": 4.5, "quyền bình đẳng": 4.0, "quyền bầu cử": 4.0, "quyền ứng cử": 4.0,
        "quyền khiếu nại": 4.5, "quyền tố cáo": 4.5, "quyền tự do ngôn luận": 4.0,
        "kinh tế thị trường": 4.0, "quy luật giá trị": 4.5, "cung cầu": 4.0, "cạnh tranh": 3.5,
        "lạm phát": 4.0, "thất nghiệp": 3.5, "ngân sách nhà nước": 4.0, "thuế": 3.5,
        "hiến pháp": 4.0, "bộ luật lao động": 4.0, "doanh nghiệp": 3.0,
    },

    # KHOA HỌC TỰ NHIÊN (THCS)
    "NATURAL_SCIENCE": {
        "tế bào": 3.5, "quang hợp": 3.5, "lực ma sát": 3.5, "áp suất": 3.5,
        "khối lượng riêng": 3.5, "chất tinh khiết": 3.5, "hỗn hợp": 3.0,
        "bảng tuần hoàn": 4.0, "nguyên tử": 3.5, "phân tử": 3.5, "đo nhiệt độ": 3.0,
    },

    # TIẾNG NGA (TRKI / TORFL)
    "RUSSIAN": {
        "русский язык": 5.0, "падеж": 4.0, "глагол": 4.0, "существительное": 4.0,
        "прилагательное": 4.0, "упражнение": 4.0, "задание": 4.0, "тест": 3.5,
        "предложение": 3.5, "текст": 3.0, "трки": 5.0, "torfl": 5.0, "trki": 5.0,
        "вариант": 3.5, "словарь": 3.5, "грамматика": 4.0, "ответы": 3.5,
    },

    # TIẾNG NHẬT (JLPT)
    "JAPANESE": {
        "jlpt": 5.0, "nihongo": 4.5, "kanji": 4.5, "hiragana": 4.0, "katakana": 4.0,
        "bunpou": 4.5, "dokkai": 4.5, "choukai": 4.5, "mondai": 4.0, "kotoba": 4.0,
    },

    # TIẾNG TRUNG (HSK)
    "CHINESE": {
        "hsk": 5.0, "hanyu": 4.5, "pinyin": 4.5, "tingli": 4.0, "yuedu": 4.0,
        "shuxie": 4.0, "hanzi": 4.0, "yufa": 4.0, "cihui": 4.0,
    },

    # TIẾNG HÀN (TOPIK)
    "KOREAN": {
        "topik": 5.0, "hangeul": 4.5, "hangul": 4.5, "deudgi": 4.0, "ilggi": 4.0,
        "sseugi": 4.0, "munbeob": 4.0, "eohwi": 4.0,
    },

    # TIẾNG PHÁP
    "FRENCH": {
        "français": 4.5, "grammaire": 4.0, "vocabulaire": 4.0, "delf": 5.0, "dalf": 5.0,
        "compréhension": 4.0, "production": 4.0, "exercice": 3.5,
    },
}

# ============================================================================
# ACADEMIC YEAR & SCHOOL/PROVINCE EXTRACTION
# ============================================================================

# Năm học: 2024-2025, 2025–2026, HK1 2024, Kì 1 năm 2024, Giữa kỳ 1 2025, etc.
RE_ACADEMIC_YEAR: Pattern = re.compile(
    r"(?i)(?:"
    r"(?:năm\s*học|n[aă]m\s*h[oọ]c)\s*[:：]?\s*(20\d{2})\s*[-–—]\s*(20\d{2})"
    r"|(?:hk|học\s*kỳ|kì|kỳ)\s*([12])\s*(?:năm\s*học?)?\s*[:：]?\s*(20\d{2})(?:\s*[-–—]\s*(20\d{2}))?"
    r"|(20\d{2})\s*[-–—]\s*(20\d{2})"
    r")"
)

# Trường / Sở GD&ĐT / Tỉnh ra đề
RE_SCHOOL_PROVINCE: Pattern = re.compile(
    r"(?i)(?:"
    r"(?:trường\s*(?:thpt|thcs|th|tiểu\s*học|đại\s*học|cao\s*đẳng|cđ)?)\s+([^\n,;()]{3,60})"
    r"|(?:sở\s*(?:gd[&]?đt|giáo\s*dục\s*(?:và\s*)?đào\s*tạo))\s+([^\n,;()]{3,40})"
    r"|(?:(?:chuyên|thpt\s*chuyên|trường\s*chuyên))\s+([^\n,;()]{3,50})"
    r"|(?:phòng\s*(?:gd[&]?đt|giáo\s*dục))\s+([^\n,;()]{3,40})"
    r")"
)

# ============================================================================
# DEEP EXAM METADATA & QUESTION DETAIL SIGNATURES (ZERO AI)
# ============================================================================

# 1. Thời gian làm bài: "Thời gian làm bài: 50 phút", "Thời gian: 90 phút", "120 mins"
RE_EXAM_DURATION: Pattern = re.compile(
    r"(?i)(?:thời\s*gian(?:\s*làm\s*bài)?|thoi\s*gian|time(?:\s*allowed)?)\s*[:：]?\s*(\d{2,3})\s*(?:phút|phut|min(?:ute)?s?)",
)

# 2. Kỳ thi cụ thể (Giữa kỳ 1, Cuối kỳ 1, Giữa kỳ 2, Cuối kỳ 2, Thi thử tốt nghiệp, KSCL, HSG, Tuyển sinh 10, ĐGNL)
RE_EXAM_PERIOD: Pattern = re.compile(
    r"(?i)(?:"
    r"(giữa\s*(?:học\s*)?kỳ\s*1|giữa\s*kì\s*1|gk1|hk1|học\s*kỳ\s*1|kỳ\s*1|kì\s*1)"
    r"|(giữa\s*(?:học\s*)?kỳ\s*2|giữa\s*kì\s*2|gk2|hk2|học\s*kỳ\s*2|kỳ\s*2|kì\s*2)"
    r"|(thi\s*thử(?:\s*tốt\s*nghiệp)?(?:\s*thpt)?)"
    r"|(khảo\s*sát\s*chất\s*lượng|kscl)"
    r"|(học\s*sinh\s*giỏi|hsg|olympic)"
    r"|(tuyển\s*sinh(?:\s*vào)?\s*(?:lớp\s*)?10)"
    r"|(đánh\s*giá\s*năng\s*lực|đgnl|đánh\s*giá\s*tư\s*duy|đgtd)"
    r")"
)

# 3. Mã đề thi: "Mã đề: 101", "Mã đề thi 204", "MÃ ĐỀ: A", "Mã đề 001"
RE_EXAM_CODE: Pattern = re.compile(
    r"(?i)\b(?:mã\s*đề(?:\s*thi)?|ma\s*de|code|test\s*code)\s*[:：]?\s*([a-zA-Z0-9_-]{1,8})\b"
)

# 4. Thang điểm tổng bài thi: "Thang điểm 10", "Điểm toàn bài: 10,0", "Tổng: 100 điểm"
RE_TOTAL_POINTS: Pattern = re.compile(
    r"(?i)(?:thang\s*điểm|tổng\s*(?:số\s*)?điểm|điểm\s*toàn\s*bài)\s*[:：]?\s*(\d{1,3}(?:[.,]\d+)?)\s*(?:điểm|đ)?"
)

# 5. Thang điểm câu hỏi: "(1,0 điểm)", "(0.5 điểm)", "(2,0đ)", "[1 điểm]", "(0,25 điểm)"
RE_QUESTION_POINTS: Pattern = re.compile(
    r"(?i)(?:[\(\[]\s*(\d+(?:[.,]\d+)?)\s*(?:điểm|đ|pts?|points?)[\)\]])"
)

# 6. Tách Lời giải / Hướng dẫn giải trong từng câu hỏi
RE_QUESTION_SOLUTION_SPLIT: Pattern = re.compile(
    r"(?i)(?:\n|\r|\A)\s*(?:▶\s*|\*+\s*)?(?:lời\s*giải(?:\s*chi\s*tiết)?|hướng\s*dẫn\s*giải|giải\s*chi\s*tiết|hdg|hướng\s*dẫn)\s*[:：]\s*",
)

# 7. Phát hiện Hình vẽ, Đồ thị, Bảng biến thiên, Mạch điện trong câu hỏi
RE_FIGURE_GRAPH_CUE: Pattern = re.compile(
    r"(?i)\b(?:hình\s*(?:vẽ\s*)?(?:bên|dưới|sau|trên|\d+)|đồ\s*thị(?:\s*hàm\s*số)?(?:\s*(?:như|bên|sau|dưới))?|bảng\s*biến\s*thiên|mạch\s*điện|sơ\s*đồ\s*(?:như\s*)?(?:bên|sau)|xem\s*hình)\b"
)

# 8. Phát hiện Bảng số liệu, Bảng dữ liệu trong câu hỏi
RE_TABLE_CUE: Pattern = re.compile(
    r"(?i)\b(?:bảng\s*số\s*liệu|bảng\s*dữ\s*liệu|bảng\s*thống\s*kê|cho\s*bảng|bảng\s*xét\s*dấu)\b"
)

# 9. Phát hiện Đoạn văn đọc hiểu / Reading Comprehension passage
RE_READING_PASSAGE_CUE: Pattern = re.compile(
    r"(?i)\b(?:đọc\s*đoạn\s*(?:trích|văn)\s*sau|read\s*the\s*following\s*passage|dựa\s*vào\s*thông\s*tin\s*dưới\s*đây)\b"
)

# 10. Danh sách tỉnh thành phố ra đề phổ biến tại Việt Nam
VIETNAM_PROVINCES = [
    "Hà Nội", "Hồ Chí Minh", "TP.HCM", "Nam Định", "Nghệ An", "Hải Phòng",
    "Bắc Ninh", "Thanh Hóa", "Đà Nẵng", "Thừa Thiên Huế", "Huế", "Thái Bình",
    "Vĩnh Phúc", "Phú Thọ", "Hải Dương", "Quảng Ninh", "Hưng Yên", "Hà Nam",
    "Ninh Bình", "Bắc Giang", "Thái Nguyên", "Lạng Sơn", "Tuyên Quang",
    "Yên Bái", "Lào Cai", "Sơn La", "Điện Biên", "Lai Châu", "Hòa Bình",
    "Hà Tĩnh", "Quảng Bình", "Quảng Trị", "Quảng Nam", "Quảng Ngãi",
    "Bình Định", "Phú Yên", "Khánh Hòa", "Ninh Thuận", "Bình Thuận",
    "Kon Tum", "Gia Lai", "Đắk Lắk", "Đắk Nông", "Lâm Đồng", "Bình Phước",
    "Tây Ninh", "Bình Dương", "Đồng Nai", "Bà Rịa - Vũng Tàu", "Long An",
    "Tiền Giang", "Bến Tre", "Trà Vinh", "Vĩnh Long", "Đồng Tháp", "An Giang",
    "Kiên Giang", "Cần Thơ", "Hậu Giang", "Sóc Trăng", "Bạc Liêu", "Cà Mau",
    "Cao Bằng", "Bắc Kạn", "Hà Giang"
]

# 11. Từ điển nhận diện chuyên đề môn học (Zero-AI, <0.1ms, cực kỳ chính xác)
TOPIC_SIGNATURES: Dict[str, List[Tuple[str, Pattern]]] = {
    "MATHEMATICS": [
        ("Hàm số & Đồ thị", re.compile(r"(?i)\b(?:hàm\s*số|đồng\s*biến|nghịch\s*biến|cực\s*trị|cực\s*đại|cực\s*tiểu|tiệm\s*cận|bảng\s*biến\s*thiên|đồ\s*thị|tương\s*giao)\b")),
        ("Mũ & Logarit", re.compile(r"(?i)\b(?:logarit|logarithm|phương\s*trình\s*mũ|bất\s*phương\s*trình\s*mũ|tập\s*nghiệm\s*của\s*bất\s*phương\s*trình|ln|log)\b")),
        ("Nguyên hàm & Tích phân", re.compile(r"(?i)\b(?:nguyên\s*hàm|tích\s*phân|diện\s*tích\s*hình\s*phẳng|thể\s*tích\s*khối\s*tròn\s*xoay)\b")),
        ("Hình không gian & Khối đa diện", re.compile(r"(?i)\b(?:hình\s*chóp|lăng\s*trụ|mặt\s*cầu|hình\s*nón|hình\s*trụ|thể\s*tích\s*khối|khoảng\s*cách\s*từ|góc\s*giữa)\b")),
        ("Phương pháp tọa độ Oxyz", re.compile(r"(?i)\b(?:ox\s*y\s*z|hệ\s*tọa\s*độ|mặt\s*phẳng\s*\([a-z]\)|đường\s*thẳng|vectơ\s*pháp\s*tuyến|tâm\s*mặt\s*cầu|bán\s*kính)\b")),
        ("Số phức", re.compile(r"(?i)\b(?:số\s*phức|phần\s*thực|phần\s*ảo|môđun|mô-đun|số\s*phức\s*liên\s*hợp)\b")),
        ("Xác suất & Thống kê", re.compile(r"(?i)\b(?:xác\s*suất|không\s*gian\s*mẫu|biến\s*cố|chỉnh\s*hợp|tổ\s*hợp|hoán\s*vị|phương\s*sai|độ\s*lệch\s*chuẩn)\b")),
        ("Dãy số & Cấp số", re.compile(r"(?i)\b(?:cấp\s*số\s*cộng|cấp\s*số\s*nhân|công\s*sai|công\s*bội|dãy\s*số)\b")),
    ],
    "PHYSICS": [
        ("Dao động cơ", re.compile(r"(?i)\b(?:dao\s*động\s*điều\s*hòa|con\s*lắc\s*lò\s*xo|con\s*lắc\s*đơn|biên\s*độ|chu\s*kì|tần\s*số\s*góc|cơ\s*năng|thế\s*năng)\b")),
        ("Sóng cơ & Sóng âm", re.compile(r"(?i)\b(?:sóng\s*cơ|giao\s*thoa\s*sóng|bước\s*sóng|sóng\s*dừng|sóng\s*âm|mức\s*cường\s*độ\s*âm)\b")),
        ("Dòng điện xoay chiều", re.compile(r"(?i)\b(?:dòng\s*điện\s*xoay\s*chiều|cảm\s*kháng|dung\s*kháng|trở\s*kháng|hệ\s*số\s*công\s*suất|máy\s*biến\s*áp|mạch\s*rlc)\b")),
        ("Dao động & Sóng điện từ", re.compile(r"(?i)\b(?:mạch\s*dao\s*động|sóng\s*điện\s*từ|điện\s*từ\s*trường|sóng\s*vô\s*tuyến)\b")),
        ("Sóng ánh sáng", re.compile(r"(?i)\b(?:tán\s*sắc\s*ánh\s*sáng|giao\s*thoa\s*ánh\s*sáng|khoảng\s*vân|quang\s*phổ|tia\s*hồng\s*ngoại|tia\s*tử\s*ngoại|tia\s*x)\b")),
        ("Lượng tử ánh sáng", re.compile(r"(?i)\b(?:quang\s*điện|lượng\s*tử|photon|công\s*thoát|giới\s*hạn\s*quang\s*điện|quang\s*phổ\s*vạch)\b")),
        ("Hạt nhân nguyên tử", re.compile(r"(?i)\b(?:hạt\s*nhân|phóng\s*xạ|độ\s*hụt\s*khối|năng\s*lượng\s*liên\s*kết|đồng\s*vị|phân\s*hạch|nhiệt\s*hạch)\b")),
    ],
    "CHEMISTRY": [
        ("Este - Lipit - Xà phòng", re.compile(r"(?i)\b(?:este|lipit|chất\s*béo|xà\s*phòng|thủy\s*phân|triglixerit|axit\s*béo)\b")),
        ("Cacbohiđrat", re.compile(r"(?i)\b(?:cacbohiđrat|glucozơ|fructozơ|saccarozơ|tinh\s*bột|xenlulozơ)\b")),
        ("Amin - Amino axit - Peptit - Protein", re.compile(r"(?i)\b(?:amin|amino\s*axit|peptit|protein|liên\s*kết\s*peptit|anilin)\b")),
        ("Polime & Vật liệu polime", re.compile(r"(?i)\b(?:polime|trùng\s*hợp|trùng\s*ngưng|cao\s*su|tơ|nilon|chất\s*dẻo)\b")),
        ("Đại cương kim loại & Dãy điện hóa", re.compile(r"(?i)\b(?:kim\s*loại|dãy\s*điện\s*hóa|ăn\s*mòn|điện\s*phân|tính\s*khử)\b")),
        ("Kim loại kiềm, kiềm thổ & Nhôm", re.compile(r"(?i)\b(?:kiềm|kiềm\s*thổ|nhôm|alumin|nước\s*cứng|hiđroxit)\b")),
        ("Sắt & Hợp chất của Sắt", re.compile(r"(?i)\b(?:sắt|fe2\+|fe3\+|gang|thép|oxit\s*sắt)\b")),
    ],
    "BIOLOGY": [
        ("Cơ chế di truyền & Biến dị", re.compile(r"(?i)\b(?:adn|arn|marn|tarn|nhân\s*đôi|phiên\s*mã|dịch\s*mã|đột\s*biến|nhiễm\s*sắc\s*thể|gen)\b")),
        ("Quy luật di truyền", re.compile(r"(?i)\b(?:menđen|phân\s*li|trội|lặn|hoán\s*vị\s*gen|liên\s*kết\s*gen|tương\s*tác\s*gen|phả\s*hệ)\b")),
        ("Di truyền quần thể", re.compile(r"(?i)\b(?:quần\s*thể|hacđi-vanbec|cân\s*bằng\s*di\s*truyền|tần\s*số\s*alen)\b")),
        ("Tiến hóa", re.compile(r"(?i)\b(?:tiến\s*hóa|chọn\s*lọc\s*tự\s*nhiên|đác-uyn|bằng\s*chứng\s*tiến\s*hóa|loài\s*mới)\b")),
        ("Sinh thái học", re.compile(r"(?i)\b(?:sinh\s*thái|chuỗi\s*thức\s*ăn|lưới\s*thức\s*ăn|quần\s*xã|hệ\s*sinh\s*thái|bậc\s*dinh\s*dưỡng)\b")),
    ],
    "ENGLISH": [
        ("Phonetics & Stress", re.compile(r"(?i)\b(?:pronunciation|stressed|differs?\s*from|primary\s*stress|pronounced)\b")),
        ("Grammar & Vocabulary", re.compile(r"(?i)\b(?:best\s*completes?|closest\s*in\s*meaning|opposite\s*in\s*meaning|correct\s*form)\b")),
        ("Error Identification", re.compile(r"(?i)\b(?:underlined\s*part|needs?\s*correction|find\s*the\s*mistake)\b")),
        ("Reading Comprehension", re.compile(r"(?i)\b(?:passage|according\s*to\s*the\s*passage|stated\s*in\s*the\s*passage|inferred)\b")),
        ("Sentence Transformation", re.compile(r"(?i)\b(?:closest\s*in\s*meaning\s*to\s*each|combine\s*each\s*pair|meaningful\s*sentence)\b")),
    ],
}


