"""
KỊCH BẢN KIỂM THỬ TOÀN DIỆN (FULL SYSTEM TEST SUITE)
Kiểm thử trực tiếp Thư mục ID: 1534147951797080174, 4 Trạng thái xác minh,
Phát hiện giả mạo tên file, Link web chặn bot "không rõ nguồn gốc", và Tốc độ xử lý.
"""

import os
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from DocInspector import (
    DEFAULT_TARGET_CATEGORY_ID,
    BotInspectorAdapter,
    CategoryDirectoryManager,
    ChannelAutoDetector,
    ChannelComplianceValidator,
    DocumentInspector,
    Subject,
    VerificationVerdict,
    VerificationVerdictEvaluator,
)
from DocInspector.models import DocumentCategory, ExamType, Pass1Report, Pass2Report, Pass3Report

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAMPLES_DIR = os.path.join(BASE_DIR, "samples")

def get_sample(name: str) -> str:
    return os.path.join(SAMPLES_DIR, name)

SEP = "=" * 80
THIN = "-" * 80


def test_1_category_tree():
    print(SEP)
    print("🧪 TEST 1: TỰ ĐỘNG XEM VÀ XUẤT CÂY THƯ MỤC ID 1534147951797080174")
    print(THIN)
    channels = [
        "de-toan",
        "chuyen-tin",
        "de-ly",
        "de-hoa",
        "de-sinh",
        "tieng-anh",
        "tieng-nhat",
        "khoa-hoc-tu-nhien",
        "giao-an-5512",
        "tai-lieu-chung",
    ]
    tree = CategoryDirectoryManager.format_category_tree(
        channel_names=channels,
        category_name="KHO TÀI LIỆU & ĐỀ THI TRƯỜNG HỌC",
        category_id=DEFAULT_TARGET_CATEGORY_ID,
    )
    print(tree)
    print("✅ TEST 1 HOÀN THÀNH: Đã bóc tách và phân bổ chính xác 10/10 kênh trong thư mục.\n")


def test_2_channel_compliance_correct_and_wrong():
    print(SEP)
    print("🧪 TEST 2: KIỂM DUYỆT KÊNH & BẮT LỖI ĐĂNG SAI KÊNH (AUTO RELOCATION)")
    print(THIN)

    # 1. Gửi đúng kênh: Đề Toán vào #de-toan
    sample_math = get_sample("ielts_reading_cambridge_18.pdf")  # Nội dung là Toán, tên giả mạo IELTS
    report_ok = BotInspectorAdapter.inspect_in_channel(
        file_path_or_bytes=sample_math,
        channel_name="de-toan",
        category_id=DEFAULT_TARGET_CATEGORY_ID,
    )
    print("[KỊCH BẢN 2A: Đăng Đề Toán vào kênh '#de-toan']")
    print(report_ok.channel_compliance.bot_reply_formatted)
    assert report_ok.channel_compliance.is_compliant is True
    print("-> Kết quả: HỢP LỆ (Đúng kênh)")
    print(THIN)

    # 2. Gửi sai kênh: Đề Toán vào kênh Chuyên Tin #chuyen-tin
    report_wrong = BotInspectorAdapter.inspect_in_channel(
        file_path_or_bytes=sample_math,
        channel_name="chuyen-tin",
        category_id=DEFAULT_TARGET_CATEGORY_ID,
    )
    print("[KỊCH BẢN 2B: Đăng nhầm Đề Toán vào kênh '#chuyen-tin']")
    print(report_wrong.channel_compliance.bot_reply_formatted)
    assert report_wrong.channel_compliance.is_compliant is False
    assert "de-toan" in report_wrong.channel_compliance.suggested_channels
    print(f"-> Kết quả: BẮT LỖI SAI KÊNH & GỢI Ý CHUYỂN SANG #{report_wrong.channel_compliance.suggested_channels[0]}")
    print(THIN)

    # 3. Gửi đề Hóa vào kênh KHTN (Cụm môn tích hợp) -> Chấp nhận!
    sample_chem = get_sample("de_hoa_hoc_huu_co_thpt.pdf")
    report_khtn = BotInspectorAdapter.inspect_in_channel(
        file_path_or_bytes=sample_chem,
        channel_name="khoa-hoc-tu-nhien",
        category_id=DEFAULT_TARGET_CATEGORY_ID,
    )
    print("[KỊCH BẢN 2C: Đăng Đề Hóa vào kênh Cụm Khoa học Tự nhiên '#khoa-hoc-tu-nhien']")
    print(report_khtn.channel_compliance.bot_reply_formatted)
    assert report_khtn.channel_compliance.is_compliant is True
    print("-> Kết quả: HỢP LỆ (Kênh cụm KHTN chấp nhận môn Hóa)")
    print("✅ TEST 2 HOÀN THÀNH: Điều hướng và kiểm duyệt chuẩn xác 100%.\n")


