"""Kiểm thử tự động cho ExamGeneratorService (Chuỗi AI 3 model và trích xuất JSON)."""

import json
from unittest.mock import AsyncMock, patch
import pytest

try:
    from not_finished.exam_generator.services.exam_generator_service import ExamGeneratorService, exam_generator_service
except ImportError:
    from services.exam_generator_service import ExamGeneratorService, exam_generator_service


class TestExamGeneratorService:
    """Kiểm tra logic xử lý, bóc tách JSON và chuỗi pipeline."""

    def test_extract_json_markdown_block(self):
        """Kiểm tra bóc tách JSON chuẩn từ khối Markdown ```json ... ```."""
        raw_text = """Dưới đây là đề thi do AI tạo ra:
```json
{
  "metadata": {
    "subject": "Toán 12",
    "exam_code": "HH-101"
  },
  "questions": [],
  "solutions": []
}
```
Chúc bạn thi tốt!"""
        extracted = ExamGeneratorService._extract_json(raw_text)
        assert extracted["metadata"]["subject"] == "Toán 12"
        assert extracted["metadata"]["exam_code"] == "HH-101"

    def test_extract_json_bracket_search(self):
        """Kiểm tra tìm kiếm khối ngoặc nhọn { ... } khi AI không dùng markdown block."""
        raw_text = """Bản thảo đề:
{"metadata": {"subject": "Vật Lý 11"}, "questions": [{"number": "1"}], "solutions": []}
Kết thúc tài liệu."""
        extracted = ExamGeneratorService._extract_json(raw_text)
        assert extracted["metadata"]["subject"] == "Vật Lý 11"
        assert len(extracted["questions"]) == 1

    def test_extract_json_invalid_raises_value_error(self):
        """Kiểm tra khi AI trả về chuỗi không có JSON hợp lệ thì ném lỗi chuẩn."""
        with pytest.raises(ValueError, match="JSON"):
            ExamGeneratorService._extract_json("Xin chào, tôi là AI, tôi không thể làm bài này.")

    @pytest.mark.asyncio
    async def test_generate_exam_pipeline_execution(self, tmp_path):
        """Kiểm tra toàn bộ chuỗi pipeline thực thi tuần tự 4 bước và gọi unload model."""
        mock_output = {
            "metadata": {
                "subject": "Tin học C++",
                "exam_code": "HH-777",
                "duration": "45 phút",
                "length_tier": "Ngắn",
            },
            "questions": [
                {
                    "type": "question",
                    "number": "1",
                    "points": "1.0",
                    "text": "Khái niệm mảng một chiều?",
                    "options": ["A. Đúng", "B. Sai"],
                    "has_diagram": False,
                }
            ],
            "solutions": [
                {
                    "number": "1",
                    "is_multiple_choice": True,
                    "correct_key": "A",
                    "explanation": "Mảng là tập hợp phần tử cùng kiểu.",
                    "rubric": [("Chọn đúng A", 1.0)],
                }
            ],
        }

        mock_response_str = f"```json\n{json.dumps(mock_output)}\n```"

        stages_visited = []

        async def mock_notify(stage_text, progress):
            stages_visited.append(stage_text)

        with patch.object(
            ExamGeneratorService, "_query_ollama", new_callable=AsyncMock
        ) as mock_query, patch.object(
            ExamGeneratorService, "_unload_model", new_callable=AsyncMock
        ) as mock_unload:

            mock_query.return_value = mock_response_str

            out_dir = str(tmp_path / "pipeline_test")
            res = await exam_generator_service.generate_exam(
                job_id="TEST-JOB-99",
                subject="Tin học C++",
                style="Trắc nghiệm ngắn",
                length_tier="Ngắn",
                mode="Lite",
                output_format="Both",
                output_dir=out_dir,
                progress_callback=mock_notify,
            )

            # Kiểm tra kết quả trả về
            assert res["job_id"] == "TEST-JOB-99"
            assert "exam_data" in res
            assert len(res["exam_files"]) == 2
            assert len(res["solution_files"]) == 2

            # Kiểm tra các giai đoạn progress callback được kích hoạt
            assert any("[1/4a]" in s or "[1/4b]" in s for s in stages_visited)
            assert any("[2/4]" in s for s in stages_visited)
            assert any("[3/4]" in s for s in stages_visited)
            assert any("[4/4]" in s for s in stages_visited)

            # Kiểm tra Ollama được gọi qua các giai đoạn
            assert mock_query.call_count >= 3

    def test_calculate_scale_multipliers(self):
        """Kiểm tra ma trận độ dài và hệ số chế độ sinh đề."""
        # 1. Ngắn + Lite: 2-3 trang
        scale_lite = ExamGeneratorService.calculate_scale("Ngắn", "Lite")
        assert scale_lite["target_pages"] == "2–3 trang"
        assert scale_lite["target_mc"] >= 4

        # 2. Ngắn + Pro: 4-5 trang
        scale_pro = ExamGeneratorService.calculate_scale("Ngắn", "Pro")
        assert scale_pro["target_pages"] == "4–5 trang"
        assert scale_pro["target_mc"] > scale_lite["target_mc"]

        # 3. Ngắn + Ultra: 8-10 trang
        scale_ultra = ExamGeneratorService.calculate_scale("Ngắn", "Ultra")
        assert scale_ultra["target_pages"] == "8–10 trang"

    @pytest.mark.asyncio
    async def test_job_cancellation(self, tmp_path):
        """Kiểm tra khi nhận tín hiệu cancel_job thì generate_exam ném CancelledError."""
        import asyncio
        cancel_job_id = "JOB-TO-CANCEL-99"
        ExamGeneratorService.cancel_job(cancel_job_id)
        assert ExamGeneratorService.is_job_cancelled(cancel_job_id) is True

        out_dir = str(tmp_path / "cancel_test")
        with pytest.raises(asyncio.CancelledError):
            await exam_generator_service.generate_exam(
                job_id=cancel_job_id,
                subject="Toán 12",
                style="Trắc nghiệm",
                length_tier="Ngắn",
                mode="Lite",
                output_format="PDF",
                output_dir=out_dir,
            )

    @pytest.mark.asyncio
    async def test_tier_model_allocation(self, tmp_path):
        """Kiểm tra Gói Free dùng qwen2.5:4b (Thinking OFF), còn Pro/Ultra dùng qwen3.5:4b (Thinking OFF)."""
        mock_payload = {
            "metadata": {"subject": "Toán 12", "exam_code": "HH-TEST"},
            "questions": [],
            "solutions": []
        }
        mock_resp = f"```json\n{json.dumps(mock_payload)}\n```"

        with patch.object(
            ExamGeneratorService, "_query_ollama", new_callable=AsyncMock
        ) as mock_query, patch.object(
            ExamGeneratorService, "_unload_model", new_callable=AsyncMock
        ):
            mock_query.return_value = mock_resp

            # 1. Test Free Tier -> qwen2.5:4b cho drafter (Call index 1)
            out_free = str(tmp_path / "free_tier")
            await exam_generator_service.generate_exam(
                job_id="TEST-FREE",
                subject="Toán 12",
                style="Trắc nghiệm",
                length_tier="Ngắn",
                mode="Lite",
                output_format="Both",
                output_dir=out_free,
                tier="Free",
            )
            # Call 0 là Gemma Planner (Thinking ON), Call 1 là Qwen Drafter (Thinking OFF)
            assert mock_query.call_args_list[0].kwargs["enable_thinking"] is True
            assert mock_query.call_args_list[1].kwargs["model_name"] == "qwen2.5:4b"
            assert mock_query.call_args_list[1].kwargs["enable_thinking"] is False

            mock_query.reset_mock()

            # 2. Test Pro Tier -> qwen3.5:4b cho drafter (Call index 1)
            out_pro = str(tmp_path / "pro_tier")
            await exam_generator_service.generate_exam(
                job_id="TEST-PRO",
                subject="Toán 12",
                style="Trắc nghiệm",
                length_tier="Ngắn",
                mode="Pro",
                output_format="Both",
                output_dir=out_pro,
                tier="Pro",
            )
            assert mock_query.call_args_list[1].kwargs["model_name"] == "qwen3.5:4b"
            assert mock_query.call_args_list[1].kwargs["enable_thinking"] is False

            mock_query.reset_mock()

            # 3. Test Ultra Tier -> qwen3.5:4b cho drafter (Call index 1)
            out_ultra = str(tmp_path / "ultra_tier")
            await exam_generator_service.generate_exam(
                job_id="TEST-ULTRA",
                subject="Toán 12",
                style="Trắc nghiệm",
                length_tier="Ngắn",
                mode="Ultra",
                output_format="Both",
                output_dir=out_ultra,
                tier="Ultra",
            )
            assert mock_query.call_args_list[1].kwargs["model_name"] == "qwen3.5:4b"
            assert mock_query.call_args_list[1].kwargs["enable_thinking"] is False

    def test_resource_governor_compute_params(self):
        """Kiểm tra ExamResourceGovernor tính toán OllamaParams hợp lệ theo active_jobs và tier."""
        try:
            from not_finished.exam_generator.services.exam_generator_service import ExamResourceGovernor, OllamaParams
        except ImportError:
            from services.exam_generator_service import ExamResourceGovernor, OllamaParams

        # Single active job (bucket 0)
        params_free = ExamResourceGovernor.compute_params(base_num_ctx=8192, active_jobs=1, tier="Free")
        assert isinstance(params_free, OllamaParams)
        assert params_free.num_ctx > 0
        assert params_free.num_thread >= 1
        assert "Server" in params_free.hw_badge

        # Pro tier gets +1 thread bonus
        params_pro = ExamResourceGovernor.compute_params(base_num_ctx=8192, active_jobs=1, tier="Pro")
        assert params_pro.num_thread >= params_free.num_thread

        # High concurrency (active_jobs >= 4 -> bucket 2)
        params_busy = ExamResourceGovernor.compute_params(base_num_ctx=8192, active_jobs=5, tier="Free")
        assert params_busy.num_ctx <= params_free.num_ctx

    def test_compute_mode_ram_gpu_and_ram_cpu(self):
        """Kiểm tra tự động kích hoạt RAM + GPU khi có VRAM hoặc chuyển sang RAM + CPU."""
        try:
            from not_finished.exam_generator.services.exam_generator_service import ExamResourceGovernor
        except ImportError:
            from services.exam_generator_service import ExamResourceGovernor

        with patch("services.hardware.get_gpu_info", return_value=[{"name": "NVIDIA RTX 4090", "vram_free_gb": 16.0}]):
            params_gpu = ExamResourceGovernor.compute_params(base_num_ctx=4096, active_jobs=1, tier="Pro")
            assert params_gpu.compute_mode == "RAM + GPU"
            assert params_gpu.num_gpu == 99
            assert "RAM + GPU" in params_gpu.hw_detail

        with patch("services.hardware.get_gpu_info", return_value=[]):
            params_cpu = ExamResourceGovernor.compute_params(base_num_ctx=4096, active_jobs=1, tier="Free")
            assert params_cpu.compute_mode == "RAM + CPU"
            assert params_cpu.num_gpu == 0
            assert "RAM + CPU" in params_cpu.hw_detail

    def test_auto_tuning_across_different_hardware_configurations(self):
        """Kiểm tra bot tự động co giãn thông số theo nhiều cấu hình phần cứng khác nhau."""
        try:
            from not_finished.exam_generator.services.exam_generator_service import ExamResourceGovernor
        except ImportError:
            from services.exam_generator_service import ExamResourceGovernor
        from services.hardware_profiler import HardwareProfile

        # 1. Cấu hình High-end Server (RTX 4090 24GB VRAM, 32GB RAM trống, 16 cores)
        high_hw = HardwareProfile(
            mode="OPTIMAL", cpu_percent=15.0, cpu_cores=16,
            ram_available_mb=32768.0, ram_total_mb=65536.0, ram_percent=20.0,
            time_limit_bonus=1.0, max_themis_tests=20, inter_test_sleep=0.01,
            badge="🟢 Server: Hiệu năng tối đa", description="High-end server",
        )
        with patch("services.hardware_profiler.ResourceGovernor.get_current_profile", return_value=high_hw), \
             patch("services.hardware.get_gpu_info", return_value=[{"name": "RTX 4090", "vram_free_gb": 22.0}]):
            p_high = ExamResourceGovernor.compute_params(base_num_ctx=8192, active_jobs=1, tier="Ultra")
            assert p_high.compute_mode == "RAM + GPU"
            assert p_high.num_gpu == 99
            assert p_high.num_ctx >= 8192
            assert p_high.num_thread >= 12
            assert "100% VRAM" in p_high.offload_strategy

        # 2. Cấu hình Mid-range Laptop (GTX 1650 4GB VRAM, 16GB RAM, 8 cores)
        mid_hw = HardwareProfile(
            mode="OPTIMAL", cpu_percent=40.0, cpu_cores=8,
            ram_available_mb=12288.0, ram_total_mb=16384.0, ram_percent=50.0,
            time_limit_bonus=1.0, max_themis_tests=20, inter_test_sleep=0.01,
            badge="🟢 Server: Hiệu năng tối đa", description="Mid laptop",
        )
        with patch("services.hardware_profiler.ResourceGovernor.get_current_profile", return_value=mid_hw), \
             patch("services.hardware.get_gpu_info", return_value=[{"name": "GTX 1650", "vram_free_gb": 3.8}]):
            p_mid = ExamResourceGovernor.compute_params(base_num_ctx=8192, active_jobs=1, tier="Pro")
            assert p_mid.compute_mode == "RAM + GPU"
            assert p_mid.num_gpu == 99
            assert "Toàn bộ mô hình trong VRAM" in p_mid.offload_strategy

        # 3. Cấu hình Hybrid Low-VRAM (2GB VRAM trống, 8GB RAM, 6 cores)
        hybrid_hw = HardwareProfile(
            mode="BALANCED", cpu_percent=65.0, cpu_cores=6,
            ram_available_mb=4096.0, ram_total_mb=8192.0, ram_percent=65.0,
            time_limit_bonus=1.15, max_themis_tests=15, inter_test_sleep=0.04,
            badge="🟡 Server: Cân bằng tải", description="Hybrid PC",
        )
        with patch("services.hardware_profiler.ResourceGovernor.get_current_profile", return_value=hybrid_hw), \
             patch("services.hardware.get_gpu_info", return_value=[{"name": "MX450", "vram_free_gb": 2.1}]):
            p_hybrid = ExamResourceGovernor.compute_params(base_num_ctx=4096, active_jobs=1, tier="Free")
            assert p_hybrid.compute_mode == "RAM + GPU"
            assert 8 <= p_hybrid.num_gpu <= 24
            assert "Hybrid" in p_hybrid.offload_strategy

        # 4. Cấu hình Budget VPS / CPU-only (0 GPU, 1.8GB RAM trống, 2 cores, tải cao)
        budget_hw = HardwareProfile(
            mode="CONSTRAINED", cpu_percent=88.0, cpu_cores=2,
            ram_available_mb=1800.0, ram_total_mb=4096.0, ram_percent=85.0,
            time_limit_bonus=1.30, max_themis_tests=10, inter_test_sleep=0.08,
            badge="🔴 Server: Đang bận cao", description="Budget VPS",
        )
        with patch("services.hardware_profiler.ResourceGovernor.get_current_profile", return_value=budget_hw), \
             patch("services.hardware.get_gpu_info", return_value=[]):
            p_budget = ExamResourceGovernor.compute_params(base_num_ctx=8192, active_jobs=2, tier="Free")
            assert p_budget.compute_mode == "RAM + CPU"
            assert p_budget.num_gpu == 0
            assert p_budget.num_ctx <= 2048  # Clamped to save RAM
            assert p_budget.num_thread == 1  # Clamped to prevent freezing

    def test_rate_limit_window(self):
        """Kiểm tra check_rate_limit cho phép tối đa 5 lần gọi liên tiếp và chặn lần thứ 6."""
        try:
            from not_finished.exam_generator.services.exam_generator_service import ExamResourceGovernor, _user_rate_window
        except ImportError:
            from services.exam_generator_service import ExamResourceGovernor, _user_rate_window
        test_user_id = 999888777
        _user_rate_window.pop(test_user_id, None)

        for _ in range(5):
            assert ExamResourceGovernor.check_rate_limit(test_user_id) is True

        # Call thứ 6 trong cùng cửa sổ phải bị chặn
        assert ExamResourceGovernor.check_rate_limit(test_user_id) is False

        # Cleanup
        _user_rate_window.pop(test_user_id, None)

    @pytest.mark.asyncio
    async def test_aiohttp_session_reuse(self):
        """Kiểm tra _get_http_session tái sử dụng TCP connection pool trong cùng event loop."""
        try:
            from not_finished.exam_generator.services.exam_generator_service import _get_http_session
        except ImportError:
            from services.exam_generator_service import _get_http_session

        s1 = await _get_http_session()
        s2 = await _get_http_session()
        assert s1 is s2
        assert not s1.closed

    @pytest.mark.asyncio
    async def test_fast_path_cleaner_skips_clean_text(self, tmp_path):
        """Kiểm tra Fast-Path tự động bỏ qua lượt gọi model cleaner khi văn bản đã sạch."""
        clean_output = {
            "metadata": {"subject": "Toán 12", "exam_code": "HH-101"},
            "questions": [
                {
                    "type": "question",
                    "number": "1",
                    "points": "1.0",
                    "text": "Tìm tập xác định của hàm số $y = \\sqrt{x}$.",
                    "options": ["A. $[0; +\\infty)$", "B. $(-\\infty; 0)$"],
                    "has_diagram": False,
                }
            ],
            "solutions": [
                {
                    "number": "1",
                    "is_multiple_choice": True,
                    "correct_key": "A",
                    "explanation": "Điều kiện xác định là $x \\ge 0$.",
                    "rubric": [("Chọn đúng A", 1.0)],
                }
            ],
        }
        mock_resp = f"```json\n{json.dumps(clean_output)}\n```"

        with patch.object(
            ExamGeneratorService, "_query_ollama", new_callable=AsyncMock
        ) as mock_query, patch.object(
            ExamGeneratorService, "_unload_model", new_callable=AsyncMock
        ):
            mock_query.return_value = mock_resp
            out_dir = str(tmp_path / "fast_path_test")
            res = await exam_generator_service.generate_exam(
                job_id="TEST-FAST-PATH",
                subject="Toán 12",
                style="Trắc nghiệm",
                length_tier="Ngắn",
                mode="Lite",
                output_format="Both",
                output_dir=out_dir,
            )
            # Planner (1) + Drafter (2) + Verifier (3) = 3 calls (Cleaner model được fast-track bỏ qua)
            assert mock_query.call_count == 3
            assert res["job_id"] == "TEST-FAST-PATH"

    def test_diagram_drawer_font_lru_cache(self):
        """Kiểm tra _get_font trong diagram_drawer có LRU cache."""
        try:
            from not_finished.exam_generator.services.diagram_drawer import _get_font
        except ImportError:
            from services.diagram_drawer import _get_font

        f1 = _get_font(14)
        f2 = _get_font(14)
        assert f1 is f2
        assert hasattr(_get_font, "cache_info")
        assert _get_font.cache_info().hits >= 1

    def test_gpu_info_ttl_cache(self):
        """Kiểm tra get_gpu_info trong services/hardware lưu cache TTL 3s."""
        from services.hardware import get_gpu_info, _GPU_CACHE_TTL
        assert _GPU_CACHE_TTL == 3.0
        with patch("services.hardware._detect_gpu_info_internal", return_value=[{"name": "RTX 3060", "vram_free_gb": 12.0}]) as mock_detect:
            gpus1 = get_gpu_info(force_refresh=True)
            assert len(gpus1) == 1
            assert mock_detect.call_count == 1

            # Gọi lần 2 ngay lập tức trong cửa sổ TTL -> không gọi lại _detect_gpu_info_internal
            gpus2 = get_gpu_info(force_refresh=False)
            assert gpus2 == gpus1
            assert mock_detect.call_count == 1

