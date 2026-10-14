---
name: hyperhub-skills-ecosystem
description: >-
  Hệ thống kỹ năng toàn diện tại D:\Project\Skills phục vụ thiết kế Web UI chuyển động,
  micro-interactions (Lucian UX/UI 200 elements, GSAP Skills), công nghệ frontend chất lượng cao
  (Addy Osmani agent-skills & web-quality-skills), cùng bot backend và DocInspector.
---

# HyperHub Skills Ecosystem (`D:\Project\Skills`)

Thư mục `D:\Project\Skills` là trung tâm tài nguyên và kỹ năng chuyên sâu được chuẩn hóa cho toàn bộ dự án HyperHub (Web, Bot, và DocInspector).

---

## 1. Danh Mục Các Bộ Kỹ Năng (Installed Skills)

| Tên Bộ Kỹ Năng | Thư Mục | Mô Tả & Điểm Mạnh |
| :--- | :--- | :--- |
| **Lucian UX/UI (Official)** | `lucian-uxui/` | Bộ CLI (`scripts/lucian-uxui.mjs`) tìm kiếm, lấy mã và chuyển đổi (porting) các thành phần giao diện không phụ thuộc framework |
| **Lucian UX/UI Prompt (Full 200)** | `lucian-uxui-prompt/` | Toàn bộ 200 elements HTML/CSS/JS tương tác, thư viện mẫu `tokens.css`, và phòng thí nghiệm tương tác `prompt-uxui-lab/` |
| **GreenSock GSAP Skills** | `gsap-skills/` | Hướng dẫn và mẫu chuyển động phức tạp với GSAP: React, ScrollTrigger, Flip, MorphSVG |
| **Addy Osmani Agent Skills** | `agent-skills/` | Chuẩn mực kỹ thuật Frontend UI Engineering, bảo mật (security-and-hardening) và tối ưu hóa hệ thống |
| **Web Quality & Accessibility** | `web-quality-skills/` | Kiểm thử tiếp cận WCAG (a11y), Core Web Vitals, và tối ưu hóa hiệu năng tải trang |
| **Lucian Curated Prototypes** | `ux-001` → `ux-039` | 9 bản mẫu HTML đơn lẻ do người dùng lưu trữ (Liquid glass button, Drag-and-drop upload, Sliding tabs, Play-pause morph, ...) |

---

## 2. Hệ Thống Design Tokens Chuẩn (Lucian `--ux-*`)

Toàn bộ thành phần UI tuân thủ hệ thống token trong `lucian-uxui-prompt/src/tokens.css`:

```css
:root {
  --ux-ease: cubic-bezier(.2, .8, .2, 1);
  --ux-spring: cubic-bezier(.34, 1.45, .64, 1);
  --ux-page: #F4F2EE;
  --ux-surface: #FFFFFF;
  --ux-ink: #16151B;
  --ux-accent: #6A57F2;
  --ux-accent-soft: rgba(106, 87, 242, .12);
  --ux-grad: linear-gradient(120deg, #7B61FF, #3D8BFF 55%, #1FB89A);
}

:root[data-theme="dark"], :root.dark {
  --ux-page: #07080D;
  --ux-surface: #13141C;
  --ux-ink: #F4F0E8;
  --ux-accent: #B7A4FF;
  --ux-accent-soft: rgba(183, 164, 255, .15);
  --ux-grad: linear-gradient(120deg, #B7A4FF, #7DB4FF 55%, #A5F2D3);
}
```

---

## 3. Cách Sử Dụng Lucian CLI trong Terminal / Agent

Để tìm kiếm và trích xuất nhanh bất kỳ element nào:

```bash
# Liệt kê tất cả danh mục
node D:\Project\Skills\lucian-uxui\scripts\lucian-uxui.mjs list

# Tìm kiếm thành phần theo từ khóa
node D:\Project\Skills\lucian-uxui\scripts\lucian-uxui.mjs search "button liquid"
node D:\Project\Skills\lucian-uxui\scripts\lucian-uxui.mjs search "upload drop"

# Lấy mã nguồn đầy đủ của 1 hoặc nhiều element
node D:\Project\Skills\lucian-uxui\scripts\lucian-uxui.mjs get 001 032
```
