# Báo cáo bàn giao — HyperHub Web (`LEARN • CHILL • CONNECT`)

## 1. Tổng quan bản làm lại

Dự án đã được thiết kế và xây dựng lại toàn diện theo định hướng **Pixel Bloom** (kết hợp **editorial dark UI**, **voxel/pixel craft** từ biểu tượng HyperHub gốc và **layered cherry-blossom glow** `#9B5CFF` / `#FF4FCB` / `#FFB8E6` trên nền than ánh tím `#0E0C14`).

| Hạng mục | Trước khi làm lại | Sau khi làm lại |
| --- | --- | --- |
| Thương hiệu & logo | Bị lẫn câu chữ / tệp cấu hình `"Orbit"`, logo lệch màu xanh cyan | Khôi phục nguyên bản **HyperHub** (`LEARN • CHILL • CONNECT`), logo khối chữ H hồng-tím và hệ biểu tượng voxel |
| Hero section | Khối giới thiệu phẳng + canvas 3D xoay liên tục | Wordmark SVG **130 khối voxel** rơi theo cột & phản hồi con trỏ, 3 trụ cột pixel-wipe, headline tiếng Việt reveal theo từ, 2 dải môn học chạy ngược chiều, bảng trạng thái bot/kho đề thời gian thực |
| Cấu trúc cuộn (Scroll Storytelling) | Các section rời rạc, cùng một kiểu fade-up | Dẫn chuyện 3 chương **01 / LEARN**, **02 / CHILL**, **03 / CONNECT** + **Chapter Rail** chỉ báo tiến độ thực tế và nhảy chương |
| Tương tác con trỏ | 1 đốm tròn cố định (`MouseAura`) | Hệ thống pointer **3 tầng (`rich` / `standard` / `lite`)**: Aura kép lệch pha, Bloom Grid, Spotlight trên thẻ lớn, Magnetic CTA, Tilt 3° duy nhất trên thẻ sáng lập chính |
| Chuyển trang `/` ↔ `/hub` | Đổi state thô hoặc reload | **View Transitions API** (`startViewTransition` + `flushSync`) + tự động **preload gói `/hub`** khi rảnh hoặc khi rê chuột vào nút mở kho |
| Font & CLS | Tải Google Fonts qua mạng lúc runtime (`CLS ~ 0.106`) | Tự host `.woff2` (`Be Vietnam Pro` 400–800 + `Silkscreen` 400/700) kèm `<link rel="preload">` → **`CLS = 0.0002 – 0.0007`** |
| Thư viện animation | Phụ thuộc hiệu ứng rời rạc | **0 thư viện animation mới** — sử dụng CSS custom properties + 3 module runtime nhẹ (`reveal.ts`, `pointer.ts`, `scroll.ts`) |

---

## 2. Kiến trúc mã nguồn chính

### 2.1. Hệ thống Motion (`src/motion/` & `src/styles/`)
Chi tiết đầy đủ về token, easing, duration và quy tắc phối hợp nằm tại [`docs/MOTION_SYSTEM.md`](./MOTION_SYSTEM.md).

- [`src/motion/capabilities.ts`](../src/motion/capabilities.ts): Phát hiện `prefers-reduced-motion`, `(hover: hover) and (pointer: fine)`, cấu hình phần cứng (`deviceMemory`, `hardwareConcurrency`, `saveData`) và phân tầng `pointerTier`: `'rich' | 'standard' | 'lite'`.
- [`src/motion/reveal.ts`](../src/motion/reveal.ts): Một `IntersectionObserver` dùng chung toàn trang, gắn `data-revealed="true"` trực tiếp lên DOM rồi `unobserve` ngay (không gây React re-render).
- [`src/motion/pointer.ts`](../src/motion/pointer.ts): Một listener `pointermove` passive + một vòng `requestAnimationFrame` tự ngủ khi chuột dừng, điều khiển Aura gần/xa, Bloom Grid, Spotlight (`--px`, `--py`), Magnetic CTA và Tilt 3°.
- [`src/motion/scroll.ts`](../src/motion/scroll.ts): Một listener `scroll` passive + rAF xử lý parallax nhẹ cho 2 orb nền và cập nhật tiến độ `ChapterRail` (đọc hình học trước, ghi `transform: scaleY` sau để tránh layout thrashing).
- [`src/styles/motion.css`](../src/styles/motion.css): Toàn bộ motion tokens, 8 preset reveal (`words`, `fade`, `rise`, `slide-l`, `slide-r`, `panel`, `draw`, `pixel`), quy tắc hover/focus/active và nhánh `@media (prefers-reduced-motion: reduce)`.
- [`src/styles/hyperhub.css`](../src/styles/hyperhub.css): Bảng màu thương hiệu, bề mặt thẻ kính tối, lưới pixel, nút vát góc bậc (`hh-btn`), ngăn kéo mobile và bố cục chương.
- [`src/styles/fonts.css`](../src/styles/fonts.css): Khai báo `@font-face` tự host cho `Be Vietnam Pro` và `Silkscreen` (`public/fonts/*.woff2`).