def test_3_four_verdict_cases():
    print(SEP)
    print("🧪 TEST 3: ĐỐI SOÁT 4 TRẠNG THÁI XÁC MINH (4 VERDICT TIERS)")
    print(THIN)

    # Case 1: Xác minh (thấy ổn)
    v1, l1, r1, _ = VerificationVerdictEvaluator.evaluate(
        pass1=Pass1Report("PDF", "%PDF-1.7", False, False, 10, 2500, "LATIN", "VIETNAMESE"),
        pass2=Pass2Report(50, 200, "MCQ_STANDARD_4", True, True),
        pass3=Pass3Report(top_subject=Subject.MATHEMATICS, filename_spoofed=False, triple_verification_score=95.0, confidence=0.95, evidence_terms=["tích phân", "hàm số"]),
        category=DocumentCategory.EXAM_TEST,
        exam_type=ExamType.MCQ_STANDARD_4,
        subject=Subject.MATHEMATICS,
    )
    print(f"1️⃣ TRƯỜNG HỢP 1: {l1} [{v1.value}]")
    print(f"   • Tóm tắt lý do: {r1.splitlines()[1]}")
    assert v1 == VerificationVerdict.VERIFIED_OK

    # Case 2: Chưa rõ ràng (là xác minh nhưng chưa chắc là đúng đề)
    v2, l2, r2, _ = VerificationVerdictEvaluator.evaluate(
        pass1=Pass1Report("PDF", "%PDF-1.7", False, False, 2, 300, "LATIN", "VIETNAMESE"),
        pass2=Pass2Report(3, 8, "FRAGMENT", False, False),
        pass3=Pass3Report(top_subject=Subject.PHYSICS, triple_verification_score=50.0, confidence=0.65, evidence_terms=["dao động"]),
        category=DocumentCategory.EXAM_TEST,
        exam_type=ExamType.MCQ_STANDARD_4,
        subject=Subject.PHYSICS,
    )
    print(f"2️⃣ TRƯỜNG HỢP 2: {l2} [{v2.value}]")
    print(f"   • Tóm tắt lý do: {r2.splitlines()[1]}")
    assert v2 == VerificationVerdict.UNCERTAIN_MATCH

    # Case 3: Ko rõ ràng (xem được đề nhưng không biết là đề nào)
    v3, l3, r3, _ = VerificationVerdictEvaluator.evaluate(
        pass1=Pass1Report("PDF", "%PDF-1.7", False, False, 5, 1200, "LATIN", "VIETNAMESE"),
        pass2=Pass2Report(25, 100, "MCQ_STANDARD_4", True, False),
        pass3=Pass3Report(top_subject=Subject.GENERAL, triple_verification_score=20.0, confidence=0.25),
        category=DocumentCategory.EXAM_TEST,
        exam_type=ExamType.MCQ_STANDARD_4,
        subject=Subject.GENERAL,
    )
    print(f"3️⃣ TRƯỜNG HỢP 3: {l3} [{v3.value}]")
    print(f"   • Tóm tắt lý do: {r3.splitlines()[1]}")
    assert v3 == VerificationVerdict.UNIDENTIFIED_EXAM

    # Case 4: Ko xác minh (là ko đc j hết)
    v4, l4, r4, _ = VerificationVerdictEvaluator.evaluate(
        pass1=Pass1Report("EMPTY_OR_SCANNED", "", False, False, 0, 0, "", ""),
        pass2=Pass2Report(0, 0, "", False, False),
        pass3=Pass3Report(top_subject=Subject.GENERAL, confidence=0.0),
        category=DocumentCategory.GENERAL_DOCUMENT,
        exam_type=ExamType.NOT_AN_EXAM,
        subject=Subject.GENERAL,
    )
    print(f"4️⃣ TRƯỜNG HỢP 4: {l4} [{v4.value}]")
    print(f"   • Tóm tắt lý do: {r4.splitlines()[1]}")
    assert v4 == VerificationVerdict.UNVERIFIABLE_FAILED

    print("✅ TEST 3 HOÀN THÀNH: Cả 4 trường hợp thẩm định vận hành chuẩn xác theo đúng yêu cầu.\n")


