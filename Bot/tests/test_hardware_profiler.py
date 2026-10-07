# Unit tests for Dynamic Adaptive Resource Governor and Hardware Profiler.
import unittest

from services.hardware_profiler import HardwareProfile, ResourceGovernor


class TestHardwareProfiler(unittest.TestCase):

    def test_get_current_profile_validity(self):
        profile = ResourceGovernor.get_current_profile(force_refresh=True)
        self.assertIsInstance(profile, HardwareProfile)
        self.assertIn(profile.mode, ["OPTIMAL", "BALANCED", "CONSTRAINED"])
        self.assertGreaterEqual(profile.cpu_percent, 0.0)
        self.assertGreater(profile.cpu_cores, 0)
        self.assertGreater(profile.ram_available_mb, 0.0)
        self.assertGreater(profile.ram_total_mb, 0.0)
        self.assertGreaterEqual(profile.time_limit_bonus, 1.0)
        self.assertGreaterEqual(profile.max_themis_tests, 8)
        self.assertGreaterEqual(profile.inter_test_sleep, 0.0)
        self.assertTrue(len(profile.badge) > 0)
        self.assertTrue(len(profile.description) > 0)

    def test_cache_ttl(self):
        p1 = ResourceGovernor.get_current_profile()
        p2 = ResourceGovernor.get_current_profile()
        self.assertIs(p1, p2)


if __name__ == "__main__":
    unittest.main()
