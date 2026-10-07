"""
Professional Reporting and Dossier Exporters for DocInspector.
Generates responsive standalone HTML audit reports, Markdown dossiers, and CSV summaries.
Includes Difficulty Assessment and User Requirement Qualification Audit.
"""

from __future__ import annotations

import csv
import html
import io
from pathlib import Path
from typing import List, Union

from .models import InspectionReport


class DocumentReporter:
    """Generates rich visual and tabular audit reports for DocInspector."""

    @classmethod
    def generate_html_report(cls, report: InspectionReport, output_path: Union[str, Path]) -> Path:
        """
        Creates a standalone, modern, responsive HTML audit report
        with dark/light aesthetics, difficulty metrics, user requirements audit,
        cognitive level charts, and itemized questions.
        """
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)

        spoof_banner = ""
        if report.is_spoofed_filename:
            spoof_banner = f"""
            <div class="spoof-card">
                <div class="spoof-header">🚨 <strong>CẢNH BÁO PHÁT HIỆN TÊN FILE GIẢ MẠO / LỪA ĐẢO</strong></div>
                <div class="spoof-body">{html.escape(report.spoof_details or "")}</div>
            </div>
            """
        # 4-Tier Verification Verdict Banner
        verdict = report.verdict
        verdict_config = {
            "XAC_MINH": {"color": "#10b981", "bg": "rgba(16, 185, 129, 0.12)", "border": "#10b981", "icon": "⭐"},
            "CHUA_RO_RANG": {"color": "#f59e0b", "bg": "rgba(245, 158, 11, 0.12)", "border": "#f59e0b", "icon": "⚠️"},
            "KO_RO_RANG": {"color": "#a855f7", "bg": "rgba(168, 85, 247, 0.12)", "border": "#a855f7", "icon": "❓"},
            "KO_XAC_MINH": {"color": "#ef4444", "bg": "rgba(239, 68, 68, 0.12)", "border": "#ef4444", "icon": "🚫"},
        }.get(verdict.value, {"color": "#6366f1", "bg": "rgba(99, 102, 241, 0.12)", "border": "#6366f1", "icon": "ℹ️"})

        verdict_card = f"""
        <div style="background: {verdict_config['bg']}; border: 2px solid {verdict_config['border']}; border-radius: 8px; padding: 18px 22px; margin-bottom: 24px;">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; margin-bottom: 10px;">
                <div style="font-size: 13px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: {verdict_config['color']};">
                    {verdict_config['icon']} KẾT LUẬN XÁC MINH HỒ SƠ TÀI LIỆU
                </div>
                <div>
                    <span style="background: {verdict_config['color']}; color: #fff; font-weight: 700; font-size: 14px; padding: 6px 14px; border-radius: 20px;">
                        {html.escape(report.verdict_label_vi)}
                    </span>
                </div>
            </div>
            <div style="font-size: 14px; line-height: 1.6; color: var(--text-color); white-space: pre-line;">
                {html.escape(report.verdict_rationale)}
            </div>
        </div>
        """

        # Difficulty & Workload Assessment Block
        diff = report.difficulty_assessment
        tier_color = {
            "TIER_1_BASIC": "#10b981",
            "TIER_2_MODERATE": "#3b82f6",
            "TIER_3_ADVANCED": "#f59e0b",
            "TIER_4_OLYMPIAD": "#ef4444",
        }.get(diff.tier.value, "#6366f1")

        diff_card = f"""
        <div class="card" style="margin-bottom: 24px; border-left: 5px solid {tier_color};">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 12px; margin-bottom: 12px;">
                <div>
                    <div class="card-label">ĐÁNH GIÁ ĐỘ KHÓ & TẢI TRỌNG LÀM BÀI</div>
                    <div style="font-size: 22px; font-weight: 700; color: #fff;">
                        <span style="color: {tier_color};">{diff.score}/10</span> &nbsp;|&nbsp; 
                        <span style="font-size: 16px; color: {tier_color};">{html.escape(diff.tier_label_vi)}</span>
                    </div>
                </div>
                <div style="text-align: right;">
                    <span class="badge" style="background: {tier_color}; color: #fff; font-size: 13px; padding: 6px 12px;">
                        {diff.tier.value}
                    </span>
                </div>
            </div>
            <div class="diff-grid">
                <div class="diff-item">
                    <span class="diff-k">Thời gian làm bài gợi ý:</span>
                    <strong class="diff-v">{diff.recommended_duration_minutes} phút</strong>
                </div>
                <div class="diff-item">
                    <span class="diff-k">Tốc độ trung bình:</span>
                    <strong class="diff-v">~{diff.pace_seconds_per_question:.0f} giây / câu</strong>
                </div>
                <div class="diff-item">
                    <span class="diff-k">Đối tượng học sinh:</span>
                    <strong class="diff-v">{html.escape(diff.target_audience)}</strong>
                </div>
                <div class="diff-item">
                    <span class="diff-k">Đặc trưng ma trận đề:</span>
                    <strong class="diff-v">{html.escape(diff.cognitive_balance)}</strong>
                </div>
            </div>
            {f'<div style="font-size: 13px; color: var(--text-muted); margin-top: 10px; font-style: italic;">{html.escape(diff.rationale)}</div>' if diff.rationale else ''}
        </div>
        """

        # Channel Compliance Card
        channel_html = ""
        if report.channel_compliance:
            cc = report.channel_compliance
            c_color = "#10b981" if cc.is_compliant else "#ef4444"
            c_badge = "✅ ĐÚNG KÊNH" if cc.is_compliant else "🚨 SAI KÊNH"
            c_body = html.escape(cc.bot_reply_formatted).replace("\n", "<br>")
            channel_html = f"""
            <div class="card" style="margin-bottom: 24px; border-left: 5px solid {c_color};">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                    <div class="card-label">KIỂM DUYỆT ĐỊNH TUYẾN KÊNH (#{html.escape(cc.channel_name)})</div>
                    <span class="badge" style="background: {c_color}; color: #fff; font-size: 13px;">{c_badge}</span>
                </div>
                <div style="font-size: 13.5px; line-height: 1.6;">
                    {c_body}
                </div>
            </div>
            """

        # User Requirement Audit Block (if evaluated)
        req_audit_html = ""
        if report.requirement_audit:
            audit = report.requirement_audit
            audit_badge_color = "#10b981" if audit.is_eligible else "#ef4444"
            audit_badge_text = "✅ " + audit.status_label_vi if audit.is_eligible else "❌ " + audit.status_label_vi

            checks_rows = []
            for c in audit.checks:
                status_icon = "<span style='color: #10b981; font-weight: bold;'>✔ PASS</span>" if c.passed else f"<span style='color: #ef4444; font-weight: bold;'>✘ FAIL ({c.severity})</span>"
                row = f"""
                <tr>
                    <td><strong>{html.escape(c.rule_name)}</strong><br><small style='color: var(--text-muted);'>{html.escape(c.description)}</small></td>
                    <td>{html.escape(str(c.expected))}</td>
                    <td>{html.escape(str(c.actual))}</td>
                    <td style="text-align: center;">{status_icon}</td>
                </tr>
                """
                checks_rows.append(row)

            recs_html = ""
            if audit.recommendations:
                recs_list = "".join(f"<li>{html.escape(r)}</li>" for r in audit.recommendations)
                recs_html = f"""
                <div style="margin-top: 14px; background: rgba(239, 68, 68, 0.08); border-left: 3px solid #ef4444; padding: 10px 16px; border-radius: 4px;">
                    <strong style="color: #fca5a5; font-size: 13px;">Khuyến nghị điều chỉnh:</strong>
                    <ul style="margin-left: 18px; margin-top: 4px; font-size: 13px; color: #fecaca;">
                        {recs_list}
                    </ul>
                </div>
                """

            req_audit_html = f"""
            <div class="card" style="margin-bottom: 24px; border: 2px solid {audit_badge_color};">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                    <div>
                        <div class="card-label">KẾT QUẢ THẨM ĐỊNH YÊU CẦU NGƯỜI DÙNG</div>
                        <div style="font-size: 16px; font-weight: 700;">Hồ sơ áp dụng: <span style="color: #a5b4fc;">{html.escape(audit.profile_applied)}</span></div>
                    </div>
                    <div>
                        <span class="badge" style="background: {audit_badge_color}; color: #fff; font-size: 14px; padding: 6px 14px;">
                            {audit_badge_text}
                        </span>
                    </div>
                </div>
                <div style="font-size: 13px; margin-bottom: 10px;">
                    Đã kiểm tra <strong>{len(audit.checks)} tiêu chí</strong>: 
                    <span style="color: #10b981;">{audit.passed_checks_count} Đạt</span> | 
                    <span style="color: #ef4444;">{audit.failed_checks_count} Không đạt</span>
                </div>
                <div style="overflow-x: auto;">
                    <table>
                        <thead>
                            <tr>
                                <th>Tiêu chí kiểm định</th>
                                <th>Yêu cầu mong đợi</th>
                                <th>Thực tế phát hiện</th>
                                <th style="text-align: center;">Trạng thái</th>
                            </tr>
                        </thead>
                        <tbody>
                            {''.join(checks_rows)}
                        </tbody>
                    </table>
                </div>
                {recs_html}
            </div>
            """

        # Cognitive breakdown bars
        cb = report.pass2.cognitive_breakdown
        total_cog = max(1, cb.recognition_count + cb.comprehension_count + cb.application_count + cb.high_application_count)
        p_rec = round(cb.recognition_count / total_cog * 100, 1)
        p_comp = round(cb.comprehension_count / total_cog * 100, 1)
        p_app = round(cb.application_count / total_cog * 100, 1)
        p_high = round(cb.high_application_count / total_cog * 100, 1)

        # Questions rows
        question_rows = []
        for q in report.pass2.questions[:25]:  # Show up to first 25
            cog_color = {
                "RECOGNITION": "#10b981",
                "COMPREHENSION": "#3b82f6",
                "APPLICATION": "#f59e0b",
                "HIGH_APPLICATION": "#ef4444",
            }.get(q.cognitive_level.value, "#6b7280")

            opts_html = ""
            if q.options:
                opts_list = [f"<strong>{k}.</strong> {html.escape(v)}" for k, v in q.options.items()]
                opts_html = f"<div class='q-opts'>{' &nbsp;|&nbsp; '.join(opts_list)}</div>"

            ans_badge = (
                f"<span class='badge ans-badge'>Đ/Án: {q.detected_answer}</span>"
                if q.detected_answer
                else "<span class='badge gray-badge'>Chưa khớp</span>"
            )

            row = f"""
            <tr>
                <td style="font-weight: 600; text-align: center;">{q.question_index}</td>
                <td>
                    <div class="q-prompt">{html.escape(q.prompt[:150])}{'...' if len(q.prompt) > 150 else ''}</div>
                    {opts_html}
                </td>
                <td style="text-align: center;">
                    <span class="badge" style="background-color: {cog_color}; color: #fff;">{q.cognitive_level.value}</span>
                </td>
                <td style="text-align: center;">{ans_badge}</td>
            </tr>
            """
            question_rows.append(row)

        questions_table = "".join(question_rows) if question_rows else "<tr><td colspan='4' style='text-align:center;'>Không bóc tách câu hỏi riêng lẻ.</td></tr>"

        html_content = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DocInspector Audit - {html.escape(report.file_name)}</title>
    <style>
        :root {{
            --bg: #0f172a;
            --surface: #1e293b;
            --border: #334155;
            --text: #f8fafc;
            --text-muted: #94a3b8;
            --primary: #6366f1;
            --success: #10b981;
            --danger: #ef4444;
            --warning: #f59e0b;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
        body {{ background-color: var(--bg); color: var(--text); padding: 32px 16px; line-height: 1.6; }}
        .container {{ max-width: 1100px; margin: 0 auto; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid var(--border); padding-bottom: 20px; margin-bottom: 24px; }}
        .header-title h1 {{ font-size: 24px; font-weight: 700; color: #fff; }}
        .header-title p {{ color: var(--text-muted); font-size: 14px; margin-top: 4px; }}
        .badge-verified {{ background: #059669; color: #fff; padding: 6px 14px; border-radius: 9999px; font-size: 13px; font-weight: 600; text-transform: uppercase; }}
        
        .spoof-card {{ background: rgba(239, 68, 68, 0.15); border: 2px solid var(--danger); border-radius: 10px; padding: 18px 24px; margin-bottom: 24px; animation: pulse 2s infinite; }}
        .spoof-header {{ color: #fca5a5; font-size: 16px; margin-bottom: 8px; }}
        .spoof-body {{ color: #fee2e2; font-size: 14px; font-weight: 500; }}
        
        .grid-cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; margin-bottom: 24px; }}
        .card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 18px; }}
        .card-label {{ font-size: 12px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; margin-bottom: 6px; }}
        .card-val {{ font-size: 20px; font-weight: 700; color: #fff; }}
        
        .diff-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin-top: 10px; }}
        .diff-item {{ font-size: 13.5px; }}
        .diff-k {{ color: var(--text-muted); display: block; font-size: 12px; }}
        .diff-v {{ color: #fff; }}
        
        .passes-container {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 20px; margin-bottom: 24px; }}
        .pass-block {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 20px; }}
        .pass-title {{ font-size: 16px; font-weight: 700; margin-bottom: 14px; border-bottom: 1px solid var(--border); padding-bottom: 8px; display: flex; justify-content: space-between; }}
        .pass-time {{ font-size: 13px; color: #a5b4fc; font-weight: normal; }}
        .stat-line {{ display: flex; justify-content: space-between; padding: 6px 0; font-size: 14px; border-bottom: 1px dashed rgba(255,255,255,0.06); }}
        .stat-line:last-child {{ border-bottom: none; }}
        
        .cog-section {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 20px; margin-bottom: 24px; }}
        .bar-container {{ height: 16px; border-radius: 8px; overflow: hidden; display: flex; background: #334155; margin: 14px 0 10px 0; }}
        .bar-item {{ height: 100%; }}
        .cog-legend {{ display: flex; flex-wrap: wrap; gap: 16px; font-size: 13px; margin-top: 10px; }}
        .dot {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; margin-right: 6px; }}
        
        table {{ width: 100%; border-collapse: collapse; font-size: 13.5px; }}
        th, td {{ padding: 12px 14px; text-align: left; border-bottom: 1px solid var(--border); }}
        th {{ background: #162032; color: var(--text-muted); font-size: 12px; text-transform: uppercase; }}
        tr:hover {{ background: rgba(255, 255, 255, 0.02); }}
        .badge {{ padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; display: inline-block; }}
        .ans-badge {{ background: #065f46; color: #a7f3d0; }}
        .gray-badge {{ background: #374151; color: #9ca3af; }}
        .q-prompt {{ font-weight: 500; margin-bottom: 4px; }}
        .q-opts {{ font-size: 12px; color: var(--text-muted); }}
        
        .footer {{ text-align: center; color: var(--text-muted); font-size: 12px; margin-top: 36px; padding-top: 20px; border-top: 1px solid var(--border); }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="header-title">
                <h1>DocInspector Audit Report</h1>
                <p>File: <code>{html.escape(report.file_name)}</code> ({report.file_size_bytes:,} bytes)</p>
            </div>
            <div>
                <span class="badge-verified">⚡ 100% NON-AI VERIFIED</span>
            </div>
        </div>

        {verdict_card}

        {spoof_banner}

        {req_audit_html}

        {diff_card}

        {channel_html}

        <div class="grid-cards">
            <div class="card">
                <div class="card-label">Môn học phát hiện</div>
                <div class="card-val" style="color: #818cf8;">{report.detected_subject.value}</div>
            </div>
            <div class="card">
                <div class="card-label">Thể loại đề thi</div>
                <div class="card-val" style="color: #fbbf24; text-transform: uppercase;">{report.exam_track_label_vi}</div>
            </div>
            <div class="card">
                <div class="card-label">Dạng tài liệu / Đề thi</div>
                <div class="card-val" style="color: #38bdf8;">{report.exam_type.value}</div>
            </div>
            <div class="card">
                <div class="card-label">Thời gian phân tích</div>
                <div class="card-val" style="color: #34d399;">{report.total_execution_time_ms:.2f} ms</div>
            </div>
        </div>

        <div class="passes-container">
            <!-- Pass 1 -->
            <div class="pass-block">
                <div class="pass-title">
                    <span>Lần 1: Kỹ thuật & Ký tự</span>
                    <span class="pass-time">{report.pass1.execution_time_ms:.2f} ms</span>
                </div>
                <div class="stat-line"><span>Định dạng thực:</span><strong>{report.pass1.raw_file_type} ({report.pass1.magic_signature})</strong></div>
                <div class="stat-line"><span>Số trang:</span><strong>{report.pass1.page_count}</strong></div>
                <div class="stat-line"><span>Số từ / Ký tự:</span><strong>{report.pass1.metrics.word_count:,} từ / {report.pass1.char_count:,} ký tự</strong></div>
                <div class="stat-line"><span>Thời gian đọc ước tính:</span><strong>~{report.pass1.metrics.estimated_reading_time_minutes:.1f} phút</strong></div>
                <div class="stat-line"><span>Hệ chữ chính:</span><strong>{report.pass1.primary_script} ({report.pass1.detected_language})</strong></div>
                <div class="stat-line"><span>Độ hỗn loạn (Entropy):</span><strong>{report.pass1.metrics.entropy:.2f} bits/char</strong></div>
                <div class="stat-line"><span>PDF Scanned/Ảnh:</span><strong>{'Có (Ảnh chụp)' if report.pass1.is_scanned_pdf else 'Không (Vector Text)'}</strong></div>
            </div>

            <!-- Pass 2 -->
            <div class="pass-block">
                <div class="pass-title">
                    <span>Lần 2: Cấu trúc & Đề thi</span>
                    <span class="pass-time">{report.pass2.execution_time_ms:.2f} ms</span>
                </div>
                <div class="stat-line"><span>Số câu hỏi:</span><strong>{report.pass2.question_count}</strong></div>
                <div class="stat-line"><span>Số phương án (A-D):</span><strong>{report.pass2.options_count}</strong></div>
                <div class="stat-line"><span>Độ khó ước tính:</span><strong>{report.difficulty_assessment.score} / 10</strong></div>
                <div class="stat-line"><span>Định dạng chuẩn 2025:</span><strong>{'Chuẩn Bộ GD&ĐT 2025' if report.pass2.curriculum.moet_2025_compliant else 'Định dạng truyền thống'}</strong></div>
                <div class="stat-line"><span>Bộ sách / Chương trình:</span><strong>{report.pass2.curriculum.series_detected or 'Phổ thông'}</strong></div>
                <div class="stat-line"><span>Bảng đáp án / Lời giải:</span><strong>{'Có sẵn' if report.pass2.has_answer_keys else 'Không có'}</strong></div>
            </div>

            <!-- Pass 3 -->
            <div class="pass-block">
                <div class="pass-title">
                    <span>Lần 3: Ngữ nghĩa & Đối soát</span>
                    <span class="pass-time">{report.pass3.execution_time_ms:.2f} ms</span>
                </div>
                <div class="stat-line"><span>Độ tin cậy tuyệt đối:</span><strong>{report.confidence_score * 100:.1f}%</strong></div>
                <div class="stat-line"><span>Điểm đối soát 3 lần:</span><strong>{report.pass3.triple_verification_score:.1f} / 100</strong></div>
                <div class="stat-line"><span>Tình trạng tên file:</span><strong>{'🚨 BỊ GIẢ MẠO' if report.is_spoofed_filename else '✅ HỢP LỆ'}</strong></div>
                <div class="stat-line"><span>Trạng thái Consensus:</span><strong>{report.pass3.triple_verification_status}</strong></div>
                <div class="stat-line"><span>Thuật ngữ dẫn chứng:</span><strong>{', '.join(report.pass3.evidence_terms[:4])}</strong></div>
            </div>
        </div>

        <!-- Cognitive Breakdown Bar -->
        <div class="cog-section">
            <h3 style="font-size: 16px; font-weight: 700;">Phân bổ cấp độ nhận thức (Cognitive Taxonomy)</h3>
            <div class="bar-container">
                <div class="bar-item" style="width: {p_rec}%; background-color: #10b981;" title="Nhận biết: {p_rec}%"></div>
                <div class="bar-item" style="width: {p_comp}%; background-color: #3b82f6;" title="Thông hiểu: {p_comp}%"></div>
                <div class="bar-item" style="width: {p_app}%; background-color: #f59e0b;" title="Vận dụng: {p_app}%"></div>
                <div class="bar-item" style="width: {p_high}%; background-color: #ef4444;" title="Vận dụng cao: {p_high}%"></div>
            </div>
            <div class="cog-legend">
                <span><i class="dot" style="background: #10b981;"></i> Nhận biết: {cb.recognition_count} ({p_rec}%)</span>
                <span><i class="dot" style="background: #3b82f6;"></i> Thông hiểu: {cb.comprehension_count} ({p_comp}%)</span>
                <span><i class="dot" style="background: #f59e0b;"></i> Vận dụng: {cb.application_count} ({p_app}%)</span>
                <span><i class="dot" style="background: #ef4444;"></i> Vận dụng cao: {cb.high_application_count} ({p_high}%)</span>
            </div>
        </div>

        <!-- Itemized Questions Sample -->
        <div class="card" style="padding: 0; overflow: hidden; margin-bottom: 24px;">
            <div style="padding: 16px 20px; background: #162032; border-bottom: 1px solid var(--border); font-weight: 700;">
                Danh sách câu hỏi bóc tách chi tiết (Hiển thị tối đa 25 câu đầu tiên)
            </div>
            <div style="overflow-x: auto;">
                <table>
                    <thead>
                        <tr>
                            <th style="width: 60px; text-align: center;">#</th>
                            <th>Nội dung câu hỏi & Các phương án</th>
                            <th style="width: 140px; text-align: center;">Cấp độ nhận thức</th>
                            <th style="width: 120px; text-align: center;">Đáp án</th>
                        </tr>
                    </thead>
                    <tbody>
                        {questions_table}
                    </tbody>
                </table>
            </div>
        </div>

        <div class="footer">
            DocInspector Engine v2.0.0 • 100% Deterministic Rule-Based Architecture • Sub-millisecond execution
        </div>
    </div>
</body>
</html>
"""
        with open(out_p, "w", encoding="utf-8") as f:
            f.write(html_content)

        return out_p

    @classmethod
    def export_batch_csv(cls, reports: List[InspectionReport], output_path: Union[str, Path]) -> Path:
        """Exports inspection results for multiple documents to CSV format."""
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)

        fieldnames = [
            "file_name",
            "verdict",
            "verdict_label_vi",
            "file_size_bytes",
            "execution_time_ms",
            "document_category",
            "exam_type",
            "detected_subject",
            "exam_track",
            "exam_track_label_vi",
            "grade_level",
            "difficulty_score",
            "difficulty_tier",
            "recommended_duration_min",
            "meets_requirements",
            "requirements_profile",
            "channel_name",
            "channel_compliant",
            "detected_language",
            "confidence_score",
            "is_spoofed_filename",
            "spoof_warning",
            "question_count",
            "options_count",
            "has_answer_keys",
            "word_count",
            "page_count",
        ]

        with open(out_p, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in reports:
                is_eligible = "N/A"
                prof = "NONE"
                if r.requirement_audit:
                    is_eligible = "PASSED" if r.requirement_audit.is_eligible else "FAILED"
                    prof = r.requirement_audit.profile_applied

                ch_name = "N/A"
                ch_comp = "N/A"
                if r.channel_compliance:
                    ch_name = r.channel_compliance.channel_name
                    ch_comp = "COMPLIANT" if r.channel_compliance.is_compliant else "MISMATCH"

                writer.writerow({
                    "file_name": r.file_name,
                    "verdict": r.verdict.value,
                    "verdict_label_vi": r.verdict_label_vi,
                    "file_size_bytes": r.file_size_bytes,
                    "execution_time_ms": round(r.total_execution_time_ms, 2),
                    "document_category": r.document_category.value,
                    "exam_type": r.exam_type.value,
                    "detected_subject": r.detected_subject.value,
                    "exam_track": r.exam_track.value,
                    "exam_track_label_vi": r.exam_track_label_vi,
                    "grade_level": r.grade_level.value,
                    "difficulty_score": r.difficulty_assessment.score,
                    "difficulty_tier": r.difficulty_assessment.tier.value,
                    "recommended_duration_min": r.difficulty_assessment.recommended_duration_minutes,
                    "meets_requirements": is_eligible,
                    "requirements_profile": prof,
                    "channel_name": ch_name,
                    "channel_compliant": ch_comp,
                    "detected_language": r.detected_language,
                    "confidence_score": round(r.confidence_score, 4),
                    "is_spoofed_filename": r.is_spoofed_filename,
                    "spoof_warning": r.spoof_details or "",
                    "question_count": r.pass2.question_count,
                    "options_count": r.pass2.options_count,
                    "has_answer_keys": r.pass2.has_answer_keys,
                    "word_count": r.pass1.metrics.word_count,
                    "page_count": r.pass1.page_count,
                })

        return out_p