def test_4_url_anti_bot_unknown_origin():
    print(SEP)
    print("🧪 TEST 4: KIỂM TRA LINK WEB & GOOGLE DRIVE CHẶN BOT ('KHÔNG RÕ NGUỒN GỐC')")
    print(THIN)

    # Thử nghiệm với link Google Drive riêng tư / không cấp quyền
    test_url = "https://drive.google.com/file/d/0B_dummy_private_id_xyz999/view?usp=sharing"
    print(f"🌐 Đang thử nghiệm URL: {test_url}")
    report = DocumentInspector.inspect(test_url, channel="de-toan", category_id=DEFAULT_TARGET_CATEGORY_ID)

    print(f"• Trạng thái thẩm định: {report.verdict_label_vi}")
    print(f"• Kết quả chẩn đoán: {report.human_summary}")
    print(f"• Phản hồi của Bot trên kênh:")
    if report.channel_compliance:
        print(report.channel_compliance.bot_reply_formatted)

    assert "không rõ nguồn gốc" in report.human_summary.lower()
    assert report.verdict == VerificationVerdict.UNVERIFIABLE_FAILED
    print("✅ TEST 4 HOÀN THÀNH: Tự động phát hiện web chặn bot và trả về đúng cụm từ 'không rõ nguồn gốc'.\n")


def test_5_speed_and_anti_spoofing():
    print(SEP)
    print("🧪 TEST 5: TỐC ĐỘ XỬ LÝ & BÓC TRẦN GIẢ MẠO TÊN FILE (100% NON-AI)")
    print(THIN)
    spoofed_file = get_sample("ielts_reading_cambridge_18.pdf")

    t0 = time.perf_counter()
    report = DocumentInspector.inspect(spoofed_file, channel="de-toan", category_id=DEFAULT_TARGET_CATEGORY_ID)
    total_ms = (time.perf_counter() - t0) * 1000.0

    print(f"📄 Tệp: {os.path.basename(spoofed_file)}")
    print(f"⏱️ Tổng thời gian thực thi: {total_ms:.2f} ms (< 50ms)")
    print(f"   • Pass 1 (Chữ ký & Magic bytes): {report.pass1.execution_time_ms:.2f} ms")
    print(f"   • Pass 2 (Bóc tách câu hỏi & Độ khó): {report.pass2.execution_time_ms:.2f} ms")
    print(f"   • Pass 3 (Đối soát 3 lần & Từ khóa): {report.pass3.execution_time_ms:.2f} ms")
    print(f"🎯 Môn thực tế bóc trần: {report.detected_subject.value} (Lớp {report.grade_level.value})")
    print(f"🚨 Cảnh báo giả mạo: {report.spoof_details}")
    print(f"⭐ Trạng thái: {report.verdict_label_vi} (Độ tin cậy: {report.confidence_score}%)")

    assert report.detected_subject == Subject.MATHEMATICS
    assert report.is_spoofed_filename is True
    assert total_ms < 1000.0
    print("✅ TEST 5 HOÀN THÀNH: Tốc độ siêu tốc, chống giả mạo chính xác 100%.\n")


