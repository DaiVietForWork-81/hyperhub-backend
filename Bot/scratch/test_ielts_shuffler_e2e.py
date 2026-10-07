"""Kiểm tra quy trình xáo trộn mã đề tự nhiên (Natural Shuffler) và xuất bản file hoàn chỉnh."""

import copy
import json
import os
import sys
from pathlib import Path

# Đảm bảo UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.exam_shuffler import exam_shuffler
from services.document_exporter import document_exporter

# Cấu trúc đề thi IELTS 8.0 mẫu
SAMPLE_IELTS_DATA = {
    "metadata": {
        "exam_title": "KỲ THI ĐÁNH GIÁ NĂNG LỰC HYPERHUB",
        "subject": "IELTS Academic Band 8.0 Reading & Writing",
        "exam_code": "HH-101",
        "duration": "60 phút",
        "length_tier": "Ngắn",
        "job_id": "IELTS80"
    },
    "questions": [
        {
            "type": "section_header",
            "title": "SECTION 1: READING PASSAGE & COMPREHENSION"
        },
        {
            "type": "question",
            "number": "1",
            "points": "1.0",
            "text": "What is the primary factor contributing to urban heat islands according to the text?",
            "options": [
                "A. High concentration of asphalt and concrete structures",
                "B. Excessive agricultural runoff",
                "C. Natural volcanic activity in suburban perimeters",
                "D. Reduced solar radiation in dense settlements"
            ],
            "has_diagram": False
        },
        {
            "type": "question",
            "number": "2",
            "points": "1.0",
            "text": "The author implies that mitigation strategies are predominantly:",
            "options": [
                "A. Completely ineffective in subtropical zones",
                "B. Cost-prohibitive without state subsidies",
                "C. Viable only through retrofitting urban green corridors",
                "D. Universally adopted across developing nations"
            ],
            "has_diagram": False
        },
        {
            "type": "question",
            "number": "3",
            "points": "1.0",
            "text": "Which statement aligns with the empirical evidence presented in paragraph 3?",
            "options": [
                "A. Vegetative canopies reduce surface temperatures significantly",
                "B. Concrete pavements reflect 95% of infrared energy",
                "C. Microclimates remain unaffected by architectural density",
                "D. Cool roofs are detrimental to winter thermal retention"
            ],
            "has_diagram": False
        },
        {
            "type": "section_header",
            "title": "SECTION 2: ACADEMIC WRITING TASK 2"
        },
        {
            "type": "question",
            "number": "4",
            "points": "7.0",
            "text": "Some educational experts argue that artificial intelligence in pedagogical frameworks will render conventional classroom environments obsolete. To what extent do you agree or disagree? Write at least 250 words.",
            "sub_items": [],
            "has_diagram": False
        }
    ],
    "solutions": [
        {
            "number": "1",
            "is_multiple_choice": True,
            "correct_key": "A",
            "explanation": "Paragraph 1 explicitly identifies dense asphalt and concrete as primary thermal absorbents.",
            "common_mistakes": "Conflating solar radiation with surface heat absorption.",
            "rubric": [["Correctly identifies option A", 1.0]]
        },
        {
            "number": "2",
            "is_multiple_choice": True,
            "correct_key": "C",
            "explanation": "Paragraph 2 emphasizes that only systematic urban green corridors provide measurable cooling.",
            "common_mistakes": "Overgeneralizing economic cost factors.",
            "rubric": [["Correctly identifies option C", 1.0]]
        },
        {
            "number": "3",
            "is_multiple_choice": True,
            "correct_key": "A",
            "explanation": "Empirical datasets demonstrate a 4-8°C reduction under vegetative canopies.",
            "common_mistakes": "Misinterpreting cool roof data.",
            "rubric": [["Correctly identifies option A", 1.0]]
        },
        {
            "number": "4",
            "is_multiple_choice": False,
            "explanation": "Model Band 8.5 essay demonstrating cohesive structure, advanced lexical resource, and rigorous argument development.",
            "rubric": [
                ["Task Achievement & Argumentation", 2.0],
                ["Coherence & Cohesion", 2.0],
                ["Lexical Resource (C1/C2)", 1.5],
                ["Grammatical Range & Accuracy", 1.5]
            ]
        }
    ]
}

def main():
    print("=" * 60)
    print("🧪 KIỂM TRA QUY TRÌNH XÁO TRỘN ĐỀ THI & XUẤT BẢN FILE")
    print("=" * 60)

    # 1. Thực hiện trộn đề
    shuffled_data = exam_shuffler.shuffle_exam(SAMPLE_IELTS_DATA, new_exam_code="HH-102")
    new_meta = shuffled_data["metadata"]
    print(f"✅ Đã trộn sang mã đề: {new_meta['exam_code']} (Gốc: {new_meta.get('original_exam_code')})")

    # Kiểm tra tính toàn vẹn
    assert len(shuffled_data["questions"]) == len(SAMPLE_IELTS_DATA["questions"])
    assert len(shuffled_data["solutions"]) == len(SAMPLE_IELTS_DATA["solutions"])

    # In đối chiếu đáp án trắc nghiệm
    print("\n📊 ĐỐI CHIẾU ĐÁP ÁN TRƯỚC VÀ SAU KHI TRỘN:")
    for sol in shuffled_data["solutions"]:
        if sol.get("is_multiple_choice"):
            print(f"  • Câu {sol['number']}: Đáp án mới: [{sol['correct_key']}] - {sol['explanation'][:45]}...")

    # 2. Xuất file
    out_dir = os.path.join("scratch", "exports", "ielts_80_shuffled")
    os.makedirs(out_dir, exist_ok=True)

    res = document_exporter.export_all(
        metadata=new_meta,
        exam_data=shuffled_data,
        output_format="Both",
        output_dir=out_dir,
    )

    print("\n📁 DANH SÁCH FILE ĐÃ TẠO:")
    for f in res["exam_files"] + res["solution_files"]:
        size_kb = os.path.getsize(f) / 1024
        print(f"  • {os.path.basename(f)} ({size_kb:.1f} KB)")
        assert size_kb < 5120, "File vượt quá 5MB!"

    print("\n🎉 KIỂM TRA THÀNH CÔNG 100%!")

if __name__ == "__main__":
    main()
