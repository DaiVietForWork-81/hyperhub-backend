"""Adaptive Resource Governor and Dynamic Hardware Profiler.

Automatically monitors host CPU, RAM, and system load to dynamically scale:
- Concurrency and testcase pacing (inter-test backoff sleep).
- Adaptive time limit calibration (anti-false-TLE on laggy/constrained machines).
- Test suite scaling (8-20 tests based on available memory).
"""

import os
import time
from dataclasses import dataclass

try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


@dataclass
class HardwareProfile:
    """Snapshot thông số tài nguyên máy chủ và chính sách điều tiết thích ứng."""

    mode: str  # "OPTIMAL", "BALANCED", "CONSTRAINED"
    cpu_percent: float  # % CPU đang sử dụng
    cpu_cores: int  # Số nhân CPU
    ram_available_mb: float  # Dung lượng RAM khả dụng (MB)
    ram_total_mb: float  # Tổng dung lượng RAM (MB)
    ram_percent: float  # % RAM đang sử dụng
    time_limit_bonus: float  # Hệ số bù thời gian chống lag máy (1.0x -> 1.35x)
    max_themis_tests: int  # Giới hạn số lượng test Themis (8 -> 20)
    inter_test_sleep: float  # Độ trễ nghỉ giữa các testcase (giây)
    badge: str  # Icon & nhãn trạng thái hiển thị
    description: str  # Mô tả tình trạng hệ thống tiếng Việt


class ResourceGovernor:
    """
    Bộ Điều Tiết Tài Nguyên & Thích Ứng Phần Cứng Thông Minh (Dynamic Adaptive Resource Governor):
    - Tự động kiểm tra CPU và RAM thực tế của máy trước mỗi lượt chấm.
    - Chế độ 🟢 Tối ưu (Optimal): Máy khỏe, CPU < 60%, RAM dư dả -> Chấm tốc độ cao (0.01s sleep, full 20 tests).
    - Chế độ 🟡 Cân bằng (Balanced): CPU 60-80%, RAM trung bình -> Giãn nhịp nhẹ (0.04s sleep, +15% time bonus, 15 tests).
    - Chế độ 🔴 Tiết kiệm/Bảo vệ máy (Constrained): CPU > 80% hoặc RAM < 1GB -> Điều tiết chậm (0.08s sleep, +30% time bonus chống TLE oan, 10 tests).
    """

    _cached_profile: HardwareProfile | None = None
    _last_checked_time: float = 0.0
    _CACHE_TTL: float = 3.0  # Cache 3 giây để tránh gọi psutil liên tục gây overhead

    @classmethod
    def get_current_profile(cls, force_refresh: bool = False) -> HardwareProfile:
        """Đo đạc và tính toán snapshot tài nguyên phần cứng hiện tại."""
        now = time.time()
        if (
            not force_refresh
            and cls._cached_profile is not None
            and (now - cls._last_checked_time) < cls._CACHE_TTL
        ):
            return cls._cached_profile

        cpu_percent = 25.0
        cpu_cores = os.cpu_count() or 4
        ram_available_mb = 4096.0
        ram_total_mb = 8192.0
        ram_percent = 50.0

        if HAS_PSUTIL:
            try:
                cpu_percent = psutil.cpu_percent(interval=None)
                cpu_cores = psutil.cpu_count(logical=True) or cpu_cores
                mem = psutil.virtual_memory()
                ram_available_mb = mem.available / (1024 * 1024)
                ram_total_mb = mem.total / (1024 * 1024)
                ram_percent = mem.percent
            except Exception:
                pass

        # ── Phân loại chế độ thích ứng thông minh ──
        if cpu_percent >= 82.0 or ram_available_mb < 1024.0 or ram_percent >= 88.0:
            # 🔴 Chế độ Tiết Kiệm & Bảo Vệ Máy (Constrained / Low-Resource Throttle)
            mode = "CONSTRAINED"
            time_limit_bonus = 1.30  # Bù thêm 30% thời gian chạy để người dùng không bị TLE oan do nghẽn CPU
            max_themis_tests = 10  # Giảm bớt số test nặng để bảo vệ RAM
            inter_test_sleep = 0.08  # Nghỉ 80ms giữa các test để CPU hạ nhiệt
            badge = "🔴 Tiết kiệm & Bảo vệ máy (Constrained Mode)"
            description = f"Tải hệ thống cao (CPU {cpu_percent:.0f}%, RAM khả dụng {ram_available_mb:.0f}MB). Tự động kích hoạt bù độ trễ +30% Time Limit và điều tiết nhịp chấm 80ms."

        elif cpu_percent >= 60.0 or ram_available_mb < 2048.0 or ram_percent >= 75.0:
            # 🟡 Chế độ Cân Bằng (Balanced Mode)
            mode = "BALANCED"
            time_limit_bonus = 1.15  # Bù thêm 15% thời gian chạy
            max_themis_tests = 15
            inter_test_sleep = 0.04  # Nghỉ 40ms giữa các test
            badge = "🟡 Cân bằng tải (Balanced Mode)"
            description = f"Hệ thống hoạt động vừa phải (CPU {cpu_percent:.0f}%, RAM khả dụng {ram_available_mb:.0f}MB). Tự động bù +15% Time Limit và điều tiết nhịp chấm 40ms."

        else:
            # 🟢 Chế độ Tối Ưu (Optimal Performance Mode)
            mode = "OPTIMAL"
            time_limit_bonus = 1.0  # Chuẩn 100% thời gian gốc
            max_themis_tests = 20  # Chạy trọn vẹn bộ 20 testcases
            inter_test_sleep = 0.01  # Nhịp siêu tốc 10ms
            badge = "🟢 Hiệu năng tối đa (Optimal Mode)"
            description = f"Tài nguyên dồi dào (CPU {cpu_percent:.0f}%, RAM khả dụng {ram_available_mb:.0f}MB, {cpu_cores} Cores). Chấm siêu tốc với trọn bộ 20 Testcases."

        profile = HardwareProfile(
            mode=mode,
            cpu_percent=cpu_percent,
            cpu_cores=cpu_cores,
            ram_available_mb=ram_available_mb,
            ram_total_mb=ram_total_mb,
            ram_percent=ram_percent,
            time_limit_bonus=time_limit_bonus,
            max_themis_tests=max_themis_tests,
            inter_test_sleep=inter_test_sleep,
            badge=badge,
            description=description,
        )

        cls._cached_profile = profile
        cls._last_checked_time = now
        return profile