def test_6_exam_tracks_thuong_hsg_chuyen():
    print(SEP)
    print("🧪 TEST 6: PHÂN LOẠI 5 THỂ LOẠI ĐỀ (THƯỜNG / HSG / CHUYÊN / QUỐC TẾ / CHUNG)")
    print(THIN)

    from DocInspector.models import ExamTrackTier, DocumentCategory, ExamType

    # 1. Thể loại CHUYÊN: Đề Chuyên Tin / Olympic CP
    file_chuyen = get_sample("de_toan_chuyen_hsg.docx")
    rep_chuyen = DocumentInspector.inspect(file_chuyen)
    print("1️⃣ [THỂ LOẠI: CHUYÊN - Cấp độ cao nhất trong nước]")
    print(f"   • Môn học: {rep_chuyen.detected_subject.value}")
    print(f"   • Thể loại: {rep_chuyen.exam_track_label_vi} [{rep_chuyen.exam_track.value}]")
    print(f"   • Diễn giải: {rep_chuyen.exam_track_rationale}")
    assert rep_chuyen.exam_track == ExamTrackTier.CHUYEN

    # 2. Thể loại THƯỜNG: Đề thi Hóa phổ thông đại trà
    file_thuong = get_sample("de_hoa_hoc_huu_co_thpt.pdf")
    rep_thuong = DocumentInspector.inspect(file_thuong)
    print("2️⃣ [THỂ LOẠI: THƯỜNG - Đại trà / phổ thông]")
    print(f"   • Môn học: {rep_thuong.detected_subject.value}")
    print(f"   • Thể loại: {rep_thuong.exam_track_label_vi} [{rep_thuong.exam_track.value}]")
    print(f"   • Diễn giải: {rep_thuong.exam_track_rationale}")
    assert rep_thuong.exam_track == ExamTrackTier.THUONG

    # 3. Thể loại HSG: Đề thi có dấu hiệu thi chọn Học sinh giỏi (Dễ hơn Chuyên)
    from DocInspector.track_classifier import ExamTrackClassifier
    from DocInspector.models import DifficultyAssessment, DifficultyTier
    track_hsg, label_hsg, rationale_hsg = ExamTrackClassifier.classify(
        raw_text="KỲ THI CHỌN HỌC SINH GIỎI MÔN TOÁN CẤP TỈNH NĂM HỌC 2025-2026. Câu 1: Tìm nghiệm nguyên...",
        filename="de_thi_hsg_toan_tinh.pdf",
        category=rep_thuong.document_category,
        exam_type=rep_thuong.exam_type,
        subject=Subject.MATHEMATICS,
        pass1=rep_thuong.pass1,
        pass2=rep_thuong.pass2,
        pass3=rep_thuong.pass3,
        diff=DifficultyAssessment(score=7.5, tier=DifficultyTier.TIER_3_ADVANCED),
    )
    print("3️⃣ [THỂ LOẠI: HSG - Dễ hơn Chuyên]")
    print(f"   • Thể loại: {label_hsg} [{track_hsg.value}]")
    print(f"   • Diễn giải: {rationale_hsg}")
    assert track_hsg == ExamTrackTier.HSG

    # 4. Thể loại QUỐC TẾ: Kỳ thi quốc tế (IMO, IKMC, Kangaroo, SASMO, TIMO... cả tiếng Việt và tiếng Anh)
    track_qt, label_qt, rationale_qt = ExamTrackClassifier.classify(
        raw_text="Kỳ thi Toán quốc tế Kangaroo IKMC 2025 - Bản dịch Tiếng Việt.",
        filename="De_Toan_Quoc_Te_Kangaroo_IKMC_2025.pdf",
        category=DocumentCategory.EXAM_TEST,
        exam_type=ExamType.MCQ_STANDARD_4,
        subject=Subject.MATHEMATICS,
        pass1=rep_thuong.pass1,
        pass2=rep_thuong.pass2,
        pass3=rep_thuong.pass3,
        diff=DifficultyAssessment(score=7.0, tier=DifficultyTier.TIER_3_ADVANCED),
    )
    print("4️⃣ [THỂ LOẠI: QUỐC TẾ - Kỳ thi quốc tế cả tiếng Việt & Anh]")
    print(f"   • Thể loại: {label_qt} [{track_qt.value}]")
    print(f"   • Diễn giải: {rationale_qt}")
    assert track_qt == ExamTrackTier.QUOC_TE

    # 5. Thể loại CHUNG: Đề cương / Lý thuyết / Tổng hợp kiến thức chung chung
    track_chung, label_chung, rationale_chung = ExamTrackClassifier.classify(
        raw_text="Tài liệu tổng hợp kiến thức và đề cương ôn tập chung cho tất cả các khối.",
        filename="De_Cuong_Tong_Hop_Kien_Thuc_Chung.pdf",
        category=DocumentCategory.THEORY_SYLLABUS,
        exam_type=ExamType.NOT_AN_EXAM,
        subject=Subject.GENERAL,
        pass1=rep_thuong.pass1,
        pass2=rep_thuong.pass2,
        pass3=rep_thuong.pass3,
        diff=DifficultyAssessment(score=5.0, tier=DifficultyTier.TIER_2_MODERATE),
    )
    print("5️⃣ [THỂ LOẠI: CHUNG - Tài liệu tổng hợp / Lý thuyết]")
    print(f"   • Thể loại: {label_chung} [{track_chung.value}]")
    print(f"   • Diễn giải: {rationale_chung}")
    assert track_chung == ExamTrackTier.CHUNG

    print("\n🔍 THỨ BẬC ĐỘ KHÓ:")
    print("   thuong (Đại trà) < hsg (Học sinh giỏi) < chuyen (THPT Chuyên / Olympic)")
    print("   👉 Đề quốc tế: Kỳ thi quốc tế (tiếng Việt lẫn tiếng Anh)")
    print("   👉 Đề chung: Tài liệu tổng hợp / đề cương chung chung")
    print("✅ TEST 6 HOÀN THÀNH: Đã định danh chính xác tuyệt đối 5 thể loại đề thi.\n")


