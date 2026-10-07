"""Kiểm thử tự động cho UserTokenService (Quản lý Gói Hyper, Hạn mức Token, Reset 00:00 UTC+7)."""

import datetime
from unittest.mock import MagicMock
import pytest

try:
    from not_finished.exam_generator.services.user_token_service import UserTokenService, user_token_service, TIER_SPECS
except ImportError:
    from services.user_token_service import UserTokenService, user_token_service, TIER_SPECS
from config.settings import settings


class TestUserTokenService:
    """Kiểm tra toàn diện logic kinh tế token và nhận diện Role."""

    def test_determine_tier_from_member_roles(self):
        """Kiểm tra nhận diện đúng 4 gói thành viên từ Role Discord."""
        elite_role = MagicMock()
        elite_role.id = settings.ROLE_HYPER_ELITE_ID

        ultra_role = MagicMock()
        ultra_role.id = settings.ROLE_HYPER_ULTRA_ID

        pro_role = MagicMock()
        pro_role.id = settings.ROLE_HYPER_PRO_ID

        free_role = MagicMock()
        free_role.id = settings.ROLE_HYPER_FREE_ID

        # Member có role Elite
        m_elite = MagicMock()
        m_elite.roles = [elite_role, free_role]
        assert UserTokenService.determine_tier_from_member(m_elite) == "Elite"

        # Member có role Ultra
        m_ultra = MagicMock()
        m_ultra.roles = [ultra_role]
        assert UserTokenService.determine_tier_from_member(m_ultra) == "Ultra"

        # Member có role Pro
        m_pro = MagicMock()
        m_pro.roles = [pro_role]
        assert UserTokenService.determine_tier_from_member(m_pro) == "Pro"

        # Member chỉ có role Free hoặc không có role
        m_free = MagicMock()
        m_free.roles = [free_role]
        assert UserTokenService.determine_tier_from_member(m_free) == "Free"

        m_none = MagicMock()
        m_none.roles = []
        assert UserTokenService.determine_tier_from_member(m_none) == "Free"
        assert UserTokenService.determine_tier_from_member(None) == "Free"

    def test_calculate_token_cost_benchmarks(self):
        """Khớp chính xác 100% các mốc benchmark kinh tế đã thống nhất."""
        # 1. Benchmark Free: IELTS 8.0 (1.4) + Dài (35) + Pro (2.0) = 98 tokens
        cost_free, details_free = UserTokenService.calculate_token_cost(
            length="Dài", mode="Pro", subject="IELTS 8.0 Chuyên sâu"
        )
        assert cost_free == 98
        assert details_free["base_points"] == 35
        assert details_free["mode_mult"] == 2.0
        assert details_free["subj_mult"] == 1.4
        # 200 tokens / 98 ≈ 2 lần/ngày!
        assert 200 // cost_free == 2

        # 2. Benchmark Pro: IELTS (1.4) + To (60) + Ultra (4.0) = 336 tokens
        cost_pro, details_pro = UserTokenService.calculate_token_cost(
            length="To", mode="Ultra", subject="Luyện thi IELTS Speaking & Writing"
        )
        assert cost_pro == 336
        assert details_pro["base_points"] == 60
        assert details_pro["mode_mult"] == 4.0
        # 700 tokens / 336 = 2 lần/ngày!
        assert 700 // cost_pro == 2

        # 3. Benchmark Ultra: 2800 tokens / 336 = 8 lần/ngày!
        assert 2800 // cost_pro == 8

        # 4. Đề Phổ thông cơ bản: Ngắn (10) + Lite (1.0) + Toán (1.0) = 10 tokens
        cost_basic, _ = UserTokenService.calculate_token_cost(
            length="Ngắn", mode="Lite", subject="Toán 10 cơ bản"
        )
        assert cost_basic == 10

        # 5. Đề Lập trình C++: Vừa (20) + Flash (1.5) + C++ (1.2) = 36 tokens
        cost_cpp, _ = UserTokenService.calculate_token_cost(
            length="Vừa", mode="Flash", subject="Lập trình C++ Mảng và Chuỗi"
        )
        assert cost_cpp == 36

    def test_progress_bar_render(self):
        """Kiểm tra thanh tiến trình trực quan hiển thị đúng tỷ lệ."""
        # Đã dùng 0/200 -> toàn bộ ô trống
        bar_0 = UserTokenService.render_progress_bar(0, 200, length=10)
        assert "░" * 10 in bar_0

        # Đã dùng 100/200 (50%) -> 5 ô đầy, 5 ô trống
        bar_50 = UserTokenService.render_progress_bar(100, 200, length=10)
        assert "█" * 5 in bar_50
        assert "░" * 5 in bar_50

        # Đã dùng 200/200 (100%) -> 10 ô đầy
        bar_100 = UserTokenService.render_progress_bar(200, 200, length=10)
        assert "█" * 10 in bar_100

    @pytest.mark.asyncio
    async def test_token_deduct_and_refund_lifecycle(self):
        """Kiểm tra chu trình: Khởi tạo -> Trừ token -> Hoàn 100% token khi có lỗi."""
        from database.database import init_db
        await init_db()
        test_user_id = 999888777111

        # 1. Khởi tạo tài khoản mới (mặc định Free 200 tokens)
        token_info = await user_token_service.get_or_sync_user_token(test_user_id)
        assert token_info["tier"] == "Free"
        assert token_info["daily_tokens"] == 200
        assert token_info["used_tokens_today"] == 0
        assert token_info["remaining_tokens"] == 200

        # 2. Trừ 98 tokens (tạo đề IELTS Dài Pro)
        deducted = await user_token_service.deduct_tokens(test_user_id, 98)
        assert deducted is True

        updated_info = await user_token_service.get_or_sync_user_token(test_user_id)
        assert updated_info["used_tokens_today"] == 98
        assert updated_info["remaining_tokens"] == 102
        assert updated_info["total_generated"] == 1

        # 3. Hoàn 100% token khi xảy ra lỗi
        await user_token_service.refund_tokens(test_user_id, 98, reason="Test refund")

        refunded_info = await user_token_service.get_or_sync_user_token(test_user_id)
        assert refunded_info["used_tokens_today"] == 0
        assert refunded_info["remaining_tokens"] == 200
        assert refunded_info["total_generated"] == 0

    @pytest.mark.asyncio
    async def test_exam_job_search_and_checkpoint(self):
        """Kiểm tra ghi nhận job, cập nhật checkpoint, và tìm kiếm trong kho đề."""
        import uuid
        from database.database import init_db
        await init_db()
        test_job_id = f"JOB-SEARCH-{uuid.uuid4().hex[:6].upper()}"
        test_uid = 888777666222

        await user_token_service.record_exam_job(
            job_id=test_job_id,
            discord_id=test_uid,
            thread_id=123456789,
            subject="IELTS Academic 8.0 Reading",
            style="Trắc nghiệm và tự luận",
            length_tier="Ngắn",
            mode="Lite",
            output_format="Both",
            token_cost=30,
        )

        # Cập nhật checkpoint và trạng thái COMPLETED
        sample_cp = '{"metadata": {"subject": "IELTS Academic 8.0 Reading"}}'
        await user_token_service.update_exam_job(
            job_id=test_job_id,
            status="COMPLETED",
            checkpoint_data=sample_cp,
            is_shuffled=True,
        )

        job = await user_token_service.get_exam_job(test_job_id)
        assert job is not None
        assert job.job_id == test_job_id
        assert job.status == "COMPLETED"
        assert job.checkpoint_data == sample_cp
        assert job.is_shuffled is True

        # Tìm kiếm theo từ khóa
        found = await user_token_service.search_exam_jobs("IELTS", limit=5)
        assert any(j.job_id == test_job_id for j in found)