### 2.2. Các nguyên tử giao diện (`src/components/hh/`)
- [`PixelWordmark.tsx`](../src/components/hh/PixelWordmark.tsx): Wordmark SVG `HYPER / HUB` gồm 130 khối voxel rơi theo cột lúc mở trang và nhô nhẹ theo bán kính con trỏ trên máy cấu hình cao (`rich`).
- [`PixelMark.tsx`](../src/components/hh/PixelMark.tsx): Biểu tượng chữ H 5×5 bằng các ô pixel có hiệu ứng sóng theo cột khi hover logo trên thanh điều hướng.
- [`Ambient.tsx`](../src/components/hh/Ambient.tsx): Lớp nền đa tầng (2 orb tím/hồng trôi chậm, lưới điểm pixel, Bloom Grid bám con trỏ, Aura kép và 5 cánh hoa pixel rơi chậm khi hero còn trong màn hình).
- [`Controls.tsx`](../src/components/hh/Controls.tsx): `<PixelButton>` (magnetic nhẹ, trạng thái loading/disabled chuẩn `aria-busy`, mũi tên dịch chuyển), `<SpotSurface>` (spotlight bám chuột, tilt tùy chọn) và `<InlineCTA>`.
- [`Reveal.tsx`](../src/components/hh/Reveal.tsx): `<Reveal>` và `<SplitWords>` (tách theo **từng từ** với đệm mask `0.14em / 0.12em` để bảo toàn tuyệt đối dấu thanh tiếng Việt như `Ể`, `Ỗ`, `ặ`).
- [`Chapters.tsx`](../src/components/hh/Chapters.tsx): `<ChapterHeader>` (số thứ tự, nhãn pixel wipe `steps(8)`, đường kẻ vẽ dần) và `<ChapterRail>` (thanh tiến độ 3 chương cố định bên trái cho màn hình `≥ 1480px`).
- [`BrandGlyphs.tsx`](../src/components/hh/BrandGlyphs.tsx): Bộ icon SVG sắc nét cho Discord, Messenger và các huy hiệu.

### 2.3. Các phân khu nội dung (`src/components/`)
- [`Navbar.tsx`](../src/components/Navbar.tsx): Chỉ báo pill trượt mượt giữa các mục (`--hh-ease-inout`), tự thu gọn khi cuộn, ngăn kéo mobile giữ sẵn trong DOM (`data-open`, `inert`, khóa cuộn, đóng bằng `Escape` và trả focus về nút mở).
- [`Hero.tsx`](../src/components/Hero.tsx): Chuỗi intro phân nhịp trong ~1s không khóa thao tác; hiển thị trạng thái thật của Discord Bot và tổng số đề từ [`useHubPulse.ts`](../src/hooks/useHubPulse.ts) (không dùng số liệu giả).
- [`CommunityIntro.tsx`](../src/components/CommunityIntro.tsx) (**Chương 01 — LEARN**): Bố cục bất đối xứng giới thiệu Web Hub, Discord Bot và tài liệu chọn lọc kèm nút mở trực tiếp `/hub`.
- [`DreamAspirations.tsx`](../src/components/DreamAspirations.tsx) (**Chương 02 — CHILL**): Không gian xả hơi âm nhạc/vẽ/tâm sự + bảng lưu mục tiêu trường mơ ước vào `localStorage` với crossfade 320ms và thông báo trạng thái thật (`role="status"`).
- [`CommunityChannels.tsx`](../src/components/CommunityChannels.tsx) (**Chương 03 — CONNECT**): Hai cổng kết nối chính thức (Discord Server `discord.gg/hyperhub` và nhóm Messenger) đi vào từ 2 hướng đối xứng (`slide-l` / `slide-r`).
- [`CoFounders.tsx`](../src/components/CoFounders.tsx): Dải đồng sáng lập với đường mạch vẽ dần (`draw`), thẻ sáng lập chính (`panel` + tilt 3°) và 4 thẻ đồng sáng lập phụ.
- [`Footer.tsx`](../src/components/Footer.tsx): Đại cảnh CTA cuối trang (`SplitWords` + `PixelButton`), liên kết điều hướng có gạch chân trượt và thông tin bản quyền.

---

## 3. Tối ưu gói tải (Bundle) & Hiệu năng