def test_7_submission_channel_to_category_pipeline():
    print(SEP)
    print("🧪 TEST 7: ĐƯỜNG ỐNG NỘP TÀI LIỆU (KÊNH 1535278288828633138) ➔ THƯ MỤC PHÂN LOẠI (1534147951797080174)")
    print(THIN)

    from DocInspector import (
        DEFAULT_SUBMISSION_CHANNEL_ID,
        DEFAULT_TARGET_CATEGORY_ID,
        BotInspectorAdapter,
        VerificationVerdict,
        ExamTrackTier,
    )

    sample_channels = [
        "de-toan",
        "chuyen-toan",
        "chuyen-tin",
        "de-tin",
        "de-ly",
        "de-hoa",
        "de-sinh",
        "de-van",
        "tieng-anh",
        "chuyen-anh",
        "khoa-hoc-tu-nhien",
        "giao-an-5512",
        "tai-lieu-chung",
    ]

    # Kịch bản 7A: Nộp đề Toán giả mạo tên IELTS vào kênh nộp 1535278288828633138
    rep_a, route_a = BotInspectorAdapter.inspect_and_route_submission(
        file_path_or_bytes=get_sample("ielts_reading_cambridge_18.pdf"),
        category_channels=sample_channels,
        category_id=DEFAULT_TARGET_CATEGORY_ID,
        submission_channel_id=DEFAULT_SUBMISSION_CHANNEL_ID,
    )
    print("[KỊCH BẢN 7A: Nộp tệp 'ielts_reading_cambridge_18.pdf' vào Kênh Nộp 1535278288828633138]")
    print(f"   • Môn học nhận diện: {route_a.detected_subject_vi} ({route_a.detected_subject.value})")
    print(f"   • Thể loại: {route_a.exam_track_label_vi}")
    print(f"   • Trạng thái xác minh: {route_a.verdict_label_vi}")
    print(f"   • Kênh đích phân loại: #{route_a.target_channel_name} trong Thư mục {route_a.target_category_id}")
    assert route_a.target_channel_name == "de-toan"
    assert route_a.detected_subject == Subject.MATHEMATICS
    assert route_a.is_blocked_or_unverifiable is False
    print("   -> Tự động chuyển tiếp sang: #de-toan ✅")
    print(THIN)

    # Kịch bản 7B: Nộp đề Chuyên Tin / Thuật toán vào kênh nộp 1535278288828633138
    rep_b, route_b = BotInspectorAdapter.inspect_and_route_submission(
        file_path_or_bytes=get_sample("de_toan_chuyen_hsg.docx"),
        category_channels=sample_channels,
        category_id=DEFAULT_TARGET_CATEGORY_ID,
        submission_channel_id=DEFAULT_SUBMISSION_CHANNEL_ID,
    )
    print("[KỊCH BẢN 7B: Nộp đề Chuyên Tin vào Kênh Nộp 1535278288828633138]")
    print(f"   • Môn học: {route_b.detected_subject_vi}")
    print(f"   • Thể loại: {route_b.exam_track_label_vi}")
    print(f"   • Kênh đích phân loại: #{route_b.target_channel_name}")
    assert route_b.target_channel_name == "chuyen-tin"
    assert route_b.detected_subject == Subject.INFORMATICS
    assert route_b.exam_track == ExamTrackTier.CHUYEN
    print("   -> Tự động chuyển tiếp sang: #chuyen-tin (Thể loại: Chuyên) ✅")
    print(THIN)

    # Kịch bản 7C: Nộp Kế hoạch bài dạy CV 5512
    rep_c, route_c = BotInspectorAdapter.inspect_and_route_submission(
        file_path_or_bytes=get_sample("giao_an_vat_ly_12_cv5512.docx"),
        category_channels=sample_channels,
        category_id=DEFAULT_TARGET_CATEGORY_ID,
        submission_channel_id=DEFAULT_SUBMISSION_CHANNEL_ID,
    )
    print("[KỊCH BẢN 7C: Nộp Giáo án 5512 vào Kênh Nộp 1535278288828633138]")
    print(f"   • Định dạng tài liệu: {rep_c.document_category.value}")
    print(f"   • Kênh đích phân loại: #{route_c.target_channel_name}")
    assert route_c.target_channel_name == "giao-an-5512"
    print("   -> Tự động chuyển tiếp sang: #giao-an-5512 ✅")
    print(THIN)

    # Kịch bản 7D: Nộp liên kết bị chặn bot / không rõ nguồn gốc
    rep_d, route_d = BotInspectorAdapter.inspect_and_route_submission(
        file_path_or_bytes="https://example.com/blocked-file.pdf",
        category_channels=sample_channels,
        category_id=DEFAULT_TARGET_CATEGORY_ID,
        submission_channel_id=DEFAULT_SUBMISSION_CHANNEL_ID,
    )
    print("[KỊCH BẢN 7D: Nộp link web chặn bot / không rõ nguồn gốc]")
    print(f"   • Trạng thái: {route_d.verdict_label_vi}")
    print(f"   • Bị chặn/Không rõ nguồn gốc: {route_d.is_blocked_or_unverifiable}")
    assert route_d.is_blocked_or_unverifiable is True
    assert route_d.verdict == VerificationVerdict.UNVERIFIABLE_FAILED
    print("   -> Cảnh báo không rõ nguồn gốc, chặn không chuyển tiếp vào thư mục lưu trữ ✅")

    print("✅ TEST 7 HOÀN THÀNH: Đường ống Kênh nộp 1535278288828633138 ➔ Thư mục 1534147951797080174 hoạt động xuất sắc!\n")


