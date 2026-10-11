"""
Granular Sub-Topic & Chapter Detector for DocInspector.
Deconstructs subject matter into specific curriculum chapters and sub-domains.
100% Deterministic, Zero AI.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

from .models import SubTopicMatch, Subject

SUB_TOPIC_TAXONOMY: Dict[str, Dict[str, Tuple[str, List[str]]]] = {
    "MATHEMATICS": {
        "MATH_CALCULUS_DERIVATIVES": (
            "Ứng dụng đạo hàm & Khảo sát hàm số",
            ["đạo hàm", "cực trị", "đồng biến", "nghịch biến", "tiệm cận", "bảng biến thiên", "giá trị lớn nhất", "giá trị nhỏ nhất", "tiếp tuyến", "hàm số"],
        ),
        "MATH_INTEGRAL": (
            "Nguyên hàm, Tích phân & Ứng dụng",
            ["nguyên hàm", "tích phân", "diện tích hình phẳng", "thể tích tròn xoay", "đổi biến", "từng phần"],
        ),
        "MATH_COMPLEX_NUMBERS": (
            "Số phức & Biểu diễn hình học",
            ["số phức", "phần thực", "phần ảo", "môđun", "liên hợp", "mặt phẳng phức", "tập hợp điểm"],
        ),
        "MATH_SOLID_GEOMETRY": (
            "Hình học không gian & Khối đa diện",
            ["hình chóp", "lăng trụ", "thể tích khối chóp", "mặt cầu", "hình nón", "hình trụ", "khoảng cách", "góc giữa hai mặt"],
        ),
        "MATH_OXYZ": (
            "Hình học giải tích không gian Oxyz",
            ["oxyz", "oxz", "vectơ pháp tuyến", "vectơ chỉ phương", "mặt phẳng", "phương trình đường thẳng", "tọa độ"],
        ),
        "MATH_PROBABILITY": (
            "Xác suất, Tổ hợp & Nhị thức Newton",
            ["xác suất", "tổ hợp", "chỉnh hợp", "hoán vị", "biến cố", "nhị thức newton"],
        ),
        "MATH_OLYMPIAD_ADVANCED": (
            "Số học, Phương trình hàm & BĐT Olympic",
            ["bất đẳng thức", "cauchy", "schwarz", "đồng dư", "phương trình hàm", "diophantine", "dirichlet", "nguyên lý bù trừ"],
        ),
    },

    "INFORMATICS": {
        "INFO_DYNAMIC_PROGRAMMING": (
            "Quy hoạch động & Tối ưu hóa",
            ["quy hoạch động", "knapsack", "kadane", "lis", "lcs", "bitmask", "chia để trị"],
        ),
        "INFO_DATA_STRUCTURES": (
            "Cấu trúc dữ liệu nâng cao",
            ["segment tree", "fenwick tree", "trie", "dsu", "disjoint set", "hàng đợi ưu tiên", "ngăn xếp"],
        ),
        "INFO_GRAPH_THEORY": (
            "Lý thuyết đồ thị & Đường đi ngắn nhất",
            ["đồ thị", "dijkstra", "floyd", "bfs", "dfs", "cây khung", "kruskal", "tarjan", "lca", "binary lifting"],
        ),
        "INFO_SEARCH_GREEDY": (
            "Tìm kiếm nhị phân & Kỹ thuật tham lam",
            ["chặt nhị phân", "tham lam", "hai con trỏ", "quay lui", "nhánh cận", "thuật toán"],
        ),
        "INFO_COMPUTATIONAL_MATH": (
            "Số học thuật toán & Hình học tính toán",
            ["sàng eratosthenes", "bignum", "modulo", "bao lồi", "convex hull", "ước số"],
        ),
    },

    "PHYSICS": {
        "PHYS_OSCILLATIONS": (
            "Dao động cơ học (Con lắc lò xo & Con lắc đơn)",
            ["dao động điều hòa", "con lắc lò xo", "con lắc đơn", "tần số góc", "biên độ dao động", "chu kỳ"],
        ),
        "PHYS_WAVES": (
            "Sóng cơ & Sóng âm",
            ["sóng cơ", "giao thoa sóng", "sóng dừng", "bước sóng", "mức cường độ âm"],
        ),
        "PHYS_AC_CIRCUITS": (
            "Dòng điện xoay chiều & Máy biến áp",
            ["dòng điện xoay chiều", "cuộn cảm", "tụ điện", "hệ số công suất", "máy biến áp", "công suất"],
        ),
        "PHYS_OPTICS_QUANTUM": (
            "Sóng ánh sáng & Lượng tử ánh sáng",
            ["giao thoa ánh sáng", "quang phổ", "quang điện", "photon", "lượng tử ánh sáng", "bước sóng ánh sáng"],
        ),
        "PHYS_NUCLEAR": (
            "Vật lý hạt nhân & Phóng xạ",
            ["hạt nhân", "năng lượng liên kết", "phóng xạ", "bán rã", "phản ứng hạt nhân", "khối lượng nghỉ"],
        ),
    },

    "CHEMISTRY": {
        "CHEM_ORGANIC_ESTERS_LIPIDS": (
            "Este, Lipit & Hóa học hữu cơ",
            ["este", "lipit", "chất béo", "xà phòng hóa", "ancol", "anđehit", "hiđrocacbon"],
        ),
        "CHEM_CARBOHYDRATES": (
            "Cacbohiđrat (Glucozơ, Saccarozơ, Tinh bột)",
            ["glucozơ", "saccarozơ", "tinh bột", "xenlulozơ", "gluxit", "cacbohiđrat"],
        ),
        "CHEM_AMINES_PROTEINS": (
            "Amin, Amino Axit, Peptit & Protein",
            ["amin", "amino axit", "peptit", "protein", "polime"],
        ),
        "CHEM_METALS_INORGANIC": (
            "Kim loại kiềm, Nhôm, Sắt & Điện phân",
            ["kim loại kiềm", "nhôm", "nhiệt nhôm", "sắt", "crôm", "điện phân", "bảo toàn e", "kết tủa"],
        ),
    },

    "BIOLOGY": {
        "BIO_MOLECULAR_GENETICS": (
            "Cơ chế di truyền & Biến dị phân tử",
            ["adn", "arn", "phiên mã", "dịch mã", "tái bản", "đột biến gen", "nhiễm sắc thể", "mã di truyền"],
        ),
        "BIO_MENDELIAN_GENETICS": (
            "Quy luật di truyền Menđen & Hoán vị gen",
            ["menđen", "alen", "kiểu gen", "kiểu hình", "liên kết gen", "hoán vị gen"],
        ),
        "BIO_POPULATION_GENETICS": (
            "Di truyền học quần thể & Phả hệ",
            ["di truyền học quần thể", "hacđi-vanbec", "phả hệ", "chọn giống"],
        ),
        "BIO_ECOLOGY": (
            "Tiến hóa & Sinh thái học",
            ["sinh thái học", "chuỗi thức ăn", "lưới thức ăn", "quần xã", "hệ sinh thái", "quang hợp"],
        ),
    },

    "ENGLISH": {
        "ENG_IELTS_READING": (
            "IELTS Reading & Task Comprehension",
            ["reading passage", "true/false/not given", "matching information", "headings", "writing task"],
        ),
        "ENG_LEXICO_GRAMMAR": (
            "Chuyên Anh: Word Formation, Cloze & Transformation",
            ["word formation", "sentence transformation", "cloze test", "primary stress", "pronunciation", "phrasal verb"],
        ),
        "ENG_TOEIC_SECTIONS": (
            "Chuẩn TOEIC Listening & Reading",
            ["part 1", "part 2", "part 3", "part 4", "part 5", "part 6", "part 7", "incomplete sentences"],
        ),
    },
}


class SubTopicDetector:
    """Detects curriculum chapters and sub-topics from text."""

    @classmethod
    def detect_sub_topics(cls, text_lower: str, subject: Subject) -> List[SubTopicMatch]:
        """
        Scans document text for specific chapter signatures matching the detected subject.
        Returns a sorted list of SubTopicMatch objects with coverage percentage.
        """
        subj_key = subject.value
        taxonomy = SUB_TOPIC_TAXONOMY.get(subj_key)
        if not taxonomy:
            return []

        raw_scores: Dict[str, Tuple[str, float, List[str]]] = {}
        total_score = 0.0

        for code, (name_vi, keywords) in taxonomy.items():
            topic_score = 0.0
            found_kw: List[str] = []

            for kw in keywords:
                if len(kw) <= 4:
                    cnt = len(re.findall(r"\b" + re.escape(kw) + r"\b", text_lower))
                else:
                    cnt = text_lower.count(kw)

                if cnt > 0:
                    topic_score += cnt * 2.0
                    found_kw.append(f"{kw} (x{cnt})")

            if topic_score > 0.0:
                raw_scores[code] = (name_vi, topic_score, found_kw)
                total_score += topic_score

        if not raw_scores or total_score == 0.0:
            return []

        results: List[SubTopicMatch] = []
        for code, (name_vi, sc, kws) in raw_scores.items():
            pct = (sc / total_score) * 100.0
            results.append(SubTopicMatch(
                topic_code=code,
                topic_name_vi=name_vi,
                weight_score=sc,
                percentage=pct,
                detected_keywords=kws,
            ))

        # Sort descending by score
        results.sort(key=lambda x: x.weight_score, reverse=True)
        return results
