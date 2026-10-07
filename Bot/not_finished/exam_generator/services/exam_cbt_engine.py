"""Động cơ Thi Thử Trực Tuyến & Chấm Điểm Khảo Thí (Exam CBT Engine).

Chuẩn bị sẵn kiến trúc, State Machine và Session Manager cho:
1. Giao diện thi trắc nghiệm tương tác trên Discord (Modal / Button Component).
2. Tích hợp Web Dashboard thi trực tuyến trong tương lai.
3. Chấm điểm tự động chuẩn barem BGDĐT 2025 (MCQ, Đúng/Sai 4 ý, Điền số ngắn).
4. Phân tích ma trận nhận thức Bloom (Nhận biết, Thông hiểu, Vận dụng) và bẫy tư duy học sinh dính phải.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional

from utils.logger import get_logger

logger = get_logger("ExamCBTEngine")


class ExamSessionStatus(str, Enum):
    """Trạng thái vòng đời phiên thi trực tuyến."""

    CREATED = "CREATED"          # Vừa tạo phiên, chờ thí sinh bấm bắt đầu
    IN_PROGRESS = "IN_PROGRESS"  # Đang làm bài, đồng hồ đếm ngược đang chạy
    COMPLETED = "COMPLETED"      # Thí sinh chủ động bấm nộp bài
    TIMED_OUT = "TIMED_OUT"      # Hết thời gian làm bài, hệ thống tự động thu bài
    CANCELLED = "CANCELLED"      # Hủy phiên thi


@dataclass
class QuestionSubmission:
    """Bản ghi câu trả lời của thí sinh cho một câu hỏi."""

    question_number: str
    selected_key: str | dict[str, str]  # "A" cho trắc nghiệm hoặc {"a": "Đ", "b": "S"...} cho Đúng/Sai
    time_spent_seconds: float = 0.0
    change_count: int = 0
    submitted_at: float = field(default_factory=time.time)


@dataclass
class ExamScoreReport:
    """Báo cáo kết quả và phân tích năng lực thí sinh sau khi nộp bài."""

    session_id: str
    user_id: int
    exam_title: str
    total_score: float
    max_score: float
    correct_count: int
    total_questions: int
    percentage: float
    duration_used_seconds: float
    bloom_analysis: dict[str, dict[str, Any]] = field(default_factory=dict)
    mistakes_analysis: list[dict[str, Any]] = field(default_factory=list)
    detailed_results: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExamSession:
    """Phiên thi trắc nghiệm độc lập của một người dùng."""

    session_id: str
    user_id: int
    exam_data: dict[str, Any]
    duration_minutes: int
    status: ExamSessionStatus = ExamSessionStatus.CREATED
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    user_answers: dict[str, QuestionSubmission] = field(default_factory=dict)
    score_report: Optional[ExamScoreReport] = None

    @property
    def remaining_seconds(self) -> float:
        """Thời gian còn lại của bài thi tính bằng giây."""
        if self.status != ExamSessionStatus.IN_PROGRESS or not self.started_at:
            return float(self.duration_minutes * 60)
        elapsed = time.time() - self.started_at
        total = self.duration_minutes * 60
        return max(0.0, total - elapsed)

    @property
    def is_expired(self) -> bool:
        """Kiểm tra bài thi đã hết giờ hay chưa."""
        return self.remaining_seconds <= 0.0


class ExamCBTManager:
    """Bộ điều phối phiên thi trực tuyến (CBT Session Manager)."""

    def __init__(self) -> None:
        self._sessions: dict[str, ExamSession] = {}

    def create_session(
        self,
        user_id: int,
        exam_data: dict[str, Any],
        duration_minutes: Optional[int] = None,
    ) -> ExamSession:
        """Khởi tạo một phiên thi trực tuyến mới cho thí sinh."""
        session_id = f"cbt_{uuid.uuid4().hex[:12]}"
        meta = exam_data.get("metadata", {})
        dur = duration_minutes or int(meta.get("duration", "45").split()[0] if meta.get("duration") else 45)

        session = ExamSession(
            session_id=session_id,
            user_id=user_id,
            exam_data=exam_data,
            duration_minutes=dur,
        )
        self._sessions[session_id] = session
        logger.info(f"📝 Đã tạo phiên thi CBT {session_id} cho User {user_id} ({dur} phút).")
        return session

    def start_session(self, session_id: str) -> ExamSession:
        """Bắt đầu tính giờ làm bài thi."""
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Không tìm thấy phiên thi {session_id}")
        if session.status != ExamSessionStatus.CREATED:
            return session

        session.status = ExamSessionStatus.IN_PROGRESS
        session.started_at = time.time()
        logger.info(f"⏳ Phiên thi {session_id} đã bắt đầu tính giờ.")
        return session

    def submit_answer(
        self,
        session_id: str,
        question_number: str,
        selected_key: str | dict[str, str],
        time_spent: float = 0.0,
        time_spent_seconds: Optional[float] = None,
    ) -> QuestionSubmission:
        """Ghi nhận lựa chọn của thí sinh cho một câu hỏi."""
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Không tìm thấy phiên thi {session_id}")

        if session.status != ExamSessionStatus.IN_PROGRESS:
            raise RuntimeError(f"Phiên thi không trong trạng thái làm bài (Hiện tại: {session.status.value})")

        if session.is_expired:
            session.status = ExamSessionStatus.TIMED_OUT
            self.finish_session(session_id)
            raise TimeoutError("Đã hết thời gian làm bài, hệ thống đã tự động thu bài!")

        actual_time = time_spent_seconds if time_spent_seconds is not None else time_spent
        q_key = str(question_number)
        if q_key in session.user_answers:
            prev = session.user_answers[q_key]
            prev.selected_key = selected_key
            prev.change_count += 1
            prev.time_spent_seconds += actual_time
            prev.submitted_at = time.time()
        else:
            session.user_answers[q_key] = QuestionSubmission(
                question_number=q_key,
                selected_key=selected_key,
                time_spent_seconds=actual_time,
            )

        return session.user_answers[q_key]

    def cancel_session(self, session_id: str) -> bool:
        """Hủy phiên thi trực tuyến của thí sinh."""
        session = self.get_session(session_id)
        if not session:
            return False
        session.status = ExamSessionStatus.CANCELLED
        logger.info(f"🚫 Phiên thi {session_id} đã bị hủy.")
        return True

    def finish_session(self, session_id: str) -> ExamScoreReport:
        """Thu bài, chấm điểm tự động và xuất báo cáo phân tích năng lực."""
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Không tìm thấy phiên thi {session_id}")

        if session.status not in (ExamSessionStatus.IN_PROGRESS, ExamSessionStatus.TIMED_OUT):
            if session.score_report:
                return session.score_report

        if session.status != ExamSessionStatus.TIMED_OUT:
            session.status = ExamSessionStatus.COMPLETED

        session.finished_at = time.time()
        used_time = (session.finished_at - (session.started_at or session.created_at))

        # ── Chấm điểm tự động theo barem ──
        solutions = session.exam_data.get("solutions", [])
        questions = [q for q in session.exam_data.get("questions", []) if q.get("type") == "question"]
        sol_map = {str(s.get("number")): s for s in solutions}

        total_score = 0.0
        max_score = 0.0
        correct_count = 0
        mistakes_analysis: list[dict[str, Any]] = []
        detailed_results: list[dict[str, Any]] = []

        for q in questions:
            q_num = str(q.get("number"))
            sol = sol_map.get(q_num, {})
            user_sub = session.user_answers.get(q_num)
            user_ans = user_sub.selected_key if user_sub else None

            points_str = str(q.get("points", "0.5")).replace("điểm", "").replace("đ", "").strip()
            try:
                q_max_pts = float(points_str)
            except ValueError:
                q_max_pts = 0.5
            max_score += q_max_pts

            correct_key = sol.get("correct_key")
            is_correct = False
            q_earned_pts = 0.0

            # 1. Trắc nghiệm đơn phương án (A, B, C, D)
            if isinstance(user_ans, str) and correct_key and isinstance(correct_key, str):
                if user_ans.strip().upper() == correct_key.strip().upper():
                    is_correct = True
                    q_earned_pts = q_max_pts
                    correct_count += 1
                else:
                    mistakes_analysis.append({
                        "question_number": q_num,
                        "question_text": q.get("text", "")[:120],
                        "user_answer": user_ans,
                        "user_selected": user_ans,
                        "correct_answer": correct_key,
                        "correct_key": correct_key,
                        "common_mistake": sol.get("common_mistakes", "Nhầm lẫn kiến thức trọng tâm"),
                        "trap_warning": sol.get("common_mistakes", "Nhầm lẫn kiến thức trọng tâm"),
                        "explanation": sol.get("explanation", ""),
                    })

            # 2. Trắc nghiệm Đúng/Sai 4 ý chuẩn QĐ 764/BGDĐT
            elif isinstance(user_ans, dict) and isinstance(correct_key, dict):
                correct_sub = sum(
                    1 for k, v in user_ans.items() if str(v).strip().upper() == str(correct_key.get(k, "")).strip().upper()
                )
                from not_finished.exam_generator.services.exam_blueprint_engine import ExamBlueprintEngine
                tf_score = ExamBlueprintEngine.calculate_true_false_score(correct_sub)
                q_earned_pts = tf_score
                if correct_sub == 4:
                    is_correct = True
                    correct_count += 1
                else:
                    mistakes_analysis.append({
                        "question_number": q_num,
                        "question_text": q.get("text", "")[:120],
                        "user_subitems": user_ans,
                        "correct_subitems": correct_key,
                        "correct_subitems_count": correct_sub,
                        "earned_points": tf_score,
                        "common_mistake": sol.get("common_mistakes", "Chưa phân biệt được các mệnh đề đúng/sai"),
                        "explanation": sol.get("explanation", ""),
                    })

            total_score += q_earned_pts
            detailed_results.append({
                "number": q_num,
                "user_answer": user_ans,
                "correct_answer": correct_key,
                "earned_points": round(q_earned_pts, 2),
                "max_points": round(q_max_pts, 2),
                "is_correct": is_correct,
            })

        total_questions = len(questions)
        pct = round((total_score / max_score * 100), 1) if max_score > 0 else 0.0

        report = ExamScoreReport(
            session_id=session_id,
            user_id=session.user_id,
            exam_title=session.exam_data.get("metadata", {}).get("exam_title", "Đề Thi Trắc Nghiệm"),
            total_score=round(total_score, 2),
            max_score=round(max_score, 2),
            correct_count=correct_count,
            total_questions=total_questions,
            percentage=pct,
            duration_used_seconds=round(used_time, 1),
            mistakes_analysis=mistakes_analysis,
            detailed_results=detailed_results,
        )
        session.score_report = report
        logger.info(
            f"🎯 Phiên thi {session_id} đã chấm xong: {total_score:.2f}/{max_score:.2f} điểm "
            f"({pct}% - Đúng {correct_count}/{total_questions} câu)."
        )
        return report

    def get_session(self, session_id: str) -> Optional[ExamSession]:
        """Lấy phiên thi theo mã định danh."""
        return self._sessions.get(session_id)

    def get_active_sessions_for_user(self, user_id: int) -> list[ExamSession]:
        """Lấy danh sách các phiên thi đang mở của thí sinh."""
        return [
            s for s in self._sessions.values()
            if s.user_id == user_id and s.status in (ExamSessionStatus.CREATED, ExamSessionStatus.IN_PROGRESS)
        ]

    def get_active_session(self, user_id: int) -> Optional[ExamSession]:
        """Lấy phiên thi đang mở gần nhất của thí sinh."""
        active = self.get_active_sessions_for_user(user_id)
        return active[-1] if active else None


# Singleton instance dùng chung
exam_cbt_manager = ExamCBTManager()