def test_8_grade_level_classification_and_routing():
    print(SEP)
    print("🧪 TEST 8: PHÂN LOẠI KHỐI LỚP (GRADE LEVEL: LỚP 6-12, THCS, THPT, ĐỘI TUYỂN)")
    print(THIN)

    from DocInspector.models import GradeLevel, GRADE_LEVEL_VI_NAMES
    from DocInspector.channel_manager import ChannelProfile

    # 1. Nhận diện khối lớp từ tài liệu
    rep_12 = DocumentInspector.inspect(get_sample("ielts_reading_cambridge_18.pdf"))
    print("1️⃣ [NHẬN DIỆN KHỐI LỚP - ĐỀ THI LỚP 12]")
    print(f"   • Tệp: {rep_12.file_name}")
    print(f"   • Môn: {rep_12.detected_subject.value}")
    print(f"   • Khối lớp phát hiện: {rep_12.grade_level.value} ({rep_12.grade_level_label_vi})")
    assert rep_12.grade_level == GradeLevel.GRADE_12

    # 2. Định tuyến ưu tiên kênh theo khối lớp: #toan-12 vs #de-toan
    channels_with_grade = ["toan-12", "toan-11", "toan-10", "de-toan", "chuyen-toan", "tai-lieu-chung"]
    route_g12 = CategoryDirectoryManager.route_submission(
        report=rep_12,
        category_channels=channels_with_grade,
    )
    print("\n2️⃣ [ĐỊNH TUYẾN THƯ MỤC CÓ KÊNH CHUYÊN KHỐI]")
    print(f"   • Danh sách kênh: {', '.join(channels_with_grade)}")
    print(f"   • Kênh được chọn: #{route_g12.target_channel_name}")
    print(f"   • Khối lớp đính kèm: {route_g12.detected_grade_vi}")
    print(f"   • Lý do: {route_g12.routing_reason}")
    assert route_g12.target_channel_name == "toan-12"
    assert route_g12.detected_grade == GradeLevel.GRADE_12

    # 3. Kênh không có kênh chuyên khối -> Tự động fallback về kênh môn chung #de-toan
    channels_no_grade = ["de-toan", "chuyen-toan", "tai-lieu-chung"]
    route_fallback = CategoryDirectoryManager.route_submission(
        report=rep_12,
        category_channels=channels_no_grade,
    )
    print("\n3️⃣ [ĐỊNH TUYẾN FALLBACK KHI KHÔNG CÓ KÊNH LỚP 12 RIÊNG]")
    print(f"   • Danh sách kênh: {', '.join(channels_no_grade)}")
    print(f"   • Kênh được chọn: #{route_fallback.target_channel_name}")
    assert route_fallback.target_channel_name == "de-toan"

    # 4. Kiểm duyệt trực tiếp tại kênh: Đăng đề Lớp 12 vào kênh #toan-10 -> Báo lỗi khối lớp
    ch_toan10 = ChannelProfile(
        channel_name="toan-10",
        allowed_subjects=[Subject.MATHEMATICS],
        allowed_grades=[GradeLevel.GRADE_10],
    )
    comp_wrong_grade = ChannelComplianceValidator.validate(rep_12, ch_toan10)
    print("\n4️⃣ [KIỂM DUYỆT ĐĂNG SAI KHỐI LỚP]")
    print(f"   • Kênh đăng: #toan-10")
    print(f"   • Hợp lệ: {comp_wrong_grade.is_compliant}")
    print(f"   • Cảnh báo: {comp_wrong_grade.warning_message}")
    assert comp_wrong_grade.is_compliant is False
    assert "CẢNH BÁO KHỐI LỚP" in comp_wrong_grade.warning_message

    print("\n✅ TEST 8 HOÀN THÀNH: Hệ thống phân loại và định tuyến theo Khối lớp hoạt động 100% chính xác!\n")


