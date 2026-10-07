"""Unit tests for services/ai_core.py AI Core Supervisor engine."""

import unittest
import asyncio
import time
from unittest.mock import patch, MagicMock

from services.ai_core import AICore, AICoreState, ai_core, DESTRUCTIVE_ACTIONS
from config.settings import settings, AI_MODEL_NAME


class TestAICore(unittest.TestCase):
    """Test suite for AI Core Supervisor and Security Filter."""

    def setUp(self):
        self.core = AICore()

    # ==================== MODEL CENTRALIZATION ====================

    def test_model_name_centralization(self):
        """Kiểm tra model name luôn đồng bộ với settings.AI_MODEL."""
        self.assertEqual(self.core.model_name, AI_MODEL_NAME)
        self.assertEqual(self.core.model_name, "qwen3.5:4b")

    def test_single_source_of_truth(self):
        """Kiểm tra AI_MODEL_NAME import được từ config."""
        self.assertEqual(AI_MODEL_NAME, "qwen3.5:4b")

    # ==================== SECURITY SANITIZATION ====================

    def test_security_sanitization_discord_token(self):
        """Kiểm tra bộ lọc bảo mật tự động ẩn Discord Bot Token."""
        # Ghép chuỗi động để tránh false positive từ GitHub Secret Scanning Push Protection
        token_parts = ["MTAwMTIzNDU2Nzg5MDEyMzQ1Ng", "G12345", "abcdefghijklmnopqrstuvwxyz123456"]
        fake_token = ".".join(token_parts)
        leak_text = f"Lỗi kết nối Discord với Token: {fake_token}"
        sanitized = self.core.sanitize_text(leak_text)
        self.assertNotIn(fake_token, sanitized)
        self.assertIn("[DISCORD_TOKEN_REDACTED]", sanitized)

    def test_security_sanitization_passwords_and_keys(self):
        """Kiểm tra bộ lọc ẩn password, secret, api_key."""
        leak_text = "Database connection string: password=mySuperSecret123, api_key='sk-test-secret-999'"
        sanitized = self.core.sanitize_text(leak_text)
        self.assertNotIn("mySuperSecret123", sanitized)
        self.assertNotIn("sk-test-secret-999", sanitized)
        self.assertIn("[REDACTED]", sanitized)

    def test_sanitize_empty_text(self):
        """Kiểm tra sanitize với text rỗng."""
        self.assertEqual(self.core.sanitize_text(""), "")
        self.assertEqual(self.core.sanitize_text(None), "")

    # ==================== IDLE STATE ====================

    def test_idle_state_on_stable(self):
        """Kiểm tra AI Core ở trạng thái IDLE khi hệ thống ổn định."""
        self.assertEqual(self.core.state, AICoreState.IDLE)
        health = self.core.diagnose_system_health()
        self.assertIn("database", health)
        self.assertIn("problem_bank", health)
        self.assertIn("error_rate", health)
        self.assertIn("ai_core", health)
        self.assertEqual(health["ai_core"]["model"], AI_MODEL_NAME)

    def test_states_are_distinct(self):
        """Kiểm tra các state là distinct."""
        self.assertNotEqual(AICoreState.IDLE, AICoreState.ANALYZING)
        self.assertNotEqual(AICoreState.ANALYZING, AICoreState.PATCHING)

    # ==================== ERROR RECORDING ====================

    def test_record_error_ring_buffer(self):
        """Kiểm tra ghi nhận lỗi hệ thống vào ring buffer."""
        self.core.record_error("TestModule", "Test Exception Message: Something went wrong")
        errors = self.core.get_recent_errors(5)
        self.assertGreaterEqual(len(errors), 1)
        self.assertEqual(errors[-1]["source"], "TestModule")
        self.assertIn("Something went wrong", errors[-1]["message"])

    def test_record_error_maxlen(self):
        """Kiểm tra ring buffer không vượt quá 50 entries."""
        for i in range(60):
            self.core.record_error("Test", f"Error {i}")
        errors = self.core.get_recent_errors(100)
        self.assertLessEqual(len(errors), 50)

    # ==================== DETERMINISTIC QUERIES ====================

    def test_handle_status_query_deterministic(self):
        """Kiểm tra xử lý câu hỏi trạng thái nhanh không tốn token LLM."""
        res = asyncio.run(self.core.handle_user_query("Kiểm tra trạng thái bot", 123456))
        self.assertIn("title", res)
        self.assertIn("description", res)
        self.assertIn(AI_MODEL_NAME, res["title"])
        self.assertEqual(self.core.state, AICoreState.IDLE)

    def test_handle_log_query_deterministic(self):
        """Kiểm tra xử lý đọc log nhanh."""
        res = asyncio.run(self.core.handle_user_query("Kiểm tra log gần đây", 123456))
        self.assertIn("title", res)
        self.assertIn("description", res)
        self.assertEqual(self.core.state, AICoreState.IDLE)

    def test_handle_no_errors_response(self):
        """Kiểm tra phản hồi khi không có lỗi."""
        res = asyncio.run(self.core.handle_user_query("có lỗi gì không", 123456))
        self.assertIn("title", res)
        self.assertIn("Hệ thống không ghi nhận", res["description"])

    def test_handle_permissions_query(self):
        """Kiểm tra query quyền hạn."""
        res = asyncio.run(self.core.handle_user_query("kiểm tra quyền", 123456))
        self.assertIn("title", res)
        self.assertIn("quyền", res["description"].lower())

    def test_handle_find_file_query(self):
        """Kiểm tra tìm file liên quan."""
        res = asyncio.run(self.core.handle_user_query("tìm file admin", 123456))
        self.assertIn("title", res)
        self.assertIn("description", res)

    def test_handle_read_file_query(self):
        """Kiểm tra đọc file."""
        res = asyncio.run(self.core.handle_user_query("đọc file cogs/admin.py", 123456))
        self.assertIn("title", res)
        self.assertIn("description", res)

    # ==================== DESTRUCTIVE ACTION CONFIRMATION ====================

    def test_destructive_action_detection(self):
        """Kiểm tra phát hiện hành động nguy hiểm."""
        confirm_key = self.core.check_destructive_action("xóa database")
        self.assertIsNot(confirm_key, False)
        self.assertIn("confirm_", confirm_key)

    def test_safe_action_passes(self):
        """Kiểm tra hành động an toàn không bị chặn."""
        result = self.core.check_destructive_action("kiểm tra trạng thái bot")
        self.assertFalse(result)

    def test_confirmation_validation(self):
        """Kiểm tra xác nhận hành động."""
        confirm_key = self.core.check_destructive_action("shutdown server")
        self.assertIn(confirm_key, self.core._pending_confirmations)
        self.assertTrue(self.core.validate_confirmation(confirm_key))
        self.assertFalse(self.core.validate_confirmation(confirm_key))

    def test_expired_confirmation(self):
        """Kiểm tra xác nhận hết hạn."""
        confirm_key = self.core.check_destructive_action("delete database")
        self.core._pending_confirmations[confirm_key]["timestamp"] = time.time() - 400
        self.assertFalse(self.core.validate_confirmation(confirm_key))

    def test_destructive_query_blocked(self):
        """Kiểm tra query destructive bị chặn và yêu cầu xác nhận."""
        res = asyncio.run(self.core.handle_user_query("xóa database", 123456))
        self.assertTrue(res.get("requires_confirmation"))
        self.assertIn("confirm_key", res)
        self.assertEqual(res["color"], 0xE74C3C)

    # ==================== SOURCE CODE READING ====================

    def test_read_source_file_nonexistent(self):
        """Kiểm tra đọc file không tồn tại."""
        result = self.core.read_source_file("nonexistent/file.py")
        self.assertIn("error", result)

    def test_read_source_file_non_python(self):
        """Kiểm tra đọc file text ngoài .py (giờ được phép) và chặn file secrets."""
        result = self.core.read_source_file("requirements.txt")
        self.assertNotIn("error", result)
        self.assertIn("content", result)
        blocked = self.core.read_source_file(".env")
        self.assertIn("error", blocked)

    def test_clean_llm_output_no_dup_words(self):
        """Kiểm tra làm sạch từ lặp liên tiếp và thẻ <think>."""
        raw = "<think>đang suy nghĩ</think>Trạng thái tại tại của bot ổn ổn định."
        cleaned = self.core.clean_llm_output(raw)
        self.assertNotIn("<think>", cleaned)
        self.assertNotIn("tại tại", cleaned)
        self.assertNotIn("ổn ổn", cleaned)
        self.assertIn("Trạng thái", cleaned)

    def test_clean_llm_output_think_only_fallback(self):
        """Model chỉ trả <think> thì không được rỗng (fallback giữ text gốc)."""
        raw = "<think>phân tích dài dòng...</think>"
        cleaned = self.core.clean_llm_output(raw)
        self.assertTrue(len(cleaned) > 0)

    def test_clean_llm_output_no_dup_paragraphs(self):
        """Đoạn văn lặp liên tiếp bị gộp thành một."""
        raw = "Quy tắc TeenCode hay.\n\nQuy tắc TeenCode hay.\n\nNội dung khác."
        cleaned = self.core.clean_llm_output(raw)
        self.assertEqual(cleaned.count("Quy tắc TeenCode hay."), 1)
        self.assertIn("Nội dung khác.", cleaned)

    # ==================== FIND RELATED FILES ====================

    def test_find_related_files(self):
        """Kiểm tra tìm file liên quan."""
        results = self.core.find_related_files("rank")
        self.assertIsInstance(results, list)

    def test_find_related_files_no_results(self):
        """Kiểm tra tìm file không có kết quả."""
        # Ghép chuỗi động để keyword không tự xuất hiện trong chính file test này
        keyword = "zzz" + "znonexistent" + "999" + "qqqx"
        results = self.core.find_related_files(keyword)
        self.assertEqual(len(results), 0)

    def test_get_project_tree(self):
        """Kiểm tra liệt kê cây thư mục dự án."""
        tree = self.core.get_project_tree()
        self.assertIsInstance(tree, str)
        self.assertTrue(len(tree) > 0)

    def test_server_rank_query(self):
        """Hỏi rank cao nhất server phải trả lời từ DB, không đổ lỗi thiếu module."""
        res = asyncio.run(self.core.handle_user_query("ai đang rank cao nhất server hiện tại", 123456))
        self.assertTrue("Rank Server" in res.get("title", "") or "Xếp Hạng Server" in res.get("title", ""))
        self.assertTrue(len(res.get("description", "")) > 0)
        self.assertNotIn("chưa được triển khai", res.get("description", ""))

    # ==================== CONVERSATION MEMORY & NATURAL CHAT ====================

    def test_conversation_memory_add_and_retrieve(self):
        """Kiểm tra lưu trữ và truy xuất ngữ cảnh hội thoại đa lượt."""
        mem = self.core.conversation_memory
        session_id = "user_999"
        mem.clear(session_id)

        mem.add_turn(session_id, "Xin chào bạn", "Chào bạn! Mình có thể giúp gì?")
        history = mem.get_history(session_id)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["role"], "user")
        self.assertEqual(history[0]["content"], "Xin chào bạn")
        self.assertEqual(history[1]["role"], "assistant")
        self.assertEqual(history[1]["content"], "Chào bạn! Mình có thể giúp gì?")

        mem.add_turn(session_id, "Bạn tên gì?", "Mình là AI Core của bot!")
        history2 = mem.get_history(session_id)
        self.assertEqual(len(history2), 4)

    def test_conversation_memory_clear(self):
        """Kiểm tra xóa bộ nhớ hội thoại theo session."""
        mem = self.core.conversation_memory
        session_id = "user_888"
        mem.add_turn(session_id, "Tin nhắn 1", "Trả lời 1")
        self.assertEqual(len(mem.get_history(session_id)), 2)

        mem.clear(session_id)
        self.assertEqual(len(mem.get_history(session_id)), 0)

    def test_conversation_memory_max_turns(self):
        """Kiểm tra giới hạn số lượt hội thoại không vượt quá max_turns."""
        from services.ai_core import ConversationMemory
        small_mem = ConversationMemory(max_turns=2)
        s_id = "user_777"
        small_mem.add_turn(s_id, "Q1", "A1")
        small_mem.add_turn(s_id, "Q2", "A2")
        small_mem.add_turn(s_id, "Q3", "A3")
        history = small_mem.get_history(s_id)
        # max_turns=2 -> 2 turns * 2 = 4 messages max
        self.assertEqual(len(history), 4)
        self.assertEqual(history[0]["content"], "Q2")
        self.assertEqual(history[-1]["content"], "A3")

    def test_is_casual_chat_patterns(self):
        """Kiểm tra nhận diện câu chào, xã giao thông thường."""
        casual_samples = ["hi", "hello", "chào bạn", "xin chào", "alo", "ê", "cảm ơn", "bạn là ai"]
        for sample in casual_samples:
            self.assertTrue(self.core._is_casual_chat(sample), f"Should match casual: '{sample}'")

        non_casual_samples = ["đọc file cogs/admin.py", "kiểm tra log gần đây", "viết hàm quicksort python"]
        for sample in non_casual_samples:
            self.assertFalse(self.core._is_casual_chat(sample), f"Should not match casual: '{sample}'")

    def test_reset_chat_command(self):
        """Kiểm tra lệnh reset chat / xóa ký ức."""
        res = asyncio.run(self.core.handle_user_query("reset chat", 123456789))
        self.assertFalse(res.get("is_chat"))
        self.assertIn("Làm Mới Hội Thoại", res.get("title", ""))

    @patch("services.ai_core.AICore.call_chat")
    def test_casual_chat_disabled_does_not_call_chat(self, mock_call_chat):
        """Kiểm tra tính năng chat tự nhiên bị vô hiệu hóa, không gọi call_chat."""
        user_id = 987654321
        res = asyncio.run(self.core.handle_user_query("chào bạn", user_id, is_chat=True))

        self.assertFalse(res.get("is_chat"))
        self.assertIn("tắt", res.get("description", ""))
        mock_call_chat.assert_not_called()


if __name__ == "__main__":
    unittest.main()

