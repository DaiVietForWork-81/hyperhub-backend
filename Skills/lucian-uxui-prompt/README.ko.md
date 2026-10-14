[🇰🇷 한국어](README.ko.md) · [🇺🇸 English](README.md)

# Lucian UX/UI Prompt

![Lucian UX/UI Prompt: 인터랙티브 UI 요소 200개](.github/cover.png)

바로 눌러 볼 수 있는 UI 요소 200개를 모았습니다. 마음에 드는 요소는 AI 프롬프트나 실제 코드로 가져가세요. 모든 요소가 라이트·다크 테마, 마우스·터치·키보드 조작, 동작 줄이기 설정을 지원하고, 외부 라이브러리는 쓰지 않습니다.

**갤러리: [lucianlabs.dev/uxui-prompt](https://lucianlabs.dev/uxui-prompt/)**

## 사용법

1. 갤러리에서 요소를 직접 눌러 보세요. 화면에 보이면 스스로 시연하고, 언제든 직접 조작할 수 있습니다.
2. **프롬프트 복사**를 누르세요. 요소의 실행 코드 전체와 적용 지침이 함께 들어 있습니다.
3. Claude Code, Cursor, Codex 같은 AI 코딩 도구에 붙여넣고 `[삽입 위치]`(바꿀 요소가 있으면 `[교체 대상]`도)를 채워 보내면 됩니다.

AI는 프로젝트의 프레임워크와 스타일, 테마 방식을 먼저 확인한 뒤 요소를 컴포넌트로 옮깁니다. `--ux-*` 색 토큰은 프로젝트의 테마 변수에 연결하고, 바꾼 파일과 확인하지 못한 항목을 알려 줍니다.

직접 옮기고 싶다면 **코드 복사**로 HTML·CSS·JS 원본을 받거나, **코드 파일 받기**로 테마 전환 버튼이 있는 단독 HTML 파일을 저장하세요. 특정 요소는 `https://lucianlabs.dev/uxui-prompt/#001`처럼 번호로 바로 연결할 수 있습니다.

## AI 에이전트에서 쓰기

[lucian-uxui 스킬](https://github.com/Seokwoooo/lucian-uxui)을 설치하면 에이전트가 직접 요소를 찾아 프로젝트에 옮겨 넣습니다.

```sh
npx skills add Seokwoooo/lucian-uxui
```

설치한 뒤 "카페 랜딩 페이지 만들어줘. lucian-uxui 스킬로 여기 요소를 우선 써줘."처럼 요청하면 됩니다. 스킬이 읽는 데이터는 [`api/v1/`](api/v1)에 있습니다. `src/elements`에서 생성한 파일이고, `https://lucianlabs.dev/uxui-prompt/api/v1/`에서도 받을 수 있습니다.

## 로컬에서 실행

Node.js만 있으면 됩니다. 설치할 패키지는 없습니다.

```sh
git clone https://github.com/Seokwoooo/lucian-uxui-prompt.git
cd lucian-uxui-prompt
node src/build.mjs
open prompt-uxui-lab/index.html
```

빌드는 요소 파일 형식을 모두 검사한 뒤 갤러리 전체를 HTML 파일 하나로 만듭니다.

## 요소 파일 형식

요소 하나는 파일 하나, `src/elements/NNN-slug.html`입니다.

```html
<!-- @meta {"title":"…","category":"버튼","summary":"…","hint":"…","shape":"square","tags":["button"]} -->
<!-- @demo [["wait",400],["tap",".u001-btn"],["wait",1200]] -->
<!-- @en {"title":"…","summary":"…","hint":"…","map":[["계속하기","Continue"]]} -->
<style>.u001{…} .u001-btn{…}</style>
<div class="ux u001">…</div>
<script>(() => { const root = document.currentScript.previousElementSibling; … })();</script>
```

- `@meta`: 제목, 분류, 설명입니다. 원문 언어는 한국어입니다.
- `@demo`: 자동 시연 단계입니다(`wait`, `tap`, `hover`, `glide`, `drag`, `type` 등).
- `@en`: 영어 제목과 설명, 그리고 요소 코드 속 문구를 영어로 바꾸는 문자열 표입니다.
- 모든 CSS 선택자는 `.uNNN` 안에서만 동작하고, 스크립트는 `document.currentScript`로 자기 루트를 찾습니다. 그래서 요소끼리 서로 간섭하지 않습니다.
- 색은 [`src/tokens.css`](src/tokens.css)의 `--ux-*` 토큰만 씁니다. 토큰에는 라이트와 다크 값이 모두 들어 있습니다.

`node src/build.mjs`는 이 규칙을 어긴 파일을 거부합니다.

## 라이선스

[MIT](LICENSE) © 2026 Seokwoooo. 개인·상업 프로젝트에 자유롭게 쓸 수 있습니다. 갤러리에서 복사한 코드 맨 위에는 출처와 라이선스를 적은 주석 한 줄이 붙어 있으니, 파일에 남겨 주세요.
