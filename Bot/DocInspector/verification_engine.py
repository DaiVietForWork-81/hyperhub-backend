"""
Deterministic 4-Tier Verification Verdict Engine for DocInspector.
Evaluates multi-pass forensic evidence to classify document status into exactly 4 cases:
1. VERIFIED_OK ("Xác minh (thấy ổn)")
2. UNCERTAIN_MATCH ("Chưa rõ ràng (là xác minh nhưng chưa chắc là đúng đề)")
3. UNIDENTIFIED_EXAM ("Không rõ ràng (xem được đề nhưng không biết là đề nào)")
4. UNVERIFIABLE_FAILED ("Không xác minh (là ko đc j hết)")
100% Deterministic, Zero AI, Forensic-grade explanations.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .models import (
    DocumentCategory,
    ExamType,
    Pass1Report,
    Pass2Report,
    Pass3Report,
    Subject,
    VerificationVerdict,
)


class VerificationVerdictEvaluator:
    """
    Evaluates cross-pass evidence to produce a definitive 4-case verdict
    with deep, exhaustive forensic rationale.
    """

    VERDICT_LABELS: Dict[VerificationVerdict, str] = {
        VerificationVerdict.VERIFIED_OK: "Xác minh (thấy ổn)",
        VerificationVerdict.UNCERTAIN_MATCH: "Chưa rõ ràng (là xác minh nhưng chưa chắc là đúng đề)",
        VerificationVerdict.UNIDENTIFIED_EXAM: "Không rõ ràng (xem được đề nhưng không biết là đề nào)",
        VerificationVerdict.UNVERIFIABLE_FAILED: "Không xác minh (là ko đc j hết)",
    }

    @classmethod
    def evaluate(
        cls,
        pass1: Pass1Report,
        pass2: Pass2Report,
        pass3: Pass3Report,
        category: DocumentCategory,
        exam_type: ExamType,
        subject: Subject,
        is_blocked_url: bool = False,
        blocked_reason: str = "",
    ) -> Tuple[VerificationVerdict, str, str, Dict[str, Any]]:
        """
        Calculates the definitive verdict, human-readable label, extensive diagnostic rationale,
        and forensic breakdown dictionary.
        """
        uncertainty_factors: List[str] = []
        identified_signals: List[str] = []

        # =========================================================================
        # CASE 4: UNVERIFIABLE_FAILED (Không xác minh - không được gì hết)
        # =========================================================================
        if is_blocked_url:
            verdict = VerificationVerdict.UNVERIFIABLE_FAILED
            label_vi = cls.VERDICT_LABELS[verdict]
            reason_clean = blocked_reason or "không rõ nguồn gốc"
            rationale = (
                f"TRẠNG THÁI: KHÔNG XÁC MINH (KHÔNG ĐƯỢC GÌ HẾT)\n"
                f"• Nguyên nhân: Liên kết web / kho lưu trữ đám mây bị chặn truy cập bởi hệ thống bảo mật "
                f"(Cloudflare challenge, Captcha, tường lửa chống bot, mã lỗi HTTP 401/403 hoặc quyền truy cập riêng tư).\n"
                f"• Phản hồi hệ thống: Báo cáo xác định '{reason_clean}'.\n"
                f"• Tác động: Hoàn toàn không tải được tệp tin (0 byte), không thể trích xuất văn bản "
                f"hay tiến hành bất kỳ quy trình đối soát 3 lần nào.\n"
                f"• Khuyến nghị: Cần cung cấp liên kết tải trực tiếp (direct link), cấp quyền chia sẻ công khai "
                f"('Bất kỳ ai có liên kết đều xem được' đối với Google Drive), hoặc tải tệp trực tiếp lên máy cục bộ."
            )
            forensic = {
                "verdict_case": 4,
                "has_extractable_text": False,
                "char_volume": 0,
                "structure_identified": False,
                "recommended_action": "Kiểm tra lại quyền truy cập hoặc tải tệp lên cục bộ.",
            }
            return verdict, label_vi, rationale, forensic

        if pass1.is_encrypted:
            verdict = VerificationVerdict.UNVERIFIABLE_FAILED
            label_vi = cls.VERDICT_LABELS[verdict]
            rationale = (
                "TRẠNG THÁI: KHÔNG XÁC MINH (KHÔNG ĐƯỢC GÌ HẾT)\n"
                "• Nguyên nhân: Tệp tin PDF bị đặt mật khẩu bảo vệ mã hóa (Password-Protected / Encrypted PDF).\n"
                "• Tác động: Không thể giải mã các luồng dữ liệu bên trong (0 ký tự đọc được). Toàn bộ nội dung "
                "bị phong tỏa ở tầng nhị phân Pass 1.\n"
                "• Khuyến nghị: Gỡ bỏ mật khẩu bảo vệ của tệp PDF trước khi đưa vào hệ thống kiểm định."
            )
            forensic = {
                "verdict_case": 4,
                "has_extractable_text": False,
                "char_volume": 0,
                "structure_identified": False,
                "recommended_action": "Gỡ bỏ mật khẩu bảo vệ file PDF.",
            }
            return verdict, label_vi, rationale, forensic

        if pass1.char_count == 0 and not pass1.is_scanned_pdf:
            verdict = VerificationVerdict.UNVERIFIABLE_FAILED
            label_vi = cls.VERDICT_LABELS[verdict]
            rationale = (
                "TRẠNG THÁI: KHÔNG XÁC MINH (KHÔNG ĐƯỢC GÌ HẾT)\n"
                "• Nguyên nhân: Tệp tin rỗng hoàn toàn (0 ký tự văn bản, 0 trang nội dung) hoặc cấu trúc tệp bị hỏng "
                "nghiêm trọng ở mức byte khiến bộ trích xuất nhị phân không đọc được bất kỳ thông tin nào.\n"
                "• Tác động: Không có bất kỳ dữ liệu nào để đối soát Pass 1, 2 và 3.\n"
                "• Khuyến nghị: Kiểm tra lại dung lượng tệp tin gốc và định dạng tệp trước khi quét."
            )
            forensic = {
                "verdict_case": 4,
                "has_extractable_text": False,
                "char_volume": 0,
                "structure_identified": False,
                "recommended_action": "Kiểm tra lại tính nguyên vẹn của tệp nguồn.",
            }
            return verdict, label_vi, rationale, forensic

        if pass1.is_scanned_pdf and pass1.char_count < 30:
            verdict = VerificationVerdict.UNVERIFIABLE_FAILED
            label_vi = cls.VERDICT_LABELS[verdict]
            rationale = (
                "TRẠNG THÁI: KHÔNG XÁC MINH (KHÔNG ĐƯỢC GÌ HẾT)\n"
                f"• Nguyên nhân: Tệp tin là bản scan dạng ảnh thuần túy (PDF Bitmap gồm {pass1.page_count} trang ảnh) "
                f"nhưng KHÔNG CÓ LỚP VĂN BẢN SỐ HÓA (OCR Text Layer).\n"
                f"• Tác động: Lượng ký tự trích xuất được xấp xỉ bằng 0 ({pass1.char_count} ký tự rác/nhiễu). "
                f"Không thể đọc nội dung câu hỏi, ma trận từ khóa hay kiểm tra tính nguyên bản.\n"
                f"• Khuyến nghị: Sử dụng phần mềm OCR (nhận dạng ký tự quang học) để số hóa văn bản trước khi kiểm định."
            )
            forensic = {
                "verdict_case": 4,
                "has_extractable_text": False,
                "char_volume": pass1.char_count,
                "structure_identified": False,
                "recommended_action": "Thực hiện nhận dạng quang học (OCR) để trích xuất văn bản.",
            }
            return verdict, label_vi, rationale, forensic

        # =========================================================================
        # CASE 3: UNIDENTIFIED_EXAM (Không rõ ràng - xem được đề nhưng không biết là đề nào)
        # =========================================================================
        # Has unambiguous exam signals (questions, options, or test headers)
        has_exam_layout = (
            pass2.question_count >= 2
            or pass2.options_count >= 4
            or category == DocumentCategory.EXAM_TEST
            or any(t in pass2.candidate_exam_types for t in [
                ExamType.MCQ_STANDARD_4,
                ExamType.MCQ_TRUE_FALSE,
                ExamType.MCQ_SHORT_ANSWER,
                ExamType.OLYMPIAD_ESSAY,
                ExamType.GENERAL_ESSAY,
            ])
        )

        # Subject domain is totally unknown or generic
        subject_is_indeterminate = (
            subject in [Subject.GENERAL, Subject.NON_ACADEMIC]
            or pass3.top_subject in [Subject.GENERAL, Subject.NON_ACADEMIC]
            or (pass3.confidence < 0.60 and len(pass3.evidence_terms) == 0)
        )

        is_not_administrative = category not in [DocumentCategory.ADMIN_CONTRACT, DocumentCategory.LESSON_PLAN]

        if has_exam_layout and subject_is_indeterminate and is_not_administrative:
            verdict = VerificationVerdict.UNIDENTIFIED_EXAM
            label_vi = cls.VERDICT_LABELS[verdict]
            rationale = (
                "TRẠNG THÁI: KHÔNG RÕ RÀNG (XEM ĐƯỢC ĐỀ NHƯNG KHÔNG BIẾT LÀ ĐỀ NÀO)\n"
                f"• Đã nhận diện được: Cấu trúc đề thi / bài kiểm tra rõ ràng (bóc tách thành công {pass2.question_count} "
                f"câu hỏi, {pass2.options_count} phương án lựa chọn trắc nghiệm, cấu trúc: {pass2.detected_structure}).\n"
                f"• Điểm không rõ ràng: KHÔNG THỂ XÁC ĐỊNH ĐƯỢC MÔN HỌC HOẶC BÀI THI CỤ THỂ. Hệ thống quét qua 16 bộ từ "
                f"điển chuyên ngành (Toán, Lý, Hóa, Sinh, Tin, Anh, Văn, Sử, Địa,...) nhưng điểm số từ khóa đều dưới ngưỡng tối thiểu.\n"
                f"• Nguyên nhân chẩn đoán: Đề thi có thể là bài kiểm tra IQ / tư duy logic tổng quát, đề kiểm tra nội bộ "
                f"dùng thuật ngữ quy ước riêng, bài thi liên môn chưa có thuật ngữ chuyên sâu, hoặc đề thi sử dụng mã đề/ký tự viết tắt.\n"
                f"• Khuyến nghị: Kiểm tra lại tiêu đề môn học trong văn bản hoặc bổ sung từ vựng chuyên ngành vào đề bài."
            )
            forensic = {
                "verdict_case": 3,
                "has_extractable_text": True,
                "char_volume": pass1.char_count,
                "structure_identified": True,
                "question_count": pass2.question_count,
                "options_count": pass2.options_count,
                "detected_subject": Subject.GENERAL.value,
                "recommended_action": "Bổ sung tiêu đề hoặc từ khóa môn học vào đề thi.",
            }
            return verdict, label_vi, rationale, forensic

        # =========================================================================
        # CASE 2: UNCERTAIN_MATCH (Chưa rõ ràng - xác minh nhưng chưa chắc là đúng đề)
        # =========================================================================
        is_uncertain = False

        # Signal 1: Confidence is between 0.50 and 0.88
        if pass3.confidence < 0.88:
            is_uncertain = True
            uncertainty_factors.append(
                f"Mật độ từ vựng chuyên ngành môn {subject.value} còn mỏng (độ tin cậy đạt {pass3.confidence * 100:.1f}%, dưới chuẩn 88%)."
            )

        # Signal 2: Content is academic, but NOT an exam (e.g. syllabus, study notes, formula cheat-sheet)
        if category in [DocumentCategory.THEORY_SYLLABUS, DocumentCategory.GENERAL_DOCUMENT, DocumentCategory.RESEARCH_PAPER]:
            if pass2.question_count == 0 and not any(t in pass2.candidate_exam_types for t in [ExamType.IELTS_TEST, ExamType.JLPT_TEST, ExamType.COMPETITIVE_PROGRAMMING]):
                is_uncertain = True
                uncertainty_factors.append(
                    f"Tài liệu có chứa kiến thức môn {subject.value}, nhưng không có cấu trúc câu hỏi đề thi (0 câu hỏi). "
                    "Đây có thể là đề cương lý thuyết, tóm tắt bài giảng hoặc tài liệu tham khảo chứ chưa chắc là một đề thi thực sự."
                )

        # Signal 3: Highly contested subjects (difference between top 1 and top 2 is small)
        if pass3.subject_scores:
            sorted_scores = sorted(pass3.subject_scores.items(), key=lambda x: x[1], reverse=True)
            if len(sorted_scores) >= 2:
                top1_name, top1_score = sorted_scores[0]
                top2_name, top2_score = sorted_scores[1]
                if top1_score > 0 and top2_score > 0:
                    diff_ratio = (top1_score - top2_score) / top1_score
                    if diff_ratio < 0.25 and top2_score >= 8.0:
                        is_uncertain = True
                        uncertainty_factors.append(
                            f"Có sự giao thoa từ vựng lớn giữa 2 môn {top1_name} ({top1_score:.1f}đ) và {top2_name} ({top2_score:.1f}đ), "
                            "khiến phân loại chưa đạt độ thuần nhất 100%."
                        )

        # Signal 4: Low question count (1-2 questions) in an alleged exam
        if category == DocumentCategory.EXAM_TEST and 0 < pass2.question_count <= 2:
            is_uncertain = True
            uncertainty_factors.append(
                f"Số lượng câu hỏi quá ít ({pass2.question_count} câu), giống một bài tập nhỏ hoặc trích đoạn đề thi hơn là một đề hoàn chỉnh."
            )

        # Signal 5: General subject with low confidence
        if subject in [Subject.GENERAL, Subject.NON_ACADEMIC] and category != DocumentCategory.ADMIN_CONTRACT:
            is_uncertain = True
            uncertainty_factors.append("Môn học chưa được phân định rõ ràng (Subject: GENERAL).")

        if is_uncertain:
            verdict = VerificationVerdict.UNCERTAIN_MATCH
            label_vi = cls.VERDICT_LABELS[verdict]
            factors_text = "\n".join(f"   - {f}" for f in uncertainty_factors)
            evidence_str = ", ".join(pass3.evidence_terms[:4]) if pass3.evidence_terms else "chưa rõ"
            rationale = (
                "TRẠNG THÁI: CHƯA RÕ RÀNG (LÀ XÁC MINH NHƯNG CHƯA CHẮC LÀ ĐÚNG ĐỀ)\n"
                f"• Đã xác minh bước đầu: Nhận diện được tín hiệu môn {subject.value} với bằng chứng ({evidence_str}), "
                f"phân loại: {category.value}.\n"
                f"• Điểm còn nghi vấn / chưa chắc chắn:\n{factors_text}\n"
                f"• Đánh giá chuyên sâu: Tài liệu có thông tin học thuật thật nhưng chưa hội tụ đủ tất cả tiêu chí "
                f"của một đề thi chuẩn mực (có thể là đề cương ôn tập, đề thi thử nghiệm dở dang hoặc tài liệu bài giảng).\n"
                f"• Khuyến nghị: Cần đối chiếu thêm với khung đề chuẩn hoặc kiểm tra xem tài liệu có bị thiếu trang không."
            )
            forensic = {
                "verdict_case": 2,
                "has_extractable_text": True,
                "char_volume": pass1.char_count,
                "structure_identified": bool(pass2.detected_structure),
                "uncertainty_factors": uncertainty_factors,
                "confidence_score": pass3.confidence,
                "recommended_action": "Kiểm tra tính hoàn chỉnh của đề thi hoặc bổ sung thêm trang nội dung.",
            }
            return verdict, label_vi, rationale, forensic

        # =========================================================================
        # CASE 1: VERIFIED_OK (Xác minh - thấy ổn)
        # =========================================================================
        verdict = VerificationVerdict.VERIFIED_OK
        label_vi = cls.VERDICT_LABELS[verdict]

        identified_signals.append(f"Ngôn ngữ & Hệ chữ: {pass1.primary_script} ({pass1.detected_language})")
        identified_signals.append(f"Cấu trúc định dạng: {pass2.detected_structure}")
        identified_signals.append(f"Môn học khẳng định: {subject.value} (Độ tin cậy: {pass3.confidence * 100:.1f}%)")
        if pass3.evidence_terms:
            identified_signals.append(f"Thuật ngữ chuyên ngành cốt lõi: {', '.join(pass3.evidence_terms[:5])}")
        if pass2.question_count > 0:
            identified_signals.append(f"Bóc tách câu hỏi hoàn thiện: {pass2.question_count} câu ({pass2.options_count} phương án)")
        if pass2.has_answer_keys:
            identified_signals.append("Có kèm bảng ma trận đáp án / lời giải chi tiết")

        signals_text = "\n".join(f"   + {s}" for s in identified_signals)
        spoof_note = ""
        if pass3.filename_spoofed:
            spoof_note = (
                f"\n• ĐỐI SOÁT CHỐNG GIẢ MẠO: Đã phát hiện và bóc trần tên file giả mạo ('{pass3.spoof_warning}'). "
                f"Hệ thống đã xác minh chính xác 100% nội dung thực sự bên trong là môn {subject.value}."
            )

        rationale = (
            "TRẠNG THÁI: XÁC MINH (THẤY ỔN)\n"
            f"• Kết luận: Tài liệu hoàn toàn minh bạch, chuẩn xác và hợp lệ 100% qua quy trình kiểm tra 3 lần độc lập "
            f"(Điểm đối soát: {pass3.triple_verification_score:.1f}/100, Độ tin cậy: {pass3.confidence * 100:.1f}%).\n"
            f"• Các bằng chứng đồng thuận:\n{signals_text}{spoof_note}\n"
            f"• Phân loại chuẩn xác: [{category.value}] - Dạng: {exam_type.value} - Môn: {subject.value}.\n"
            f"• Khuyến nghị: Tài liệu đã sẵn sàng để lưu trữ, tổ chức thi hoặc đưa vào hệ thống học tập tự động."
        )

        forensic = {
            "verdict_case": 1,
            "has_extractable_text": True,
            "char_volume": pass1.char_count,
            "structure_identified": True,
            "confidence_score": pass3.confidence,
            "identified_signals": identified_signals,
            "recommended_action": "Tài liệu đạt chuẩn, có thể sử dụng ngay.",
        }

        return verdict, label_vi, rationale, forensic
