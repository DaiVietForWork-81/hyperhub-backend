# HyperHub Motion System

> Phạm vi: trang chủ HyperHub (`/`) và lớp chuyển view Home ↔ Hub. Workspace Hub (`/hub`) giữ nguyên chuyển động của Dashboard cũ, chỉ thêm cursor aura ở cường độ thấp.

## 1. Định hướng — "Pixel Bloom"

HyperHub bắt nguồn từ logo voxel/pixel hồng tím giữa vườn anh đào. Ngôn ngữ chuyển động tách làm hai giọng rõ ràng:

| Giọng | Dùng cho | Đặc tính |
| --- | --- | --- |
| **Smooth** (mượt) | Nội dung: heading, đoạn văn, card, menu, chuyển view | Easing có tăng tốc / giảm tốc tự nhiên, quãng ngắn |
| **Pixel step** (bậc 8-bit) | Chỉ accent thương hiệu: chữ LEARN/CHILL/CONNECT, gạch chân pillar, cánh hoa, spinner | `steps()` — gợi thế giới khối |

**Điểm nhấn duy nhất (signature moment):** wordmark `HYPER / HUB` dựng từ 130 khối voxel rơi vào chỗ theo cột trong ~1 giây, rồi phản hồi con trỏ (khối gần chuột nhô lên). Mọi thứ khác tiết chế để không tranh sự chú ý.

**Phân cấp thị giác**
1. Chính: wordmark + headline hero.
2. Hỗ trợ: pillar LEARN • CHILL • CONNECT, CTA, chữ pixel mở đầu mỗi chương.
3. Nền: ambient orb, lưới pixel, bloom grid quanh con trỏ, aura.

## 2. Token

Định nghĩa tại `src/styles/motion.css` (`:root`).

### Duration
| Token | Giá trị | Vai trò |
| --- | --- | --- |
| `--hh-dur-micro` | 140ms | Nhấn nút, toggle, feedback tức thì |
| `--hh-dur-hover` | 200ms | Đổi màu, lift khi hover |
| `--hh-dur-enter` | 380ms | Opacity khi component xuất hiện |
| `--hh-dur-section` | 560ms | Transform reveal heading / section |
| `--hh-dur-page` | 240ms | Chuyển view Home ↔ Hub |
| `--hh-dur-ambient` | 48s (orb hồng 64s) | Orb nền trôi chậm |

### Easing
| Token | Đường cong | Vai trò |
| --- | --- | --- |
| `--hh-ease-out` | `cubic-bezier(0.16, 1, 0.3, 1)` | Reveal nội dung |
| `--hh-ease-soft` | `cubic-bezier(0.25, 1, 0.5, 1)` | Hover, màu, opacity |
| `--hh-ease-inout` | `cubic-bezier(0.65, 0, 0.35, 1)` | Chuyển trạng thái hai chiều (nav indicator, đường kẻ vẽ dần, orb) |
| `--hh-ease-drop` | `cubic-bezier(0.34, 1.42, 0.64, 1)` | Khối pixel rơi (nảy nhẹ), sóng logo |
| `--hh-ease-press` | `cubic-bezier(0.5, 0, 0.75, 0)` | Nhấn xuống, view cũ thoát ra |
| `--hh-steps-pixel` | `steps(8, end)` | Wipe 8-bit cho accent thương hiệu |

### Stagger & khoảng cách
| Token | Giá trị |
| --- | --- |
| `--hh-stagger-tight` | 35ms (từng từ của heading, tối đa 14 bước) |
| `--hh-stagger-base` | 70ms (nhóm card) |
| `--hh-stagger-loose` | 110ms (thành viên sáng lập) |
| `--hh-rise-sm` / `--hh-rise-md` | 10px / 22px |
| `--hh-lift` | −3px |

## 3. Reveal presets (khi cuộn tới)

Component: `<Reveal preset="…" delay={ms}>` — `src/components/hh/Reveal.tsx`.
Runtime: **một** `IntersectionObserver` dùng chung (`src/motion/reveal.ts`), ghi `data-revealed="true"` thẳng lên DOM rồi `unobserve` — không setState, không re-render.

| Preset | Dùng cho | Chuyển động |
| --- | --- | --- |
| `words` | Heading chương, CTA footer | Từng **từ** trồi lên trong mask (không tách ký tự → giữ dấu thanh tiếng Việt). Mask có padding 0.14em trên / 0.12em dưới để không cắt dấu `Ể Ỗ ặ` |
| `fade` | Đoạn văn, tiêu đề phụ, khối có modal bên trong | Opacity + rise 10px |
| `rise` | Card nhỏ, ghi chú, dải ngang | Opacity + rise 22px |
| `slide-l` / `slide-r` | Cặp card đối xứng (Discord / Messenger, cột phải hệ sinh thái) | Đi vào từ hai phía 28px |
| `panel` | Khối lớn (Web Hub, bảng ước mơ, thẻ sáng lập chính) | Clip từ dưới (`inset(0 0 14% 0)`) + scale 0.985 → 1 |
| `draw` | Đường kẻ chương, sợi nối các đồng sáng lập | `scaleX` 0 → 1 trong 900ms |
| `pixel` | Chữ LEARN / CHILL / CONNECT mở chương | Wipe trái→phải bằng `steps(8)` (clip đặt trên phần tử con để IO vẫn đo được diện tích) |

