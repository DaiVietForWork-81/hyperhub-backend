"""Unit tests verifying AI-generated code detection heuristics and scoring with Vietnamese output."""

import unittest

from services.ai_detector import AIDetector


class TestAIDetector(unittest.TestCase):

    def test_human_like_code_scores_low(self):
        clean_code = """
        #include <bits/stdc++.h>
        using namespace std;

        int main() {
            ios_base::sync_with_stdio(false);
            cin.tie(NULL);
            int t;
            if (!(cin >> t)) return 0;
            while (t--) {
                int n;
                cin >> n;
                vector<int> a(n);
                long long sum = 0;
                for (int i = 0; i < n; i++) {
                    cin >> a[i];
                    sum += a[i];
                }
                cout << sum << "\\n";
            }
            return 0;
        }
        """
        result = AIDetector.analyze(clean_code, "GNU C++17")
        self.assertLessEqual(float(result["score"]), 30)
        self.assertEqual(result["status"], "Bình thường")

    def test_chatgpt_generated_code_scores_high(self):
        ai_code = """
        # In this solution, we solve the problem using dynamic programming.
        # Time Complexity: O(N * K)
        # Space Complexity: O(N)
        # Step 1: Initialize the memoization table
        # Note that we handle base cases appropriately.

        def solve():
            '''
            Here is the complete python solution.
            This function computes the optimal substructure and avoids overlapping subproblems.
            '''
            n = int(input())
            memoization_table = [0] * (n + 1)
            for i in range(1, n + 1):
                memoization_table[i] = memoization_table[i - 1] + i
            return memoization_table[n]

        if __name__ == '__main__':
            print(solve())
        """
        result = AIDetector.analyze(ai_code, "Python 3")
        self.assertGreaterEqual(float(result["score"]), 60)

    def test_cp_human_discount(self):
        cp_code = """
        #include <bits/stdc++.h>
        using namespace std;
        #define int long long
        #define pb push_back
        #define all(x) (x).begin(), (x).end()

        int32_t main() {
            ios_base::sync_with_stdio(false);
            cin.tie(NULL);
            // nhap vao n phan tu
            int n; cin >> n;
            vector<int> a(n);
            for (int i = 0; i < n; i++) cin >> a[i];
            // tinh tong
            cout << accumulate(all(a), 0LL) << "\\n";
            return 0;
        }
        """
        result = AIDetector.analyze(cp_code, "GNU C++17")
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["status"], "Bình thường")
        self.assertFalse(result["is_flagged"])

    def test_enterprise_docstring_detection(self):
        enterprise_code = """
        def compute_max_subarray(nums: list) -> int:
            \"\"\"
            Calculates the maximum subarray sum using Kadane's algorithm.

            Args:
                nums (list): The list of integer elements.
            Returns:
                int: The maximum contiguous subarray sum.
            \"\"\"
            current_subarray_sum = 0
            maximum_subarray_sum = float('-inf')
            for x in nums:
                current_subarray_sum = max(x, current_subarray_sum + x)
                maximum_subarray_sum = max(maximum_subarray_sum, current_subarray_sum)
            return maximum_subarray_sum
        """
        result = AIDetector.analyze(enterprise_code, "Python 3")
        self.assertGreaterEqual(float(result["score"]), 40)
        self.assertIn(
            result["status"],
            ["Nghi vấn nhẹ", "Đáng ngờ", "Rất đáng ngờ", "Cực kỳ đáng ngờ"],
        )


if __name__ == "__main__":
    unittest.main()