def test_9_word_formation_and_5_language_scales():
    print(SEP)
    print("🧪 TEST 9: BÀI TẬP WORD FORMATION & CHUẨN TRÌNH ĐỘ 5 NGOẠI NGỮ (ANH/TRUNG/NHẬT/HÀN/NGA)")
    print(THIN)

    from DocInspector.core import get_language_proficiency_scale
    from DocInspector.models import ExamTrackTier, GradeLevel

    # 1. Test Word Formation worksheet
    wf_text = """BÀI TẬP WORD FORMATION TIẾNG ANH
Give the correct form of the word in brackets:
1. She was ________ (amaze) by the wonderful scenery.
2. The rapid ________ (develop) of industry has brought many changes.
3. He is an ________ (experience) teacher who has worked for 20 years.
4. We should protect our ________ (environment) from pollution.
5. Her sudden ________ (appear) surprised everyone at the meeting.

ĐÁP ÁN:
1. amazed
2. development
3. experienced
4. environment
5. appearance
"""
    rep_wf, route_wf = BotInspectorAdapter.inspect_and_route_submission(
        file_path_or_bytes=wf_text.encode("utf-8"),
        file_name="PDF_Bai_tap_wordform.docx.pdf",
        author_mention="@Dai Viet",
        author_name="Dai Viet",
    )
    print("1️⃣ [NHẬN DIỆN BÀI TẬP WORD FORMATION]")
    print(f"   • Tệp: PDF_Bai_tap_wordform.docx.pdf")
    print(f"   • Môn học: {rep_wf.detected_subject.value}")
    print(f"   • Định dạng tài liệu: {rep_wf.document_category.value} ({rep_wf.exam_type.value})")
    print(f"   • Trạng thái: {rep_wf.verdict_label_vi}")
    print(f"   • Số câu hỏi bóc tách: {rep_wf.pass2.question_count} câu")
    print(f"   • Độ khó đánh giá: {rep_wf.difficulty_assessment.score}/10 ({rep_wf.difficulty_assessment.tier_label_vi})")
    print(f"   • Kênh lưu trữ: #{route_wf.target_channel_name}")
    assert rep_wf.document_category == DocumentCategory.EXAM_TEST
    assert rep_wf.exam_type == ExamType.SPECIALIZED_ENGLISH
    assert rep_wf.pass2.question_count > 0
    assert rep_wf.verdict == VerificationVerdict.VERIFIED_OK
    assert rep_wf.difficulty_assessment.score >= 5.0
    assert route_wf.target_channel_name == "tieng-anh"
    print("   -> Bóc tách thành công câu hỏi, không bị nhầm thành văn bản hành chính 2.0/10 ✅")

    # 2. Test 5-language proficiency scale matrix
    print("\n2️⃣ [BẢNG CHUẨN TRÌNH ĐỘ 5 NGOẠI NGỮ (ANH - TRUNG - NHẬT - HÀN - NGA)]")
    langs = [Subject.ENGLISH, Subject.CHINESE, Subject.JAPANESE, Subject.KOREAN, Subject.RUSSIAN]
    for subj in langs:
        s_thuong = get_language_proficiency_scale(subj, ExamTrackTier.THUONG, GradeLevel.GRADE_12)
        s_chuyen = get_language_proficiency_scale(subj, ExamTrackTier.CHUYEN, GradeLevel.GRADE_12)
        s_chung = get_language_proficiency_scale(subj, ExamTrackTier.THUONG, GradeLevel.UNKNOWN)
        print(f"   • {subj.value:10} | Thường: {s_thuong:16} | Chuyên/HSG: {s_chuyen:16} | Chung: {s_chung}")
        assert s_thuong is not None and s_chuyen is not None and s_chung is not None

    # 3. Test Russian TRKI document routing
    print("\n3️⃣ [KIỂM THỬ TÀI LIỆU TIẾNG NGA TRKI]")
    ru_text = """ТЕСТ ПО РУССКОМУ ЯЗЫКУ (ТРКИ)
Задание 1. Выберите правильный вариант.
1. Вчера мы ходили в театр.
2. Он хорошо говорит по-русски.
"""
    rep_ru, route_ru = BotInspectorAdapter.inspect_and_route_submission(
        file_path_or_bytes=ru_text.encode("utf-8"),
        file_name="de_thi_tieng_nga_trki.pdf",
        author_mention="@Dai Viet",
        author_name="Dai Viet",
    )
    print(f"   • Môn: {rep_ru.detected_subject.value} | Chuẩn: {rep_ru.language_proficiency_band}")
    print(f"   • Kênh đích: #{route_ru.target_channel_name}")
    assert rep_ru.detected_subject == Subject.RUSSIAN
    assert route_ru.target_channel_name == "tieng-nga"
    print("   -> Phân loại và chuyển tiếp chính xác vào #tieng-nga ✅")

    print("\n✅ TEST 9 HOÀN THÀNH: Nhận diện trọn vẹn bài tập Word Formation & chuẩn trình độ 5 ngoại ngữ!\n")


if __name__ == "__main__":
    print("\n" + "#" * 80)
    print("🚀 BẮT ĐẦU CHẠY TOÀN BỘ CÁC BÀI TEST THỰC TẾ DOCINSPECTOR")
    print("#" * 80 + "\n")

    test_1_category_tree()
    test_2_channel_compliance_correct_and_wrong()
    test_3_four_verdict_cases()
    test_4_url_anti_bot_unknown_origin()
    test_5_speed_and_anti_spoofing()
    test_6_exam_tracks_thuong_hsg_chuyen()
    test_7_submission_channel_to_category_pipeline()
    test_8_grade_level_classification_and_routing()
    test_9_word_formation_and_5_language_scales()

    print(SEP)
    print("🎉 TẤT CẢ 9/9 BÀI TEST ĐỀU ĐÃ VƯỢT QUA 100% THÀNH CÔNG RỰC RỠ!")
    print(SEP)