Quy tắc:
- Không dùng một kiểu fade-up cho mọi thứ — chọn preset theo **vai trò** nội dung.
- Stagger chỉ trong nhóm ≤ 4–8 phần tử.
- Phần tử reveal và phần tử có hover transform là **hai lớp DOM khác nhau** (tránh transition của reveal đè lên hover).
- Nội dung chỉ bị ẩn khi `<html>` có class `hh-motion` (gắn bằng script inline trước khi vẽ; không có khi tắt JS, khi reduced-motion hoặc thiếu IntersectionObserver).

## 4. Hero intro (một lần, không chặn thao tác)

| Thời điểm | Phần tử | Kỹ thuật |
| --- | --- | --- |
| 0ms | Ambient nền | Fade 900ms |
| 90–~700ms | 130 khối wordmark | Rơi theo cột (`--hh-ease-drop`, 460ms/khối) |
| 420 / 520 / 620ms | LEARN / CHILL / CONNECT | Pixel wipe `steps(8)`; gạch chân vẽ sau +160ms |
| 560ms + 35ms/từ | Headline | Word mask reveal |
| 700ms | Cột môn học | Fade |
| 820ms | Mô tả | Fade + rise |
| 900 / 980ms | CTA chính / Discord | Fade + rise |
| 1080ms | Trạng thái bot thật | Fade |

Không có splash screen. CTA bấm được ngay từ đầu (opacity không chặn click).

## 5. Pointer layer (chỉ chuột thật, phân 3 tầng theo cấu hình máy)

Bật khi `(hover: hover) and (pointer: fine)` **và** không reduced-motion. Runtime: `src/motion/pointer.ts` — **một** listener `pointermove` passive + **một** vòng rAF cho mọi follower, tự ngủ khi đứng yên, chỉ ghi `transform` / CSS variable trực tiếp lên phần tử.

`pointerTier` (`src/motion/capabilities.ts`) tự chọn cấu hình mượt nhất theo năng lực thiết bị (`data-pointer-tier` trên `<html>`):
- **`rich`** (máy ≥ 8 luồng, ≥ 8GB RAM): Aura gần + Aura xa + Bloom grid + Wordmark block lift + Spotlight + Magnetic CTA + Founder tilt 3°.
- **`standard`** (máy tầm trung 4–6 luồng): Aura gần + Aura xa + Spotlight + Magnetic CTA (tắt Bloom grid và rAF 130 khối wordmark để giảm tổng diện tích composite).
- **`lite`** (máy cấu hình thấp ≤ 2 luồng / ≤ 2GB RAM / `Save-Data`): chỉ giữ 1 lớp Aura gần (320px) + Magnetic CTA; tắt Aura xa, Bloom grid, Spotlight, Wordmark block lift và Tilt.

| Lớp | Hệ số làm mượt | Tầng bật | Hiệu ứng |
| --- | --- | --- | --- |
| Aura gần (hồng, 320px) | 0.18 | `rich`, `standard`, `lite` | Glow bám sát |
| Aura xa (tím, 680px) | 0.07 | `rich`, `standard` | Glow trễ → chiều sâu |
| Bloom grid (520px) | 0.20 | `rich` | Lưới pixel hồng sáng lên quanh con trỏ; lưới bên trong dịch ngược để đứng yên với viewport → chỉ có transform, không repaint |
| Wordmark | rAF cục bộ | `rich` | Khối trong bán kính 26 đơn vị nhô lên ≤ 3.4px bằng thuộc tính `translate` (không đè transform của intro) |
| Card `hh-spot` | rAF cục bộ khi hover | `rich`, `standard` | Spotlight radial theo `--px/--py` |
| Thẻ sáng lập chính | rAF cục bộ | `rich` | **Phần tử duy nhất có tilt**, tối đa 3° |
| CTA chính (hero, footer) | rAF cục bộ | `rich`, `standard`, `lite` | Magnetic tối đa 5px ngang / 3px dọc — vùng bấm không trượt khỏi tay |

Không thay con trỏ hệ thống, `pointer-events: none` cho mọi lớp trang trí, ẩn hẳn trên `(hover: none), (pointer: coarse)`.

## 6. Scroll layer

