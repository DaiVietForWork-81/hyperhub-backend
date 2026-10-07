"""
tests/test_high_tier_problems_and_escalation.py
Bộ kiểm thử toàn diện cho hệ thống đề bài Ranked 1:1:
1. Audit kiểm duyệt chất lượng đề bài (loại bỏ bài dummy, print('OK')).
2. Độ chính xác 100% của các bài toán Olympic chuyên sâu (LT2, MT2, HT2, LT1, MT1, HT1).
3. Cơ chế leo thang độ khó theo từng chặng (+1.5% mỗi chặng, mở rộng trần tier khi tie-break).
4. Ngăn chặn triệt để tình trạng tier cao bị fallback về bài tier thấp (T8-T5).
5. Hiển thị áp lực đấu trường (escalation badge) trong Rich Embeds.
"""

import io
import json
import os
import sys
import pytest

from services.ai_problem_upgrader import (
    HIGH_TIER_EXEMPLARY_PROBLEMS,
    audit_problem,
    batch_clean_and_upgrade_bank,
    upgrade_problem,
)
from services.duel_problems import (
    PROBLEM_BANK,
    RANK_ORDER,
    DuelProblem,
    get_problem_by_tier,
    get_problem_for_match,
    get_rank_index,
)


# ==============================================================================
# 1. TEST AUDIT FUNCTIONALITY
# ==============================================================================

def test_audit_problem_detects_dummy_print_ok():
    """Kiểm tra audit_problem phát hiện và loại bỏ mã giả print('OK')."""
    dummy_prob = {
        "id": "dummy_01",
        "name": "Dummy Problem",
        "tier": "LT2",
        "statement": "Hãy in ra kết quả cho bài toán này.",
        "constraints": "Subtask 1 (50%): N <= 10\nSubtask 2 (50%): N <= 1000",
        "sample_input": "1 2 3",
        "sample_output": "OK",
        "secret_tests": [{"input": "1", "output": "OK"}],
        "solution_code": "print('OK')",
    }
    is_valid, issues = audit_problem(dummy_prob)
    assert not is_valid
    assert any("print('OK')" in issue or "mã giả" in issue for issue in issues)


def test_audit_problem_detects_lack_of_subtasks_in_high_tier():
    """Tier cao (LT2 - HT1) bắt buộc phải có phân chia 3 Subtasks."""
    high_tier_no_subtasks = {
        "id": "test_no_subtasks",
        "name": "Bài toán không có subtasks",
        "tier": "HT1",
        "statement": "Cho đồ thị N đỉnh M cạnh. Tính số đường đi ngắn nhất.",
        "constraints": "1 <= N <= 1000, 1 <= M <= 10000. Giới hạn 1s.",
        "sample_input": "3 3\n1 2 1\n2 3 1\n1 3 2",
        "sample_output": "2",
        "secret_tests": [
            {"input": "1", "output": "1"},
            {"input": "2", "output": "2"},
            {"input": "3", "output": "3"},
            {"input": "4", "output": "4"},
        ],
        "solution_code": "import sys\nprint('2')",
    }
    is_valid, issues = audit_problem(high_tier_no_subtasks)
    assert not is_valid
    assert any("subtask" in issue.lower() for issue in issues)


def test_audit_problem_accepts_all_exemplary_problems():
    """Tất cả 6 bài toán Olympic mẫu cho High Tier đều phải vượt qua audit 100%."""
    for prob in HIGH_TIER_EXEMPLARY_PROBLEMS:
        is_valid, issues = audit_problem(prob)
        assert is_valid, f"Problem {prob['id']} failed audit: {issues}"


# ==============================================================================
# 2. TEST REFERENCE SOLUTIONS PASS 100% TESTCASES
# ==============================================================================

@pytest.mark.parametrize("prob", HIGH_TIER_EXEMPLARY_PROBLEMS, ids=lambda p: p["id"])
def test_exemplary_problem_reference_solution(prob):
    """Đảm bảo code mẫu của từng bài Olympic chạy chính xác 100% trên sample và secret tests."""
    code = prob["solution_code"]
    tests = [{"input": prob["sample_input"], "output": prob["sample_output"]}] + prob["secret_tests"]

    for idx, t in enumerate(tests):
        inp = t["input"].strip()
        expected = t["output"].strip().split()

        old_stdin, old_stdout = sys.stdin, sys.stdout
        sys.stdin = io.StringIO(inp)
        sys.stdout = io.StringIO()
        try:
            exec(code, {"__name__": "__main__"})
            actual = sys.stdout.getvalue().strip().split()
            assert actual == expected, (
                f"Problem {prob['id']} failed on test #{idx}.\n"
                f"Input: {inp}\nExpected: {expected}\nActual: {actual}"
            )
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout


