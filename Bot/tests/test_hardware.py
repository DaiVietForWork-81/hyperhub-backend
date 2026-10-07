"""Test auto-profile Ollama theo từng hệ thống (services/hardware.py)."""

import unittest

from services.hardware import classify_system, recommend_llm_options


def _hw(vram=None, ram_free=10.0, ram_total=16.0):
    gpus = []
    if vram is not None:
        gpus = [{
            "name": "NVIDIA GeForce RTX 4060",
            "vendor": "nvidia",
            "vram_total_gb": vram,
            "vram_free_gb": vram,
            "usage_percent": 0.0,
            "backend": "nvidia-smi",
        }]
    return {
        "gpus": gpus,
        "ram": {"total_gb": ram_total, "free_gb": ram_free, "usage_percent": 30.0},
    }


class TestSystemProfiles(unittest.TestCase):
    def test_nvidia_strong_full_gpu(self):
        """NVIDIA VRAM >= 6GB -> ép full GPU + ctx lớn."""
        rec = recommend_llm_options(_hw(vram=12.0, ram_free=10.0))
        self.assertEqual(rec["profile"], "nvidia_full")
        self.assertEqual(rec["num_gpu"], 999)
        self.assertEqual(rec["num_ctx"], 8192)

    def test_nvidia_small_hybrid(self):
        """NVIDIA VRAM < 6GB -> hybrid, ctx vừa."""
        rec = recommend_llm_options(_hw(vram=4.0, ram_free=10.0))
        self.assertEqual(rec["profile"], "nvidia_hybrid")
        self.assertIsNone(rec["num_gpu"])
        self.assertEqual(rec["num_ctx"], 4096)

    def test_cpu_only_ram_based(self):
        """Không NVIDIA -> auto, ctx theo RAM."""
        rec = recommend_llm_options(_hw(vram=None, ram_free=1.0))
        self.assertEqual(rec["profile"], "auto")
        self.assertIsNone(rec["num_gpu"])
        self.assertEqual(rec["num_ctx"], 2048)

    def test_low_ram_caps_ctx_even_on_strong_gpu(self):
        """GPU mạnh nhưng RAM hệ thống ít -> hạ ctx để tránh OOM."""
        rec = recommend_llm_options(_hw(vram=12.0, ram_free=2.0))
        self.assertEqual(rec["profile"], "nvidia_full")
        self.assertLessEqual(rec["num_ctx"], 4096)

    def test_classify_labels(self):
        self.assertIn("NVIDIA", classify_system(_hw(vram=8.0))["label"])
        self.assertEqual(classify_system(_hw(vram=None))["profile"], "auto")

    def test_amd_strong_full_gpu(self):
        """AMD Radeon VRAM >= 6GB -> profile amd_full, ép 999 layer lên ROCm."""
        hw = {
            "gpus": [{
                "name": "AMD Radeon RX 6700 XT",
                "vendor": "amd",
                "vram_total_gb": 12.0,
                "vram_free_gb": 12.0,
                "usage_percent": 0.0,
                "backend": "rocm-smi",
            }],
            "ram": {"total_gb": 32.0, "free_gb": 16.0, "usage_percent": 20.0},
        }
        rec = recommend_llm_options(hw)
        self.assertEqual(rec["profile"], "amd_full")
        self.assertEqual(rec["num_gpu"], 999)
        self.assertEqual(rec["num_ctx"], 8192)

    def test_amd_legacy_safe_cpu_fallback(self):
        """AMD Radeon cũ VRAM <= 2GB -> profile amd_legacy, ép num_gpu=0 để chống lỗi rác chữ."""
        hw = {
            "gpus": [{
                "name": "AMD Radeon R5 M335",
                "vendor": "amd",
                "vram_total_gb": 2.0,
                "vram_free_gb": 1.0,
                "usage_percent": 0.0,
                "backend": "wmi",
            }],
            "ram": {"total_gb": 12.0, "free_gb": 1.1, "usage_percent": 90.0},
        }
        rec = recommend_llm_options(hw)
        self.assertEqual(rec["profile"], "amd_legacy")
        self.assertEqual(rec["num_gpu"], 0)
        self.assertEqual(rec["num_ctx"], 2048)

    def test_amd_hybrid(self):
        """AMD Radeon tầm trung (4GB) -> profile amd_hybrid."""
        hw = {
            "gpus": [{
                "name": "AMD Radeon RX 550",
                "vendor": "amd",
                "vram_total_gb": 4.0,
                "vram_free_gb": 3.5,
                "usage_percent": 0.0,
                "backend": "lspci",
            }],
            "ram": {"total_gb": 16.0, "free_gb": 8.0, "usage_percent": 50.0},
        }
        rec = recommend_llm_options(hw)
        self.assertEqual(rec["profile"], "amd_hybrid")
        self.assertIsNone(rec["num_gpu"])


if __name__ == "__main__":
    unittest.main()
