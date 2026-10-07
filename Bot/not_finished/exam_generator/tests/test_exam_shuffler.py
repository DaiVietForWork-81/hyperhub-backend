"""Kiểm thử tự động cho ExamShuffler (Xáo trộn câu hỏi và phương án A, B, C, D)."""

try:
    from not_finished.exam_generator.services.exam_shuffler import exam_shuffler
except ImportError:
    from services.exam_shuffler import exam_shuffler


def test_exam_shuffler_syncs_correct_keys():
    """Kiểm tra xáo trộn đề thi bảo toàn tính đúng đắn của đáp án khi đảo A, B, C, D."""
    original_exam = {
        "metadata": {
            "subject": "Tiếng Anh",
            "exam_code": "HH-101",
        },
        "questions": [
            {
                "type": "section_header",
                "title": "PHẦN I: TRẮC NGHIỆM",
            },
            {
                "type": "question",
                "number": "1",
                "text": "What is the capital of France?",
                "options": ["A. Berlin", "B. Paris", "C. London", "D. Rome"],
            },
            {
                "type": "question",
                "number": "2",
                "text": "Which planet is known as the Red Planet?",
                "options": ["A. Earth", "B. Jupiter", "C. Mars", "D. Venus"],
            },
        ],
        "solutions": [
            {
                "number": "1",
                "correct_key": "B",  # Paris
                "explanation": "Paris is the capital of France.",
            },
            {
                "number": "2",
                "correct_key": "C",  # Mars
                "explanation": "Mars is known as the Red Planet.",
            },
        ],
    }

    shuffled = exam_shuffler.shuffle_exam(original_exam, new_exam_code="HH-102", seed=42)

    # 1. Mã đề được cập nhật
    assert shuffled["metadata"]["exam_code"] == "HH-102"
    assert shuffled["metadata"]["is_shuffled"] is True

    # 2. Số lượng câu hỏi và lời giải không đổi
    assert len(shuffled["questions"]) == 3  # 1 header + 2 questions
    assert len(shuffled["solutions"]) == 2

    # 3. Kiểm tra tính đồng bộ của đáp án đúng mới
    for sol in shuffled["solutions"]:
        q_num = sol["number"]
        new_key = sol["correct_key"]
        # Tìm câu hỏi tương ứng
        matching_q = next(q for q in shuffled["questions"] if q.get("number") == q_num)
        matching_opt = next(opt for opt in matching_q["options"] if opt.startswith(f"{new_key}."))

        if "France" in matching_q["text"]:
            assert "Paris" in matching_opt
        elif "Red Planet" in matching_q["text"]:
            assert "Mars" in matching_opt