# ==============================================================================
# 3. TEST DIFFICULTY ESCALATION ACROSS ROUNDS
# ==============================================================================

def test_round_escalation_bonus_pct():
    """Kiểm tra công thức tăng độ khó: Chặng 1 (+0%), Chặng 2 (+1.5%), Chặng 3 (+3.0%)."""
    prob_r1 = get_problem_for_match("LT2", "LT2", round_index=1)
    assert getattr(prob_r1, "round_index", 1) == 1
    assert getattr(prob_r1, "difficulty_bonus_pct", 0) == 0.0

    prob_r2 = get_problem_for_match("LT2", "LT2", round_index=2)
    assert getattr(prob_r2, "round_index", 1) == 2
    assert getattr(prob_r2, "difficulty_bonus_pct", 0) == 1.5

    prob_r3 = get_problem_for_match("LT2", "LT2", round_index=3)
    assert getattr(prob_r3, "round_index", 1) == 3
    assert getattr(prob_r3, "difficulty_bonus_pct", 0) == 3.0

    prob_r5 = get_problem_for_match("LT2", "LT2", round_index=5)
    assert getattr(prob_r5, "round_index", 1) == 5
    assert getattr(prob_r5, "difficulty_bonus_pct", 0) == 6.0


def test_high_tier_duels_never_fallback_to_low_tier():
    """
    Đấu thủ ở Tier cao (LT2 -> HT1) tuyệt đối không bao giờ nhận đề T8-T5,
    ngay cả khi exclude_ids chứa nhiều đề.
    """
    high_tiers = ["LT2", "MT2", "HT2", "LT1", "MT1", "HT1"]
    for tier in high_tiers:
        exclude = {"duel_lt2_olympic_segtree_lazy", "duel_mt2_olympic_statespace_dijkstra"}
        prob = get_problem_for_match(tier, tier, exclude_ids=exclude, round_index=2)
        rank_idx = get_rank_index(prob.tier)
        assert rank_idx >= 6, f"For tier {tier}, got problem {prob.id} of low tier {prob.tier}!"
        assert prob.tier in high_tiers


def test_round_3_escalates_tier_cap():
    """Từ chặng 3 trở đi, ngưỡng trần được mở rộng +1 Tier để phân hóa tie-break."""
    prob_r3 = get_problem_for_match("MT2", "MT2", round_index=3)
    assert prob_r3.tier in ("MT2", "HT2", "LT1", "MT1", "HT1")


# ==============================================================================
# 4. TEST EMBED RENDERING WITH ESCALATION BADGE
# ==============================================================================

def test_embed_shows_escalation_badge_when_round_gt_1():
    """Render embed chứa dòng lửa '🔥 Áp lực đấu trường' khi chặng đấu > 1."""
    prob = get_problem_for_match("MT2", "MT2", round_index=2)
    embeds = prob.render_embeds()
    info_embed = embeds[0]

    assert "Áp lực đấu trường" in info_embed.description
    assert "+1.5%" in info_embed.description
    assert "Chặng 2" in info_embed.description


def test_embed_no_escalation_badge_in_round_1():
    """Chặng 1 tiêu chuẩn không hiển thị dòng leo thang độ khó."""
    prob = get_problem_for_match("MT2", "MT2", round_index=1)
    embeds = prob.render_embeds()
    info_embed = embeds[0]

    assert "Áp lực đấu trường" not in info_embed.description


# ==============================================================================
# 5. TEST AI PROBLEMS JSON INTEGRITY
# ==============================================================================

def test_ai_problems_json_contains_zero_dummy_problems():
    """Kiểm tra tệp data/ai_problems.json không còn sót bất kỳ bài rác print('OK') nào."""
    project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    ai_problems_path = os.path.join(project_dir, "data", "ai_problems.json")

    assert os.path.exists(ai_problems_path)
    with open(ai_problems_path, "r", encoding="utf-8") as f:
        problems = json.load(f)

    for p in problems:
        is_clean, issues = audit_problem(p)
        assert is_clean, f"Problem {p.get('id')} in ai_problems.json is invalid: {issues}"
