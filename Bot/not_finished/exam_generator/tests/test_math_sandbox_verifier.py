"""tests/test_math_sandbox_verifier.py
Kiểm thử toàn diện động cơ Thẩm Định Toán Học Tuyệt Đối SymPy Sandbox (Zero Math Hallucination).
"""

import unittest

from not_finished.exam_generator.services.math_sandbox_verifier import (
    HAS_SYMPY,
    MathSandboxVerifier,
    math_sandbox_verifier,
)


class TestMathSandboxVerifier(unittest.TestCase):
    def setUp(self):
        self.verifier = math_sandbox_verifier

    def test_has_sympy(self):
        """Đảm bảo thư viện SymPy đã được cài đặt và tích hợp thành công."""
        self.assertTrue(HAS_SYMPY, "SymPy phải được cài đặt trong môi trường!")

    def test_latex_to_sympy_str(self):
        """Kiểm tra việc chuyển đổi ký hiệu LaTeX sang chuỗi biểu thức SymPy."""
        # Phân số
        self.assertEqual(self.verifier.latex_to_sympy_str(r"\frac{1}{2}"), "(1)/(2)")
        # Số mũ
        self.assertEqual(self.verifier.latex_to_sympy_str(r"x^{2} + 2x + 1"), "x**(2) + 2*x + 1")
        # Căn bậc 2
        self.assertEqual(self.verifier.latex_to_sympy_str(r"\sqrt{x}"), "sqrt(x)")
        # Lượng giác & số pi
        self.assertIn("sin", self.verifier.latex_to_sympy_str(r"\sin(x)"))
        self.assertIn("pi", self.verifier.latex_to_sympy_str(r"\pi"))

    def test_evaluate_expression(self):
        """Kiểm tra tính giá trị biểu thức số học và rút gọn đại số."""
        val1 = self.verifier.evaluate_expression(r"\frac{10}{2} + 3")
        self.assertIsNotNone(val1)
        self.assertEqual(int(val1), 8)

        val2 = self.verifier.evaluate_expression(r"2^{3} - 1")
        self.assertIsNotNone(val2)
        self.assertEqual(int(val2), 7)

    def test_verify_derivative(self):
        """Kiểm tra đạo hàm hàm số: f(x) = x^3 - 3x^2 + 2x, f'(1) = 3(1)^2 - 6(1) + 2 = -1."""
        res = self.verifier.verify_derivative("x^3 - 3*x^2 + 2*x", at_point=1.0)
        self.assertIsNotNone(res)
        self.assertAlmostEqual(res, -1.0)

    def test_verify_definite_integral(self):
        """Kiểm tra tích phân xác định: int_0^1 (2x + 3) dx = [x^2 + 3x]_0^1 = 1 + 3 = 4."""
        res = self.verifier.verify_definite_integral("2*x + 3", 0.0, 1.0)
        self.assertIsNotNone(res)
        self.assertAlmostEqual(res, 4.0)

    def test_solve_algebraic_equation(self):
        """Kiểm tra giải phương trình bậc 2: x^2 - 5x + 6 = 0 -> nghiệm là {2, 3}."""
        sols = self.verifier.solve_algebraic_equation("x^2 - 5*x + 6 = 0")
        self.assertEqual(len(sols), 2)
        str_sols = [str(s) for s in sols]
        self.assertIn("2", str_sols)
        self.assertIn("3", str_sols)

    def test_audit_exam_math_auto_correction(self):
        """Kiểm chứng tính năng sửa ảo giác đáp án của AI (AI chọn sai B, SymPy tự động sửa về A)."""
        mock_exam = {
            "questions": [
                {
                    "number": "1",
                    "type": "question",
                    "text": r"Cho hàm số $f(x) = x^2 - 4x + 3$. Tính đạo hàm $f'(3)$.",
                    "options": [
                        r"A. $2$",
                        r"B. $4$",
                        r"C. $-1$",
                        r"D. $0$",
                    ],
                }
            ],
            "solutions": [
                {
                    "number": "1",
                    "is_multiple_choice": True,
                    "correct_key": "B",  # AI chọn nhầm B ($4$) trong khi f'(3) = 2*3 - 4 = 2 (Option A)
                    "explanation": "Đạo hàm f'(x) = 2x - 4. Tại x=3 ta có kết quả là 4.",
                }
            ],
        }

        audited_exam, results = self.verifier.audit_exam_math(mock_exam)
        self.assertEqual(len(results), 1)
        r = results[0]

        # Đã phát hiện và tự động sửa key
        self.assertTrue(r.was_corrected)
        self.assertEqual(r.original_key, "B")
        self.assertEqual(r.verified_key, "A")
        # Kiểm tra dữ liệu trong exam đã được cập nhật
        self.assertEqual(audited_exam["solutions"][0]["correct_key"], "A")
        self.assertIn("Chứng minh toán học SymPy", audited_exam["solutions"][0]["explanation"])


if __name__ == "__main__":
    unittest.main()
