"""Regression tests for AI fairness policy.

Detector heuristic ch? mang tinh xac suat (de false positive, thien vi phong
cach viet) nen KHONG BAO GIO duoc dung de tu dong huy bai, tru diem hay cam
thi dau. File nay khoa chinh sach do: neu ai muon bat lai auto-phat thi test
se do va buoc phai chu y review bang tay.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services import judge as judge_module
from services.ai_detector import AIDetector


class TestAIFairnessPolicy(unittest.TestCase):
    def test_auto_punish_disabled(self):
        """Cong tac auto-phat phai LUON tat."""
        self.assertFalse(judge_module.AI_AUTO_PUNISH_ENABLED)

    def test_no_auto_punish_code_path(self):
        """Khong con duong goi apply_ai_violation tu dong trong judge."""
        import inspect

        source = inspect.getsource(judge_module)
        self.assertNotIn("apply_ai_violation(", source)

    def test_detector_is_advisory_only(self):
        """Detector tra ve diem/trang thai/tin hieu (khong co verdict phat)."""
        code = (
            "```python\n"
            "def solve():\n"
            "    # Time Complexity: O(n log n)\n"
            "    # Here is the complete solution with step 1: read input values\n"
            "    pass\n"
            "```\n"
        )
        res = AIDetector.analyze(code, "python")
        self.assertIn("score", res)
        self.assertIn("status", res)
        self.assertIn("signals", res)
        self.assertGreaterEqual(res["score"], 0)
        # Khong co truong nao quyet dinh hinh phat
        self.assertNotIn("ban", res)
        self.assertNotIn("punish", res)
        self.assertNotIn("reject", res)

    def test_clean_code_scores_low(self):
        """Code CP nguoi that viet sach khong bi danh diem cao."""
        code = (
            "#include <bits/stdc++.h>\n"
            "using namespace std;\n"
            "#define ll long long\n"
            "int main() {\n"
            "    ios_base::sync_with_stdio(false);\n"
            "    cin.tie(nullptr);\n"
            "    int n; if (!(cin >> n)) return 0;\n"
            "    ll s = 0;\n"
            "    for (int i = 0; i < n; ++i) { int x; cin >> x; s += x; }\n"
            "    cout << s;\n"
            "    return 0;\n"
            "}\n"
        )
        res = AIDetector.analyze(code, "cpp")
        self.assertLess(res["score"], 70)


if __name__ == "__main__":
    unittest.main()
