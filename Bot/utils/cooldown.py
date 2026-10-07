"""Rate limiting, cooldown management, and duplicate submission protection."""

import hashlib
import time

from utils.permissions import check_and_log_owner_bypass, is_owner_user


class SubmissionCooldownManager:
    """
    Quản lý thời gian chờ (Cooldown) giữa các lần nộp bài theo từng bậc Rank:
    - Rank T8 -> T4: 10 phút (600 giây)
    - Rank T3 -> HT1: 5 phút (300 giây)
    - Tự động bỏ qua cho OWNER_ID
    """

    COOLDOWN_T8_TO_T4 = 600  # 10 phút
    COOLDOWN_T3_TO_HT1 = 300  # 5 phút

    def __init__(self):
        # Lưu trữ: user_id -> (thời_điểm_nộp_timestamp, tổng_thời_gian_cooldown_giây, rank_thực_hiện)
        self._last_submissions: dict[int, tuple[float, int, str]] = {}

    @classmethod
    def get_cooldown_seconds_for_rank(cls, rank: str | None) -> int:
        """Trả về thời gian cooldown tương ứng: 5 phút (T3->HT1) hoặc 10 phút (T8->T4)."""
        r = (rank or "T8").upper().strip()
        if r in ("T3", "T2", "T1", "MT2", "MT1", "LT2", "HT1", "RHT1"):
            return cls.COOLDOWN_T3_TO_HT1  # 300s (5 phút)
        return cls.COOLDOWN_T8_TO_T4  # 600s (10 phút)

    def get_remaining_cooldown(self, user_id: int) -> tuple[float, int, str]:
        """
        Trả về: (thời_gian_còn_lại_giây, tổng_thời_gian_cooldown_giây, rank_ghi_nhận).
        Nếu đã hết thời gian chờ hoặc là OWNER, trả về (0.0, 0, "").
        """
        if is_owner_user(user_id):
            check_and_log_owner_bypass(user_id, "Submission Cooldown")
            return 0.0, 0, "OWNER"

        now = time.time()
        if user_id not in self._last_submissions:
            return 0.0, 0, ""

        last_time, cd_seconds, rank = self._last_submissions[user_id]
        elapsed = now - last_time
        remaining = cd_seconds - elapsed
        if remaining <= 0:
            return 0.0, cd_seconds, rank
        return max(0.0, remaining), cd_seconds, rank

    def record_submission(self, user_id: int, rank: str = "T8") -> int:
        """Ghi nhận thời điểm hoàn thành bài nộp và kích hoạt Cooldown theo Rank."""
        cd_seconds = self.get_cooldown_seconds_for_rank(rank)
        self._last_submissions[user_id] = (
            time.time(),
            cd_seconds,
            (rank or "T8").upper(),
        )
        return cd_seconds

    def reset_user(self, user_id: int) -> None:
        """Xóa bỏ thời gian chờ cho một thành viên."""
        self._last_submissions.pop(user_id, None)

    @staticmethod
    def format_remaining_time(seconds: float) -> str:
        """Định dạng thời gian chờ còn lại sang dạng 'X phút Y giây' trực quan."""
        sec = int(round(seconds))
        if sec >= 60:
            mins = sec // 60
            rem_sec = sec % 60
            if rem_sec > 0:
                return f"**{mins} phút {rem_sec} giây**"
            return f"**{mins} phút**"
        return f"**{sec} giây**"


class DuplicateSubmissionGuard:
    """Detects rapid identical submissions from the same user to prevent duplicate spam."""

    def __init__(self, memory_window_seconds: int = 60):
        self.memory_window = memory_window_seconds
        # Mapping: (user_id, problem_id, code_hash) -> timestamp
        self._recent_hashes: dict[tuple[int, str, str], float] = {}

    def _hash_code(self, code: str) -> str:
        return hashlib.sha256(code.strip().encode("utf-8")).hexdigest()

    def is_duplicate(self, user_id: int, problem_id: str, code: str) -> bool:
        """Checks whether the user submitted this exact same code for this problem recently."""
        if is_owner_user(user_id):
            return False

        now = time.time()
        # Cleanup expired entries
        self._cleanup(now)

        code_hash = self._hash_code(code)
        key = (user_id, problem_id.upper(), code_hash)

        if key in self._recent_hashes:
            last_time = self._recent_hashes[key]
            if now - last_time < self.memory_window:
                return True

        self._recent_hashes[key] = now
        return False

    def _cleanup(self, now: float) -> None:
        keys_to_delete = [
            k
            for k, timestamp in self._recent_hashes.items()
            if now - timestamp >= self.memory_window
        ]
        for k in keys_to_delete:
            del self._recent_hashes[k]


# Global singletons
submission_cooldown = SubmissionCooldownManager()
duplicate_guard = DuplicateSubmissionGuard(memory_window_seconds=60)
