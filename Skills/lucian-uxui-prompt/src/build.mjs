// lucianLabs UI 요소 갤러리 빌드
// 실행: node prompt-uxui/src/build.mjs
// 입력: src/tokens.css, src/elements/NNN-slug.html (요소 200개), src/gallery/{index.html,gallery.css,gallery.js,i18n-core.js}
// 요소 파일 머리: <!-- @meta {...} --> 필수, <!-- @demo [...] --> 자동 재생 시연, <!-- @en {...} --> 영어 제목·설명·번역 목록
// 출력: prompt-uxui/prompt-uxui-lab/index.html (단일 파일, 모든 코드를 인라인으로 포함)
import { readFileSync, readdirSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const elDir = join(here, 'elements');
const galDir = join(here, 'gallery');
const outDir = join(here, '..', 'prompt-uxui-lab');
const outFile = join(outDir, 'index.html');

// 분류와 기본 색(타일 빛 번짐). 요소 @meta의 hue, hue2가 있으면 그 값을 씁니다
const CATEGORIES = {
  '버튼': ['#7B61FF', '#3D8BFF'],
  '토글·선택': ['#14B8A6', '#7B61FF'],
  '입력·검색': ['#3D8BFF', '#22C3A6'],
  '메뉴·탭': ['#F59E0B', '#FF6B8B'],
  '카드·콘텐츠': ['#FF6B8B', '#7B61FF'],
  '로그인·가입': ['#6366F1', '#22C3A6'],
  '알림·피드백': ['#FB923C', '#7B61FF'],
  '로딩·진행': ['#06B6D4', '#7B61FF'],
  '빈·오류 상태': ['#10B981', '#3D8BFF'],
  '위젯·차트': ['#EAB308', '#FF6B8B'],
  '공간·일정·디자인 도구': ['#C16235', '#3D8BFF'],
  '문서·데이터 편집': ['#3D8BFF', '#22C3A6'],
  '분석·데이터': ['#EAB308', '#FF6B8B'],
  '작업·시스템': ['#6366F1', '#7B61FF'],
};
const ALIAS = { '메뉴·내비': '메뉴·탭', '탭': '메뉴·탭' };
const SHAPES = ['square', 'tall'];
const EXPECTED = 200;

const errors = [];
const warns = [];
const coreSrc = readFileSync(join(galDir, 'i18n-core.js'), 'utf8');
const uxLocalize = new Function(coreSrc + '\nreturn uxLocalize;')();
const HANGUL = /[\u3131-\u318E\uAC00-\uD7A3]/;
// 자동 재생 시연 단계: [동작, 대상 선택자, 순번, ...값]
const DEMO_OPS = { wait: 1, tap: 1, hold: 1, hover: 1, leave: 1, glide: 1, drag: 1, key: 1, type: 1, erase: 1, set: 1, js: 1, reset: 1, scroll: 1 };
const STRICT = !process.env.UX_PARTIAL;
const files = readdirSync(elDir).filter((f) => /^\d{3}-[a-z0-9-]+\.html$/.test(f)).sort();
const items = [];
const seenSlug = new Set();

for (const file of files) {
  const id = file.slice(0, 3);
  const slug = file.slice(4, -5);
  let src = readFileSync(join(elDir, file), 'utf8').replace(/\r\n/g, '\n');

  const metaMatch = src.match(/^\s*<!--\s*@meta\s*([\s\S]*?)-->/);
  if (!metaMatch) { errors.push(`${file}: @meta 주석 없음`); continue; }
  let meta;
  try { meta = JSON.parse(metaMatch[1]); } catch (e) { errors.push(`${file}: @meta JSON 오류 ${e.message}`); continue; }
  src = src.slice(metaMatch[0].length).trim();
  let demo = [];
  const demoMatch = src.match(/^<!--\s*@demo\s*([\s\S]*?)-->/);
  if (demoMatch) {
    try { demo = JSON.parse(demoMatch[1]); } catch (e) { errors.push(`${file}: @demo JSON 오류 ${e.message}`); }
    src = src.slice(demoMatch[0].length).trim();
  }
  let en = null;
  const enMatch = src.match(/^<!--\s*@en\s*([\s\S]*?)-->/);
  if (enMatch) {
    try { en = JSON.parse(enMatch[1]); } catch (e) { errors.push(`${file}: @en JSON 오류 ${e.message}`); }
    src = src.slice(enMatch[0].length).trim();
  }
  if (!Array.isArray(demo)) { errors.push(`${file}: @demo는 배열이어야 합니다`); demo = []; }
  demo.forEach((st, k) => {
    if (!Array.isArray(st) || !DEMO_OPS[st[0]]) errors.push(`${file}: @demo ${k}번째 단계 "${JSON.stringify(st).slice(0, 40)}" 알 수 없음`);
  });
  if (!demo.length) (STRICT ? errors : warns).push(`${file}: @demo 없음`);

  const category = ALIAS[meta.category] || meta.category;
  if (!meta.title || !meta.summary) errors.push(`${file}: title/summary 필요`);
  if (!CATEGORIES[category]) errors.push(`${file}: 알 수 없는 분류 "${meta.category}"`);
  const shape = meta.shape || 'square';
  if (!SHAPES.includes(shape)) errors.push(`${file}: shape는 square 또는 tall`);
  if (seenSlug.has(slug)) errors.push(`${file}: slug 중복`);
  seenSlug.add(slug);

  const scriptMatch = src.match(/<script>([\s\S]*?)<\/script>\s*$/);
  if (!scriptMatch) { errors.push(`${file}: 끝에 <script>가 필요합니다`); continue; }
  const js = scriptMatch[1].trim();
  const html = src.slice(0, scriptMatch.index).trim();

  if ((src.match(/<script[\s>]/g) || []).length !== 1) errors.push(`${file}: <script>은 하나여야 합니다`);
  // 루트는 class="ux uNNN" 으로 시작하며, 상태 클래스가 뒤에 붙을 수 있습니다
  if (!new RegExp(`class="ux u${id}[" ]`).test(html)) errors.push(`${file}: 루트 class="ux u${id}" 누락`);
  if (!html.includes('<style>')) errors.push(`${file}: <style> 누락`);
  if (!js.includes('document.currentScript.previousElementSibling')) errors.push(`${file}: 루트 찾기(currentScript)가 필요합니다`);
  // 요소 CSS가 다른 요소에 새지 않도록 선택자 접두사를 확인합니다
  const css = (html.match(/<style>([\s\S]*?)<\/style>/) || [, ''])[1];
  const bad = css.replace(/@keyframes[^{]+\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .split('}').map((r) => r.split('{')[0].trim()).filter(Boolean)
    .filter((sel) => !sel.startsWith('@'))
    .flatMap((sel) => sel.split(','))
    .map((s) => s.trim())
    .filter((s) => s && !s.includes(`.u${id}`) && !/^(from|to|\d+%)$/.test(s));
  if (bad.length) errors.push(`${file}: 접두사 없는 선택자 ${bad.slice(0, 3).join(' | ')}`);

  // 영어판: 주석을 지우고 번역 목록을 적용한 결과에 한글이 남으면 안 됩니다
  if (!en) (STRICT ? errors : warns).push(`${file}: @en 없음`);
  else {
    const pairs = Array.isArray(en.map) ? en.map : [];
    if (!en.title || !en.summary) errors.push(`${file}: @en title/summary 필요`);
    pairs.forEach((p) => { if (!Array.isArray(p) || p.length !== 2 || typeof p[0] !== 'string' || typeof p[1] !== 'string') errors.push(`${file}: @en map 항목 형식 ${JSON.stringify(p).slice(0, 50)}`); });
    const eh = uxLocalize(html, 'html', pairs), ej = uxLocalize(js, 'js', pairs);
    const left = [];
    for (const [part, code] of [['html', eh], ['js', ej]]) {
      // keep: 영어판에도 그대로 두는 말(예: 언어 선택 목록의 '한국어'처럼 자기 언어로 쓰는 이름)
      const keep = Array.isArray(en.keep) ? en.keep : [];
      code.split('\n').forEach((line, n) => { const l2 = keep.reduce((acc, w) => acc.split(w).join(''), line); if (HANGUL.test(l2)) left.push(`${part}:${n + 1} ${line.trim().slice(0, 110)}`); });
    }
    if (left.length) errors.push(`${file}: 영어판에 한글이 남았습니다\n      ` + left.slice(0, 14).join('\n      ') + (left.length > 14 ? `\n      …외 ${left.length - 14}줄` : ''));
    const unused = pairs.filter((p) => !html.includes(p[0]) && !js.includes(p[0]));
    if (unused.length) warns.push(`${file}: 쓰이지 않는 번역 ${unused.map((p) => JSON.stringify(p[0])).slice(0, 4).join(', ')}`);
    for (const k of ['title', 'summary', 'hint']) if (en[k] && HANGUL.test(en[k])) errors.push(`${file}: @en ${k}에 한글`);
    demo.forEach((st) => st.forEach((v) => {
      if (typeof v === 'string' && HANGUL.test(v) && st[0] !== 'js') errors.push(`${file}: @demo 문자열에 한글이 있으면 {"ko","en"}로 나눠 주세요: ${v.slice(0, 30)}`);
    }));
  }

  const [h1, h2] = CATEGORIES[category] || ['#7B61FF', '#3D8BFF'];
  items.push({
    id, slug,
    title: meta.title,
    category,
    summary: meta.summary,
    hint: meta.hint || '',
    shape,
    // 폭이 컨테이너를 따르는 요소: 갤러리는 정해진 폭의 상자 안에 놓고, 크기가 바뀌면 배율을 다시 맞춥니다
    ...(meta.fluid ? { fluid: true } : {}),
    hue: meta.hue || h1,
    hue2: meta.hue2 || h2,
    tags: Array.isArray(meta.tags) ? meta.tags : [],
    html,
    js,
    demo,
    en: en ? { title: en.title, summary: en.summary, hint: en.hint || '', map: en.map || [], keep: Array.isArray(en.keep) ? en.keep : [] } : null,
  });
}

// UX_PARTIAL=1 이면 작성 중인 부분 빌드를 허용합니다. 최종 빌드에서는 반드시 200개여야 합니다.
if (!process.env.UX_PARTIAL && items.length !== EXPECTED) errors.push(`요소 ${items.length}개 (목표 ${EXPECTED})`);
if (warns.length) console.warn('참고:\n' + warns.map((w) => ' - ' + w).join('\n'));
if (errors.length) {
  console.error('빌드 중단:\n' + errors.map((e) => ' - ' + e).join('\n'));
  process.exit(1);
}

const tokens = readFileSync(join(here, 'tokens.css'), 'utf8');
const galleryHtml = readFileSync(join(galDir, 'index.html'), 'utf8');
const galleryCss = readFileSync(join(galDir, 'gallery.css'), 'utf8');
const galleryJs = readFileSync(join(galDir, 'gallery.js'), 'utf8').replace('/*@I18N_CORE@*/', () => coreSrc);

// JSON을 <script> 안에 넣을 때 </script> 종료 방지
const data = JSON.stringify({ tokens, items }).replace(/<\//g, '<\\/');

// 스크립트가 꺼져도 목록이 보이도록 타일의 제목 구조를 미리 HTML로 넣습니다. 스크립트가 켜지면 다시 그립니다
const escH = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const staticTiles = items.map((it) =>
  `<article class="g-tile" style="--h:${it.hue};--h2:${it.hue2}"><p class="g-cap"><b>${it.id}</b><span>${escH(it.title)}</span></p></article>`).join('');

const page = galleryHtml
  .replace('<!--@GRID_TILES@-->', () => staticTiles)
  .replace('/*@GALLERY_CSS@*/', () => galleryCss)
  .replace('/*@GALLERY_JS@*/', () => galleryJs)
  .replace('/*@TOKENS@*/', () => tokens)
  .replace('__UX_DATA__', () => data);

mkdirSync(outDir, { recursive: true });
writeFileSync(outFile, page);
const kb = (Buffer.byteLength(page) / 1024).toFixed(1);
console.log(`OK: 요소 ${items.length}개 → ${outFile} (${kb} KB)`);
