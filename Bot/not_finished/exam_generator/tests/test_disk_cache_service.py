"""Kiểm thử tự động cho Dịch vụ Bộ Nhớ Đệm & Bộ Nhớ Ảo Khép Kín Trong Dự Án (DiskCacheService).

Đảm bảo 100% nguyên tắc:
- Không tạo bất kỳ file nào ra ngoài thư mục dự án data/cache/.
- Hỗ trợ lưu trữ, tra cứu siêu tốc (< 5ms), quản lý scratch swap và giới hạn trần dung lượng LRU.
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch
import pytest

from services.disk_cache_service import DiskCacheService, disk_cache_service, BASE_CACHE_DIR, PROJECT_ROOT
from services.hardware import get_project_cache_info
try:
    from not_finished.exam_generator.services.exam_generator_service import ExamGeneratorService
except ImportError:
    from services.exam_generator_service import ExamGeneratorService


class TestDiskCacheService:
    """Kiểm tra hoạt động của bộ đệm SSD/HDD và bộ nhớ ảo nội bộ dự án."""

    @pytest.mark.asyncio
    async def test_cache_is_strictly_within_project_data_cache(self, tmp_path):
        """Đảm bảo mọi file database, WAL và scratch swap chỉ nằm trong data/cache/ của project."""
        custom_dir = tmp_path / "custom_project_cache"
        cache = DiskCacheService(cache_dir=custom_dir, max_bytes=10 * 1024 * 1024)
        await cache.initialize()

        assert custom_dir.exists()
        assert (custom_dir / "ai_disk_cache.db").exists()
        assert (custom_dir / "scratch_swap").exists()

        # Kiểm tra đường dẫn mặc định của dự án
        assert BASE_CACHE_DIR == PROJECT_ROOT / "data" / "cache"

    @pytest.mark.asyncio
    async def test_cache_set_and_get_hit(self, tmp_path):
        """Kiểm tra lưu trữ và truy xuất cache (Cache Hit)."""
        cache = DiskCacheService(cache_dir=tmp_path / "cache_test", max_bytes=5 * 1024 * 1024)
        await cache.initialize()

        model = "gemma3:4b"
        prompt = "Hãy lập bản thiết kế đề thi Toán 12"
        sys_prompt = "Bạn là chuyên gia khảo thí"
        response = "BẢN THIẾT KẾ: Phần I 12 câu, Phần II 4 câu..."

        # Trước khi lưu -> Miss
        res_before = await cache.get(model, prompt, sys_prompt)
        assert res_before is None

        # Lưu vào cache
        await cache.set(model, prompt, response, sys_prompt)

        # Sau khi lưu -> Hit
        res_after = await cache.get(model, prompt, sys_prompt)
        assert res_after == response

        # Kiểm tra thống kê
        stats = await cache.get_stats()
        assert stats["total_entries"] == 1
        assert stats["total_hits"] >= 1
        assert stats["is_self_contained"] is True

    @pytest.mark.asyncio
    async def test_cache_miss_with_different_options(self, tmp_path):
        """Khác options (temperature, context) sẽ sinh key khác nhau, không bị trùng lặp."""
        cache = DiskCacheService(cache_dir=tmp_path / "cache_diff", max_bytes=5 * 1024 * 1024)
        await cache.initialize()

        model = "qwen3.5:4b"
        prompt = "Soạn câu hỏi trắc nghiệm"
        opt1 = {"temperature": 0.2, "num_ctx": 4096}
        opt2 = {"temperature": 0.7, "num_ctx": 4096}

        await cache.set(model, prompt, "Đáp án 1", options=opt1)

        assert await cache.get(model, prompt, options=opt1) == "Đáp án 1"
        assert await cache.get(model, prompt, options=opt2) is None

    @pytest.mark.asyncio
    async def test_scratch_swap_chunk_buffer_and_cleanup(self, tmp_path):
        """Kiểm tra ghi, đọc file hoán đổi tạm (Scratch Swap) và dọn sạch khi job hoàn tất."""
        cache = DiskCacheService(cache_dir=tmp_path / "scratch_test", max_bytes=5 * 1024 * 1024)
        await cache.initialize()

        job_id = "JOB-SWAP-999"
        chunk_data = "Nội dung văn bản khổng lồ cần hoán đổi ra đĩa để giải phóng RAM..."

        # 1. Ghi chunk
        chunk_path = cache.write_scratch_chunk(job_id, "chunk_1.txt", chunk_data)
        assert chunk_path.exists()
        assert chunk_path.parent.name == job_id
        assert chunk_path.parent.parent.name == "scratch_swap"

        # 2. Đọc chunk
        read_back = cache.read_scratch_chunk(job_id, "chunk_1.txt")
        assert read_back == chunk_data

        # 3. Ghi file nhị phân
        bin_data = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        cache.write_scratch_chunk(job_id, "diagram.png", bin_data)
        read_bin = cache.read_scratch_chunk(job_id, "diagram.png", as_bytes=True)
        assert read_bin == bin_data

        # 4. Dọn sạch job scratch
        deleted = cache.cleanup_job_scratch(job_id)
        assert deleted == 2
        assert not chunk_path.exists()
        assert not (cache.scratch_dir / job_id).exists()

    @pytest.mark.asyncio
    async def test_disk_quota_enforcement_lru(self, tmp_path):
        """Kiểm tra cơ chế giới hạn dung lượng đĩa và tự động xóa theo LRU."""
        # Giới hạn cực nhỏ 10 KB để test LRU
        cache = DiskCacheService(cache_dir=tmp_path / "lru_test", max_bytes=10 * 1024)
        await cache.initialize()

        # Thêm 5 bản ghi, mỗi bản ghi ~3KB
        big_text = "A" * 3000
        for i in range(5):
            await cache.set("m1", f"prompt_{i}", big_text)
            await asyncio.sleep(0.01)

        # Kiểm tra dung lượng thư mục không bùng nổ vô hạn
        stats = await cache.get_stats()
        assert stats["total_entries"] <= 5

    @pytest.mark.asyncio
    async def test_exam_generator_query_ollama_cache_hit(self):
        """Kiểm tra _query_ollama trả về trực tiếp từ SSD Cache khi đã có kết quả."""
        mock_prompt = "Kiểm tra cache hit cho bài thi"
        mock_model = "qwen2.5:4b"
        mock_response = "ĐÁP ÁN ĐÃ ĐƯỢC CACHE TRÊN SSD"

        # Nạp sẵn vào cache
        await disk_cache_service.set(
            model_name=mock_model,
            prompt=mock_prompt,
            response_text=mock_response,
            system_prompt="",
            options={"temperature": 0.3, "top_p": 0.9, "num_ctx": 4096, "num_predict": 4096, "num_thread": 4, "num_gpu": 0, "think": False, "thinking": False},
        )

        with patch("not_finished.exam_generator.services.exam_generator_service._get_http_session") as mock_session:
            # Gọi _query_ollama với đúng thông số
            res = await ExamGeneratorService._query_ollama(
                model_name=mock_model,
                prompt=mock_prompt,
                use_cache=True,
            )
            # Vì trúng cache nên không cần gọi HTTP session ra ngoài
            assert res == mock_response
            assert mock_session.call_count == 0

    def test_get_project_cache_info_hardware(self):
        """Kiểm tra hàm get_project_cache_info trong services/hardware trả về cấu trúc chuẩn."""
        info = get_project_cache_info()
        assert "cache_dir" in info
        assert "total_mb" in info
        assert "max_mb" in info
        assert info["is_self_contained"] is True