`src/motion/scroll.ts` — một listener `scroll` passive + rAF.
- **Parallax**: orb tím dịch `−0.06 × scrollY`, orb hồng `−0.12 × scrollY`. Chỉ nền; nội dung không parallax. Tắt khi reduced-motion / thiết bị yếu.
- **Chapter rail** (≥1480px): chỉ báo tiến độ LEARN → CHILL → CONNECT, đọc layout trước, ghi `scaleY` sau (không layout thrashing), bấm để nhảy chương. Có chức năng thật, không trang trí.
- **Anchor**: offset 88px dưới header cố định (`ANCHOR_OFFSET`), `scroll-margin-top: 88px` cho fallback native; sau khi cuộn, focus chuyển tới section.
- Không pinned/sticky section — nội dung không cần trình bày tuần tự bắt buộc, tránh cảm giác bị kẹt.

## 7. Hover & micro-interaction presets

| Preset | Thành phần | Hành vi |
| --- | --- | --- |
| `hh-btn` | CTA | Góc bậc pixel + bevel voxel. Hover: gradient trượt, nâng 2px, glow tăng, mũi tên chạy 4px. Active: lún 1px + scale 0.98, bevel đảo. Focus-visible: viền hồng 2px. Disabled / loading (`aria-busy`, spinner pixel) |
| `hh-lift` | Card thông tin | Nâng 3px, viền sáng hơn, bóng tím nhiều lớp; icon `hh-nudge` dịch 2px chéo lên |
| `hh-spot` | Card lớn | Spotlight bám con trỏ |
| `hh-note` / `hh-founder-mini` | Mục "yên tĩnh" (CHILL, đồng sáng lập) | Chỉ hiện nền + viền khi hover — không lift mạnh |
| `hh-link` | Link chân trang | Gạch chân chạy từ trái, rút về phải |
| `hh-inline-cta` | "Mở kho đề" | Gạch chân lớn dần, icon chéo lên |
| `hh-toggle-chip` | Gợi ý trường | `aria-pressed`, nhấn scale 0.96 |
| Nav indicator | Header | Pill trượt tới mục đang hover/focus (320ms `--hh-ease-inout`), về mục active khi rời |
| Logo | Header | Các ô chữ H nhảy lần lượt theo cột (sóng) |

Mọi hover chỉ áp dụng trong `@media (hover: hover) and (pointer: fine)`; không thông tin nào chỉ hiện khi hover.

## 8. Trạng thái & chuyển cảnh

- **Home ↔ Hub**: View Transitions API (`document.startViewTransition` + `flushSync`): view cũ thoát 160ms, view mới vào 240ms. Trình duyệt không hỗ trợ / reduced-motion → đổi tức thì. Back/Forward cũng dùng cùng cơ chế. Không remount thừa.
- **Mobile drawer**: luôn mount; mở/đóng bằng `data-open` (scrim fade, panel trượt 14px, từng mục stagger 35ms); `inert` khi đóng; Esc đóng và trả focus về nút menu; khóa cuộn (kể cả Lenis).
- **Bảng ước mơ**: crossfade form ↔ thẻ đã lưu 320ms; phản hồi thành công / thất bại **thật** (dựa trên kết quả `localStorage.setItem`), tự ẩn sau 3.2s, `role="status"`.
- **Trạng thái bot / số đề** (`useHubPulse`): `checking` → `online` (chấm vuông xanh có nhịp ping) / `offline` (chấm đỏ tĩnh). Timeout 5s, không vòng loading vô hạn, không hiển thị số giả; số đề chỉ hiện (và chỉ đếm tăng) khi API trả dữ liệu thật.

## 9. Reduced motion

Khi `prefers-reduced-motion: reduce`:
- Không gắn `hh-motion` → mọi reveal hiển thị sẵn.
- Tắt: intro keyframes, parallax, tilt, magnetic, aura, bloom grid, cánh hoa, marquee, orb drift, View Transition, Lenis.
- Giữ nguyên: toàn bộ nội dung, route, form, trạng thái hover màu (không chuyển động).

## 10. Thiết bị yếu & mobile

- `isLowPowerDevice()` (Save-Data, ≤2GB RAM, ≤2 nhân) → bỏ parallax và cánh hoa.
- `<768px`: ẩn orb thứ hai, noise, cánh hoa. Không cursor effect trên cảm ứng.
- Marquee và cánh hoa **tạm dừng** khi hero ra khỏi màn hình và khi hover cột môn học.
- Blur lớn duy nhất: `backdrop-filter` của header khi đã cuộn. Glow dùng `radial-gradient` thay cho `filter: blur`.

## 11. Công nghệ

- Không thêm thư viện animation. CSS transitions/keyframes + 3 module runtime nhỏ (`reveal.ts`, `pointer.ts`, `scroll.ts`).
- Giữ Lenis (đã có sẵn) cho cuộn mượt trên desktop.
- Bỏ `SpaceCubeBackground` (canvas 3D) và `MouseAura` cũ khỏi trang chủ — thay bằng lớp ambient thuần CSS transform.

## 12. Kết quả đo (Chrome headless, CPU throttle 4×, raster phần mềm)

Xem `docs/HANDOVER.md` mục QA cho số liệu đầy đủ.