1. **Tách gói `/hub` (Code-splitting)**:
   - Không gian kho đề [`Dashboard.tsx`](../src/components/Dashboard.tsx) được tải lười (`React.lazy`) qua [`src/hubLoader.ts`](../src/hubLoader.ts).
   - Tự động **preload trước** trong `requestIdleCallback` (sau 1.8s) hoặc ngay khi người dùng rê chuột / focus vào bất kỳ nút `"Mở Kho Đề"` / `"Web Hub"` nào.
   - Gói JS khởi đầu của trang chủ giảm từ **~600 kB** xuống **330.75 kB** (**100.37 kB gzip**); thời gian hiển thị Hero đầu tiên trên Chrome headless giảm từ **~1200ms** xuống **~655ms**.
2. **Không dùng `filter: blur()` động cỡ lớn**:
   - Toàn bộ orb nền và cursor aura dùng `radial-gradient` kết hợp `transform: translate3d(...)`, chỉ có duy nhất một lớp `backdrop-filter` trên thanh điều hướng khi đã cuộn.
3. **Tự động ngủ & tạm dừng**:
   - Vòng lặp `pointer.ts` tự ngắt `requestAnimationFrame` ngay khi khoảng cách hội tụ `< 0.15px`.
   - Khi Hero cuộn ra khỏi màn hình (`data-out="true"`), các dải môn học chạy ngang và cánh hoa pixel tự động `animation-play-state: paused`.

---

## 4. Kết quả Kiểm thử Thực tế (Browser Visual QA & Performance)

Đã kiểm thử tự động và trực quan bằng Playwright Chromium trên bản production build (`vite preview`):

### 4.1. Độ ổn định bố cục & khả năng truy cập trên các khung nhìn
| Khung nhìn / Chế độ | Kích thước | Tràn ngang (`overflowX`) | Lệch bố cục (`CLS`) | Kết quả kiểm tra chức năng |
| --- | --- | --- | --- | --- |
| **Desktop rộng** (có `ChapterRail`) | `1520 × 940` | `0px` | `0.0007` | Hero wordmark, 3 trụ cột, CTA nằm gọn trong màn hình đầu; `ChapterRail` nhảy đúng chương |
| **Desktop tiêu chuẩn** | `1440 × 900` | `0px` | `0.0007` | Wordmark tự co thông minh theo `100svh`, cả 2 CTA chính hiển thị trọn vẹn ở màn hình đầu (`bottom = 787px < 900px`) |
| **Tablet** | `820 × 1180` | `0px` | `0.0004` | Lưới thẻ tự chuyển 1–2 cột cân đối, tắt hoàn toàn hiệu ứng con trỏ chuột |
| **Mobile** | `390 × 844` | `0px` | `0.0002` | Ngăn kéo menu mượt, đóng bằng `Escape` trả focus chuẩn, khóa cuộn nền, ẩn bớt orb/noise nặng |
| **Reduced Motion** (`prefers-reduced-motion: reduce`) | `1440 × 900` | `0px` | `0.0000` | Toàn bộ nội dung hiển thị ngay lập tức (`opacity: 1`), tắt mọi animation dài, parallax, aura và cánh hoa |

### 4.2. Đo FPS dưới giới hạn CPU 4× (Chrome Headless + Software Rasterizer)
Đo trong môi trường khắc nghiệt nhất (CPU bị bóp chậm 4 lần bằng CDP `Emulation.setCPUThrottlingRate({ rate: 4 })` và vẽ bằng phần mềm không có GPU phần cứng, trung vị 3 lần chạy cho mỗi cấu hình):

| Kịch bản đo (CPU Throttle 4×) | Bản mới — Tầng `rich` (≥8 luồng) | Bản mới — Tầng `standard` (4 luồng) | Bản mới — Tầng `lite` (2 luồng) | Bản cũ (Baseline trước khi làm lại) |
| --- | --- | --- | --- | --- |
| **Di chuyển chuột liên tục (Pointer Move)** | **52.0 FPS** | **44.4 FPS** | **46.8 FPS** | 47.7 FPS |
| **Cuộn trang qua các chương (Scroll)** | **33.4 FPS** | **36.6 FPS** | **30.7 FPS** | 37.8 FPS |
| **Chuyển view `/` → `/hub` → `/`** | **188ms / 56ms** (0 lỗi console) | **188ms / 56ms** | **188ms / 56ms** | — |

---

## 5. Hướng dẫn chạy & đóng gói

```bash
# 1. Cài đặt phụ thuộc (nếu cần)
npm install

# 2. Chạy môi trường phát triển (HMR)
npm run dev

# 3. Kiểm tra kiểu TypeScript & đóng gói Production
npm run build

# 4. Xem thử bản Production
npm run preview
```
