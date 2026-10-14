---
name: ui-motion-web
description: >-
  Bộ sưu tập các thành phần UI Micro-Interactions và Animation cao cấp (Lucian UX/UI series)
  được lưu tại D:\Project\Skills. Sử dụng khi thiết kế, lập trình hoặc nâng cấp giao diện Web,
  bao gồm: Liquid Glass button, File Drag-and-Drop Upload, Sliding Pill Tabs, Play-Pause Morph,
  Rolling Label button, Floating Label input, OTP Code input, Password Strength meter, Fill Progress.
---

# UI Motion & Micro-Interactions Web Skills

Thư mục `D:\Project\Skills` lưu trữ các thành phần chuyển động UI/UX tương tác hiện đại, tinh tế dành riêng cho ứng dụng web HyperHub.

---

## 1. Hệ thống Motion Tokens & Animation Physics

Tất cả các thành phần sử dụng chung hệ số cong chuẩn xác để đảm bảo cảm giác tự nhiên, mượt mà và nảy:

```css
:root {
  /* Motion timing curves */
  --ux-ease: cubic-bezier(.2, .8, .2, 1);       /* Chuyển động lướt êm dịu, không giật */
  --ux-spring: cubic-bezier(.34, 1.45, .64, 1); /* Chuyển động nảy đàn hồi (spring physics) */

  /* Glassmorphism & Depth */
  --ux-glass: rgba(255, 255, 255, .08);
  --ux-glass-line: rgba(255, 255, 255, .18);
  --ux-shadow: rgba(0, 0, 0, .45);
  --ux-shadow-strong: rgba(0, 0, 0, .72);
  --ux-grad: linear-gradient(120deg, #8B6CFF, #3D8BFF 55%, #1FB89A);
}
```

---

## 2. Danh mục các thành phần (Catalog) trong `D:\Project\Skills`

| Mã UX | Tên thành phần | Tệp nguồn | Ứng dụng trong HyperHub |
| :--- | :--- | :--- | :--- |
| **UX-001** | **Liquid Glass Button** | `ux-001-liquid-glass-button-en.html` | Nút hành động chính (Nộp tài liệu, Tải thêm, Bộ lọc) với hiệu ứng lượn sóng và phản xạ ánh sáng |
| **UX-004** | **Fill Progress Download** | `ux-004-fill-progress-download-en.html` | Nút tải đề thi / đáp án với thanh tiến trình lấp đầy và biến đổi trạng thái hoàn tất |
| **UX-007** | **Play–Pause Morph** | `ux-007-play-pause-morph-en.html` | Trình phát nhạc Lo-fi học tập với nút Play/Pause biến hình SVG mượt mà và dải sóng Equalizer sống động |
| **UX-009** | **Rolling Label Button** | `ux-009-rolling-label-button-en.html` | Nút bấm có hiệu ứng lật chữ từng ký tự 3D khi hover và quả cầu icon xoay chuyển |
| **UX-025** | **Floating Label Field** | `ux-025-floating-label-field-en.html` | Ô nhập liệu tìm kiếm, tiêu đề tài liệu, tên trường với nhãn bay mượt mà |
| **UX-026** | **OTP Code Input** | `ux-026-otp-code-input-en.html` | Ô nhập mã bảo mật 6 số xác thực Discord / Admin với con trỏ nhấp nháy và tự động nhảy ô |
| **UX-032** | **Drag-and-Drop Upload** | `ux-032-file-drop-upload-en.html` | Khung kéo thả nộp đề thi (DocUploadZone) với viền sáng chạy quanh, hiệu ứng thả file và thanh tiến trình |
| **UX-036** | **Password Strength** | `ux-036-password-strength-en.html` | Thanh đo độ mạnh mật khẩu với 4 vạch chuyển màu động và danh sách tiêu chí kiểm tra |
| **UX-039** | **Sliding Pill Tabs** | `ux-039-sliding-tabs-pill-en.html` | Thanh chuyển Tab môn học / khối lớp (Dashboard) với con trượt dạng viên thuốc (pill) bám theo tab đang chọn |

---

## 3. Hướng dẫn Tích hợp vào React / Tailwind

### A. Sliding Pill Tabs (UX-039)
Dùng cho danh mục Khối Lớp & Môn Học:
- Đặt `relative` cho container và `relative z-10` cho các nút bấm tab.
- Thêm một `span` nền tuyệt đối (`absolute`) có `transition: all 0.35s cubic-bezier(0.34, 1.45, 0.64, 1)` bám theo vị trí `offsetLeft` và `offsetWidth` của tab được chọn.

### B. Liquid Glass Button (UX-001)
Dùng cho các nút kêu gọi hành động (CTA):
```jsx
<button className="relative overflow-hidden rounded-full backdrop-blur-md bg-white/10 dark:bg-white/5 border border-white/20 shadow-lg transition-transform duration-300 active:scale-95 hover:border-purple-400/50 hover:shadow-purple-500/20">
  <span className="relative z-10 font-semibold">{label}</span>
</button>
```

### C. Drag-and-Drop Upload Pulse (UX-032)
Dùng cho `DocUploadZone.tsx`:
- Hiệu ứng viền phát sáng gradient xoay quanh khi có file kéo qua (`isDragging`).
- Icon tài liệu nảy nhẹ (`transform: translateY(-4px) scale(1.05)`) khi hover hoặc kéo file vào.

### D. Play-Pause Morph (UX-007)
Dùng cho `LofiPlayer.tsx`:
- Morph 2 thẻ `<polygon>` trong SVG từ toạ độ tam giác Play sang toạ độ 2 vạch chữ nhật Pause bằng thuật toán nội suy điểm hoặc CSS transition.
