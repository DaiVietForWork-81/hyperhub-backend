"""Testcase generator creating official CF sample suites and 15-20 Themis Multi-Test suites for Step 2."""

import random
from dataclasses import dataclass


@dataclass
class TestCase:
    id: int
    input_data: str
    expected_output: str | None = None
    is_sample: bool = True
    test_type: str = (
        "SAMPLE"  # "SAMPLE", "EDGE_CASE", "TLE_STRESS", "MEMORY_STRESS", "RANDOM"
    )
    description: str = ""


class TestcaseGenerator:
    """Produces test cases including samples and structured problem test cases."""

    @classmethod
    def generate_step1_sample_suite(
        cls,
        sample_tests: list[tuple[str, str]],
        problem_id: str = "",
        time_limit: float = 2.0,
    ) -> list[TestCase]:
        """
        Xây dựng bộ Testcase mẫu chính thức từ Codeforces cho Bước 1.
        """
        suite: list[TestCase] = []
        test_id = 1

        if sample_tests:
            for inp, out in sample_tests:
                clean_inp = inp.strip() + "\n"
                clean_out = out.strip()
                suite.append(
                    TestCase(
                        id=test_id,
                        input_data=clean_inp,
                        expected_output=clean_out,
                        is_sample=True,
                        test_type="SAMPLE",
                        description=f"Test Mẫu Codeforces #{test_id}",
                    )
                )
                test_id += 1
        else:
            suite.append(
                TestCase(
                    id=1,
                    input_data="1\n",
                    expected_output=None,
                    is_sample=True,
                    test_type="SAMPLE",
                    description="Kiểm tra thực thi mẫu cơ bản",
                )
            )

        return suite

    @classmethod
    def generate_themis_step2_suite(
        cls,
        sample_tests: list[tuple[str, str]] | None = None,
        problem_id: str = "",
        time_limit: float = 2.0,
        problem_rating: int = 1200,
        target_test_count: int = 18,
    ) -> list[TestCase]:
        """
        Xây dựng bộ 15-20 Testcase Themis Đa Tầng cho Bước 2:
        - 🧪 Test 01 - 03: Testcase mẫu chính thức (Sample I/O)
        - 🎯 Test 04 - 08: Testcase trường hợp biên (Edge cases: N=1, số âm, số lớn)
        - ⚡ Test 09 - 14: Testcase áp lực thời gian (TLE Stress: N=10^5, N=2*10^5, bẫy O(N^2))
        - 💾 Test 15 - 17: Testcase bộ nhớ & đồ thị sâu (Memory / Recursion Stress)
        - 🔁 Test 18 - 20: Testcase ngẫu nhiên đa dạng (Randomized Stress Inputs)
        """
        suite: list[TestCase] = []
        test_id = 1
        samples = sample_tests or []

        # 1. Thêm các testcase mẫu chính thức (Test 01 - 03)
        for inp, out in samples[:4]:
            suite.append(
                TestCase(
                    id=test_id,
                    input_data=inp.strip() + "\n",
                    expected_output=out.strip(),
                    is_sample=True,
                    test_type="SAMPLE",
                    description=f"Themis #{test_id:02d} [Mẫu Codeforces]: Kiểm tra tính đúng đắn cơ bản",
                )
            )
            test_id += 1

        # Phân tích cấu trúc dữ liệu đầu vào từ sample
        sample_input = samples[0][0].strip() if samples else "1\n"
        sample_lines = [
            line.strip() for line in sample_input.splitlines() if line.strip()
        ]

        is_single_int = len(sample_lines) == 1 and sample_lines[0].lstrip("-").isdigit()
        is_single_line_ints = len(sample_lines) == 1 and all(
            tok.lstrip("-").isdigit() for tok in sample_lines[0].split()
        )
        num_tokens_in_line1 = len(sample_lines[0].split()) if sample_lines else 1

        rng = random.Random(42)

        if is_single_int:
            # Bài toán nhận vào duy nhất 1 số nguyên (ví dụ: 4A, 1A...)
            val_base = int(sample_lines[0])
            test_values = [
                (2, "Số chẵn nhỏ (N=2)"),
                (4, "Số chẵn cơ bản (N=4)"),
                (1, "Số lẻ tối tiểu (N=1)"),
                (3, "Số lẻ (N=3)"),
                (8, "Giá trị mẫu (N=8)"),
                (10, "Số chẵn (N=10)"),
                (98, "Số chẵn gần 100 (N=98)"),
                (99, "Số lẻ gần 100 (N=99)"),
                (100, "Giới hạn đề bài N=100"),
                (1000000, "Kiểm tra số lớn N=10^6"),
                (2000000000, "Kiểm tra số lớn chạm 2*10^9"),
                (999999999, "Kiểm tra số lẻ cực đại"),
                (50, "Số chẵn trung bình N=50"),
                (75, "Số lẻ trung bình N=75"),
                (12, "Số chẵn N=12"),
                (24, "Số chẵn N=24"),
                (36, "Số chẵn N=36"),
                (48, "Số chẵn N=48"),
            ]
            for val, desc in test_values:
                if test_id > target_test_count:
                    break
                if val in (1, 2, 100):
                    t_type = "EDGE_CASE"
                elif val in (1000000, 2000000000):
                    t_type = "TLE_STRESS"
                elif val == 999999999:
                    t_type = "MEMORY_STRESS"
                else:
                    t_type = "RANDOM"

                exp_out = None
                if problem_id.upper().startswith("4A"):
                    exp_out = "YES" if (val > 2 and val % 2 == 0) else "NO"

                suite.append(
                    TestCase(
                        id=test_id,
                        input_data=f"{val}\n",
                        expected_output=exp_out,
                        is_sample=False,
                        test_type=t_type,
                        description=f"Themis #{test_id:02d}: {desc}",
                    )
                )
                test_id += 1

        elif is_single_line_ints:
            # Bài toán nhận vào 1 dòng gồm K số nguyên
            k = num_tokens_in_line1
            for _ in range(target_test_count - test_id + 1):
                nums = [str(rng.randint(1, 1000)) for _ in range(k)]
                suite.append(
                    TestCase(
                        id=test_id,
                        input_data=" ".join(nums) + "\n",
                        expected_output=None,
                        is_sample=False,
                        test_type="RANDOM",
                        description=f"Themis #{test_id:02d} [Dòng K={k} số nguyên]: Dữ liệu kiểm thử ngẫu nhiên",
                    )
                )
                test_id += 1

        else:
            # Bài toán mảng, chuỗi hoặc đa testcases
            # Kiểm tra xem dòng 1 có phải là số lượng testcases T không
            has_multi_test = False
            try:
                first_int = int(sample_lines[0])
                if 1 <= first_int <= 1000 and len(sample_lines) > 2:
                    has_multi_test = True
            except ValueError:
                has_multi_test = False

            # Test biên
            edge_scenarios = [
                (
                    "1\n1\n0\n" if has_multi_test else "1\n0\n",
                    "Trường hợp biên cực tiểu: N = 1, giá trị = 0",
                ),
                (
                    "1\n1\n1000000000\n" if has_multi_test else "1\n1000000000\n",
                    "Trường hợp biên số lớn: N = 1, giá trị = 10^9",
                ),
                (
                    "1\n1\n1\n" if has_multi_test else "1\n1\n",
                    "Trường hợp biên tối giản N = 1, giá trị = 1",
                ),
                (
                    "1\n5\n1 1 1 1 1\n" if has_multi_test else "5\n1 1 1 1 1\n",
                    "Trường hợp tất cả phần tử bằng nhau",
                ),
                (
                    "1\n5\n5 4 3 2 1\n" if has_multi_test else "5\n5 4 3 2 1\n",
                    "Trường hợp mảng giảm dần",
                ),
            ]

            for inp_text, desc in edge_scenarios:
                if test_id > target_test_count:
                    break
                suite.append(
                    TestCase(
                        id=test_id,
                        input_data=inp_text,
                        expected_output=None,
                        is_sample=False,
                        test_type="EDGE_CASE",
                        description=f"Themis #{test_id:02d} [Test Biên]: {desc}",
                    )
                )
                test_id += 1

            # Test Áp Lực TLE
            max_n = 200000 if problem_rating >= 1400 else 50000
            rev_arr = " ".join(str(x) for x in range(min(50000, max_n), 0, -1))
            tle_rev = (
                f"1\n{min(50000, max_n)}\n{rev_arr}\n"
                if has_multi_test
                else f"{min(50000, max_n)}\n{rev_arr}\n"
            )
            suite.append(
                TestCase(
                    id=test_id,
                    input_data=tle_rev,
                    expected_output=None,
                    is_sample=False,
                    test_type="TLE_STRESS",
                    description=f"Themis #{test_id:02d} [Bẫy TLE]: Mảng đảo ngược kích thước lớn",
                )
            )
            test_id += 1

            rand_arr = " ".join(
                str(rng.randint(1, 10**9)) for _ in range(min(50000, max_n))
            )
            tle_max = (
                f"1\n{min(50000, max_n)}\n{rand_arr}\n"
                if has_multi_test
                else f"{min(50000, max_n)}\n{rand_arr}\n"
            )
            suite.append(
                TestCase(
                    id=test_id,
                    input_data=tle_max,
                    expected_output=None,
                    is_sample=False,
                    test_type="TLE_STRESS",
                    description=f"Themis #{test_id:02d} [Bẫy TLE]: Mảng ngẫu nhiên cực đại N={min(50000, max_n):,}",
                )
            )
            test_id += 1

            # Test Random
            while test_id <= max(18, target_test_count):
                size = rng.randint(5, 100)
                arr_str = " ".join(str(rng.randint(1, 1000)) for _ in range(size))
                rand_inp = (
                    f"1\n{size}\n{arr_str}\n"
                    if has_multi_test
                    else f"{size}\n{arr_str}\n"
                )
                suite.append(
                    TestCase(
                        id=test_id,
                        input_data=rand_inp,
                        expected_output=None,
                        is_sample=False,
                        test_type="RANDOM",
                        description=f"Themis #{test_id:02d} [Ngẫu Nhiên]: Dữ liệu ngẫu nhiên (Size={size})",
                    )
                )
                test_id += 1

        return suite

    @classmethod
    def generate_suite(
        cls,
        sample_tests: list[tuple[str, str]],
        problem_id: str = "",
        time_limit: float = 2.0,
    ) -> list[TestCase]:
        """Tương thích ngược: Sinh bộ test mẫu cơ bản."""
        return cls.generate_step1_sample_suite(sample_tests, problem_id, time_limit)

    @classmethod
    def build_full_test_suite(
        cls,
        sample_tests: list[tuple[str, str]] | None = None,
        time_limit: float = 2.0,
        problem_id: str = "",
        samples: list[tuple[str, str]] | None = None,
    ) -> list[TestCase]:
        """Tương thích ngược: Xây dựng bộ test mẫu ban đầu."""
        tests = sample_tests if sample_tests is not None else (samples or [])
        return cls.generate_step1_sample_suite(tests, problem_id, time_limit)
