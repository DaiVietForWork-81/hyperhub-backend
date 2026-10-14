(function () {
  'use strict';

  // 미리보기, 복사되는 프롬프트, 다운로드 파일은 모두 같은 소스(item.html, item.js)에서 만듭니다.
  // 영어판은 같은 소스에 요소별 번역 목록을 적용해 만들므로 세 경로가 언제나 같은 코드를 씁니다.
  var DATA = JSON.parse(document.getElementById('ux-data').textContent);
  var ITEMS = DATA.items;
  var TOKENS = DATA.tokens.trim();
  // 영어판 코드에는 한국어 주석을 뺀 토큰을 넣습니다
  var TOKENS_EN = uxLocalize(TOKENS, 'html', []).replace(/^\s*\n/, '');
  function tokens() { return lang === 'en' ? TOKENS_EN : TOKENS; }
  var THEME_KEY = 'ux-gallery-theme';
  var LANG_KEY = 'ux-gallery-lang';
  var AUTO_KEY = 'ux-gallery-auto';
  var root = document.documentElement;
  var body = document.body;
  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)');
  var mobileQ = window.matchMedia('(max-width: 760px)');
  var wideQ = window.matchMedia('(min-width: 1100px)');

  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var esc = function (s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };
  var store = {
    get: function (k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set: function (k, v) { try { localStorage.setItem(k, v); } catch (e) { /* 저장할 수 없는 환경에서도 동작합니다 */ } }
  };
  var ICON = {
    open: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 5h5v5M10 19H5v-5M19 5l-6 6M5 19l6-6"/></svg>',
    prompt: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 6h14M5 12h8M5 18h5"/><path d="M17.5 13.2l.9 2.2 2.2.9-2.2.9-.9 2.2-.9-2.2-2.2-.9 2.2-.9z"/></svg>',
    copy: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="8" y="8" width="12" height="12" rx="2.5"/><path d="M16 8V6.5A2.5 2.5 0 0 0 13.5 4h-7A2.5 2.5 0 0 0 4 6.5v7A2.5 2.5 0 0 0 6.5 16H8"/></svg>',
    code: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v11M7 10.5l5 5 5-5M5 19.5h14"/></svg>',
    check: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5l4.2 4.2L19 7"/></svg>',
    hand: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 11V5.5a1.5 1.5 0 0 1 3 0V10m0-1.5a1.5 1.5 0 0 1 3 0V11m0-1a1.5 1.5 0 0 1 3 0v4.5A5.5 5.5 0 0 1 12.5 20h-1a5 5 0 0 1-4-2l-2.6-3.6a1.4 1.4 0 0 1 2.2-1.7L9 14"/></svg>'
  };
  // 창이 열려 있는 동안 뒤쪽 움직임을 멈추는 표시입니다(:has 선택자는 요소를 붙일 때마다 다시 검사돼 무거워서 클래스로 둡니다)
  function markDialogs() { body.classList.toggle('has-dlg', !!$('dialog[open]')); }
  function openDialog(d) { if (d.showModal) { if (!d.open) d.showModal(); } else d.setAttribute('open', ''); markDialogs(); syncAll(); }
  function closeDialog(d) { if (d.close) d.close(); else d.removeAttribute('open'); markDialogs(); syncAll(); }

  /* ---------- 언어: 저장한 값 → 한국 시간대나 한국어 브라우저면 한국어 → 그 밖에는 영어 ---------- */
  var CAT_EN = {
    '전체': 'All', '버튼': 'Buttons', '토글·선택': 'Toggles & Pickers', '입력·검색': 'Inputs & Search', '메뉴·탭': 'Menus & Tabs',
    '카드·콘텐츠': 'Cards & Content', '로그인·가입': 'Sign-in & Sign-up', '알림·피드백': 'Alerts & Feedback',
    '로딩·진행': 'Loading & Progress', '빈·오류 상태': 'Empty & Error States', '위젯·차트': 'Widgets & Charts',
    '공간·일정·디자인 도구': 'Layout, Schedule & Design', '문서·데이터 편집': 'Document & Data Editing',
    '분석·데이터': 'Analytics & Data', '작업·시스템': 'Workflow & Systems'
  };
  var T = {
    ko: {
      docTitle: 'Lucian UX/UI Prompt',
      docDesc: '바로 눌러 볼 수 있는 UX/UI 요소 200개. 다크·라이트 테마와 실제 코드, 적용 프롬프트를 함께 제공합니다.',
      skip: '요소 목록으로 건너뛰기',
      brand: 'Lucian UX/UI Prompt, 맨 위로',
      guideBtn: '적용 방법',
      langGroup: '언어',
      h1: 'Lucian UX/UI Prompt', w1: 'Lucian', w2: 'UX/UI', w3: 'Prompt',
      intro: '버튼과 차트부터 디자인 도구, 문서 편집, 데이터 분석, 업무 화면까지 지금 바로 눌러 볼 수 있는 인터페이스 200개. 화면에 보이면 스스로 움직이고, 직접 누르면 바로 써 볼 수 있어요. 마음에 들면 프롬프트나 코드로 그대로 가져가세요.',
      count: function (n) { return '<b id="count">' + n + '</b>개'; },
      metaTheme: '다크 · 라이트', metaCode: '코드 포함',
      cats: '분류',
      searchOpen: '검색 열기', searchPh: '버튼, 차트, 로그인…', searchLabel: '요소 검색',
      reelBtn: '릴스로 크게 넘겨 보기', reelLabel: '릴스',
      toDark: '다크 테마로 전환', toLight: '라이트 테마로 전환',
      autoOn: '자동 재생 켜짐. 누르면 멈춥니다', autoOff: '자동 재생 꺼짐. 누르면 다시 재생합니다', autoText: '자동 재생',
      grid: 'UI 요소',
      emptyT: '맞는 요소가 없어요', emptyS: '다른 단어로 찾거나 분류를 ‘전체’로 바꿔 보세요.', emptyB: '검색 지우기',
      reel: 'UI 요소 릴스', hud: '릴스 도구', back: '그리드로 돌아가기', backText: '그리드',
      close: '닫기', seg: '보기 전환', tabPrompt: '적용 프롬프트', tabCode: '코드',
      dl: '코드 파일 받기', copyPrompt: '프롬프트 복사', copyCode: '코드 복사',
      hintPrompt: function (n) { return '프롬프트 ' + n + '자 · 실행 코드 전체 포함'; },
      hintCode: function (n) { return '코드 ' + n + '자 · 실행 코드 전체 포함'; },
      areaPrompt: '적용 프롬프트', areaCode: '요소 코드',
      guideKick: '적용 방법', guideTitle: '이렇게 가져가세요',
      skillBtn: '에이전트 스킬', skillBtnLong: '에이전트 스킬로 쓰기 →', skillTitle: 'AI 에이전트에게 맡기기',
      skillLead: 'lucian-uxui 스킬을 설치하면 Claude Code, Codex 같은 코딩 에이전트가 이 갤러리에서 맞는 요소를 찾아 프로젝트에 옮겨 넣습니다.',
      skillAny: '모든 에이전트', skillPlugin: 'Claude Code 플러그인', copyCmd: '명령 복사', tCmdCopied: '복사했어요',
      useAsk: '말로 부탁하기', useAskEx: '“lucian-uxui 스킬로 요금제 토글이랑 FAQ 넣어줘”',
      usePick: '번호로 고르기', usePickEx: '“lucian-uxui 스킬로 056번 요소 넣어줘”',
      useCall: '바로 부르기', useCallEx: 'Claude Code <code>/lucian-uxui</code> (플러그인은 <code>/lucian-uxui:lucian-uxui</code>) · Codex <code>$lucian-uxui</code>',
      skillMore: '자세히 보기', skillLine: '에이전트 스킬로 부르기', skillHow: '설치 방법',
      skillAskId: function (id) { return 'lucian-uxui 스킬로 ' + id + '번 요소 넣어줘'; },
      guideSteps: [
        '<b>보고, 직접 눌러 보세요.</b> 요소는 화면에 보이면 스스로 조작 시연을 반복합니다. 요소를 직접 누르거나 키보드로 들어가면 시연이 멈추고, 손을 떼고 잠시 지나면 처음부터 다시 시작합니다.',
        '<b>프롬프트 복사</b>에는 요소의 실행 코드 전체와 적용 지침이 들어 있습니다. 프로젝트의 AI 도구에 붙여넣고 삽입 위치만 채우면 됩니다.',
        '<b>코드 파일 받기</b>는 같은 요소를 단독 HTML로 저장합니다. 라이트·다크 토큰이 함께 들어 있어 바로 열어 볼 수 있습니다.',
        '언어·테마·자동 재생은 위쪽 버튼에서 바꿀 수 있고, 고른 값은 다음 방문에도 유지됩니다.'
      ],
      guideNote: '개발 메모 · 요소마다 <code>.ux</code>와 <code>.uNNN</code> 접두사 안에서만 스타일과 스크립트가 동작합니다. 색은 <code>--ux-*</code> 토큰을 쓰므로 프로젝트 테마 변수에 연결하면 됩니다.',
      open: function (t) { return t + ' 크게 보기'; },
      railPrompt: '프롬프트', railCopy: '복사', railCode: '코드',
      tPromptCopied: '프롬프트를 복사했어요', tCodeCopied: '코드를 복사했어요', tSelect: '글을 선택해 두었어요. ⌘C로 복사하세요',
      tSaved: '코드 파일을 저장했어요', tCopyIn: '프롬프트 창에서 복사해 주세요',
      themeBtn: '테마 전환', num: 'ko-KR'
    },
    en: {
      docTitle: 'Lucian UX/UI Prompt',
      docDesc: '200 UX/UI elements you can try right away — with dark and light themes, working code and a ready-to-use prompt.',
      skip: 'Skip to the elements',
      brand: 'Lucian UX/UI Prompt, back to top',
      guideBtn: 'How to use',
      langGroup: 'Language',
      h1: 'Lucian UX/UI Prompt', w1: 'Lucian', w2: 'UX/UI', w3: 'Prompt',
      intro: 'From buttons and charts to design tools, document editors, analytics and workflow screens — 200 interfaces you can try right now. Each one plays itself when it scrolls into view, and you can take over with a tap. Take the ones you like as a prompt or as code.',
      count: function (n) { return '<b id="count">' + n + '</b> elements'; },
      metaTheme: 'Dark · Light', metaCode: 'Code included',
      cats: 'Categories',
      searchOpen: 'Open search', searchPh: 'Button, chart, login…', searchLabel: 'Search elements',
      reelBtn: 'Browse full screen in Reels', reelLabel: 'Reels',
      toDark: 'Switch to dark theme', toLight: 'Switch to light theme',
      autoOn: 'Autoplay is on. Press to pause', autoOff: 'Autoplay is off. Press to play', autoText: 'Autoplay',
      grid: 'UI elements',
      emptyT: 'No matching elements', emptyS: 'Try another word, or switch the category to “All”.', emptyB: 'Clear search',
      reel: 'UI element reels', hud: 'Reel controls', back: 'Back to the grid', backText: 'Grid',
      close: 'Close', seg: 'Switch view', tabPrompt: 'Prompt', tabCode: 'Code',
      dl: 'Download code', copyPrompt: 'Copy prompt', copyCode: 'Copy code',
      hintPrompt: function (n) { return 'Prompt · ' + n + ' characters · includes the full working code'; },
      hintCode: function (n) { return 'Code · ' + n + ' characters · the full working element'; },
      areaPrompt: 'Prompt', areaCode: 'Element code',
      guideKick: 'How to use', guideTitle: 'Bring it into your project',
      skillBtn: 'Agent skill', skillBtnLong: 'Use it from an AI agent →', skillTitle: 'Let an AI agent do it',
      skillLead: 'Install the lucian-uxui skill and coding agents like Claude Code and Codex find the right elements in this gallery and port them into your project.',
      skillAny: 'Any agent', skillPlugin: 'Claude Code plugin', copyCmd: 'Copy command', tCmdCopied: 'Copied',
      useAsk: 'Ask in words', useAskEx: '“Add a pricing toggle and an FAQ with the lucian-uxui skill.”',
      usePick: 'Pick by number', usePickEx: '“Use the lucian-uxui skill to add element #056.”',
      useCall: 'Call it directly', useCallEx: 'Claude Code <code>/lucian-uxui</code> (as a plugin, <code>/lucian-uxui:lucian-uxui</code>) · Codex <code>$lucian-uxui</code>',
      skillMore: 'Read more', skillLine: 'Call it from an agent', skillHow: 'How to install',
      skillAskId: function (id) { return 'Use the lucian-uxui skill to add element #' + id; },
      guideSteps: [
        '<b>Watch, then try it.</b> Each element plays a short demo on a loop while it is on screen. Tap it or tab into it and the demo stops so you can use it yourself; leave it for a moment and it starts over.',
        '<b>Copy prompt</b> gives you the element’s full working code plus instructions. Paste it into your project’s AI tool and fill in where it should go.',
        '<b>Download code</b> saves the same element as a standalone HTML file, with light and dark tokens included, so it opens as is.',
        'Language, theme and autoplay can be changed with the buttons at the top, and your choices are remembered next time.'
      ],
      guideNote: 'Dev note · Each element keeps its styles and scripts inside the <code>.ux</code> and <code>.uNNN</code> prefixes. Colors use <code>--ux-*</code> tokens, so you can map them to your project’s theme variables.',
      open: function (t) { return 'Open ' + t; },
      railPrompt: 'Prompt', railCopy: 'Copy', railCode: 'Code',
      tPromptCopied: 'Prompt copied', tCodeCopied: 'Code copied', tSelect: 'Text selected — press ⌘C to copy',
      tSaved: 'Code file saved', tCopyIn: 'Copy it from the prompt window',
      themeBtn: 'Switch theme', num: 'en-US'
    }
  };
  var lang = root.getAttribute('lang') === 'en' ? 'en' : 'ko';
  var t = function (k) { return T[lang][k]; };
  var catLabel = function (c) { return lang === 'en' ? (CAT_EN[c] || c) : c; };
  /*@I18N_CORE@*/
  // 현재 언어의 제목·설명·코드. 영어 코드는 처음 쓸 때 한 번 만들어 둡니다
  function loc(it) {
    if (lang !== 'en' || !it.en) return { title: it.title, summary: it.summary, hint: it.hint, category: it.category, html: it.html, js: it.js };
    if (!it._en) it._en = { html: uxLocalize(it.html, 'html', it.en.map), js: uxLocalize(it.js, 'js', it.en.map) };
    return { title: it.en.title, summary: it.en.summary, hint: it.en.hint, category: catLabel(it.category), html: it._en.html, js: it._en.js };
  }

  /* ---------- 테마 ---------- */
  function isDark() {
    var a = root.getAttribute('data-theme');
    if (a) return a === 'dark';
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  }
  function syncTheme() {
    var dark = isDark();
    var b = $('#theme');
    b.classList.toggle('is-dark', dark);
    b.setAttribute('aria-label', dark ? t('toLight') : t('toDark'));
    $('.g-hud-theme').setAttribute('aria-label', dark ? t('toLight') : t('toDark'));
  }
  // 누른 버튼 자리에서 원이 퍼지며 테마가 바뀝니다. 요소를 다시 만들지 않으므로 입력값과 진행 상태가 유지됩니다
  function toggleTheme(fromEl) {
    var next = isDark() ? 'light' : 'dark';
    var apply = function () { root.setAttribute('data-theme', next); syncTheme(); };
    store.set(THEME_KEY, next);
    if (!document.startViewTransition || reduce.matches) { apply(); return; }
    var r = fromEl ? fromEl.getBoundingClientRect() : { left: innerWidth / 2, top: 0, width: 0, height: 0 };
    var x = r.left + r.width / 2, y = r.top + r.height / 2;
    var end = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y));
    var tr = document.startViewTransition(apply);
    tr.ready.then(function () {
      root.animate({ clipPath: ['circle(0px at ' + x + 'px ' + y + 'px)', 'circle(' + end + 'px at ' + x + 'px ' + y + 'px)'] },
        { duration: 650, easing: 'cubic-bezier(.2,.8,.2,1)', pseudoElement: '::view-transition-new(root)' });
    }).catch(function () { /* 전환을 건너뛰어도 테마는 이미 적용됐습니다 */ });
  }
  $('#theme').addEventListener('click', function (e) { toggleTheme(e.currentTarget); });
  var schemeQ = window.matchMedia('(prefers-color-scheme: dark)');
  var onScheme = function () { if (!root.getAttribute('data-theme')) syncTheme(); };
  if (schemeQ.addEventListener) schemeQ.addEventListener('change', onScheme); else if (schemeQ.addListener) schemeQ.addListener(onScheme);

  /* ---------- 요소 마운트와 배율 맞춤 ---------- */
  // 요소 HTML을 넣고 스크립트를 새로 만들어 붙입니다. 스크립트 바로 앞 형제가 요소의 루트입니다
  function mountInto(fit, it) {
    var c = loc(it);
    fit.innerHTML = c.html;
    var s = document.createElement('script');
    s.textContent = c.js;
    fit.appendChild(s);
  }
  function unmount(fit) { dropPlayer(fit); fit.innerHTML = ''; fit.removeAttribute('data-k'); }
  // 무대 안쪽 여백을 두고 요소를 배율로 맞춥니다. 요소 루트는 모든 상태에서 크기가 같도록 만들어져 있습니다
  // 폭이 컨테이너를 따르는 요소(is-fluid)는 펼치거나 줄을 더하면 높이가 바뀝니다. 그때마다 배율을 다시 맞춥니다
  var refit = window.ResizeObserver ? new ResizeObserver(function (entries) {
    entries.forEach(function (en) { var f = en.target; if (f._fa && f.isConnected) fitTo(f._fa[0], f, f._fa[1], f._fa[2]); });
  }) : null;
  function fitTo(stage, fit, maxK, padRatio) {
    if (refit && fit.classList.contains('is-fluid')) {
      if (!fit._fa) refit.observe(fit);
      fit._fa = [stage, maxK, padRatio];
    }
    var w = fit.offsetWidth, h = fit.offsetHeight;
    if (!w || !h) return;
    var sw = stage.clientWidth, sh = stage.clientHeight;
    var pad = Math.min(sw, sh) * (padRatio == null ? 0.09 : padRatio);
    var k = Math.min(maxK, (sw - pad * 2) / w, (sh - pad * 2) / h);
    k = Math.max(0.2, k);
    fit.dataset.k = k.toFixed(3);
    fit.style.transform = 'translate(-50%,-50%) scale(' + k.toFixed(4) + ')';
  }
  var fitTile = function (stage, fit) { fitTo(stage, fit, 1.3); };
  var fitSlide = function (stage, fit) { fitTo(stage, fit, mobileQ.matches ? 1.25 : 1.7, 0.04); };

  // 미리보기 안에서는 링크 이동과 폼 전송이 갤러리 주소를 바꾸지 않게 막고, 시연용 가짜 이벤트가 갤러리로 새지 않게 합니다
  function guardFit(fit) {
    if (fit._guard) return;
    fit._guard = true;
    fit.addEventListener('click', function (e) { var a = e.target.closest && e.target.closest('a[href]'); if (a) e.preventDefault(); });
    fit.addEventListener('submit', function (e) { e.preventDefault(); });
    ['pointerdown', 'pointerup', 'pointermove', 'pointerover', 'pointerout', 'pointercancel', 'mousedown', 'mouseup', 'click', 'dblclick', 'contextmenu', 'keydown', 'keyup', 'input', 'change', 'wheel'].forEach(function (type) {
      fit.addEventListener(type, function (e) { if (!e.isTrusted) e.stopPropagation(); });
    });
  }

  /* ---------- 자동 재생: 화면에 보이는 요소가 스스로 조작 시연을 반복합니다 ---------- */
  // 켜고 끄기는 저장됩니다. 저장한 값이 없으면 동작 줄이기 설정을 따릅니다
  var autoOn = (function () { var s = store.get(AUTO_KEY); return s === 'on' ? true : s === 'off' ? false : !reduce.matches; })();
  var players = [];
  var PID = 41;
  // 시연용 포인터는 실제 포인터가 아니어서 setPointerCapture가 예외를 던집니다. 미리보기에서만 조용히 넘깁니다
  ['setPointerCapture', 'releasePointerCapture'].forEach(function (m) {
    var orig = Element.prototype[m];
    if (!orig) return;
    Element.prototype[m] = function (id) { try { return orig.call(this, id); } catch (e) { return undefined; } };
  });
  var origHas = Element.prototype.hasPointerCapture;
  if (origHas) Element.prototype.hasPointerCapture = function (id) { return id === PID ? !!(this._demoCap) : origHas.call(this, id); };
  // 시연 중인 요소는 초점을 가져가지 않습니다. 사용자가 다른 곳에서 입력하던 흐름과 단축키를 지킵니다
  var nativeFocus = HTMLElement.prototype.focus;
  HTMLElement.prototype.focus = function (o) {
    var f = this.closest && this.closest('.g-fit');
    if (f && f._pl && f._pl.on) return undefined;
    return nativeFocus.call(this, o);
  };
  // select()도 초점을 옮기므로, 시연 중에는 초점 없이 글자만 선택합니다
  [HTMLInputElement, HTMLTextAreaElement].forEach(function (C) {
    var nativeSelect = C.prototype.select;
    C.prototype.select = function () {
      var f = this.closest && this.closest('.g-fit');
      if (f && f._pl && f._pl.on) { try { this.setSelectionRange(0, this.value.length); } catch (e) { /* 선택을 못 하는 입력 종류 */ } return undefined; }
      return nativeSelect.call(this);
    };
  });

  function hostOf(fit) { return fit.closest('.g-tile, .g-slide'); }
  // 가짜 포인터로는 CSS :hover, :active가 켜지지 않습니다. 미리보기의 스타일시트에만 같은 규칙을 클래스판으로 하나씩 더해 둡니다
  // (원본 코드는 그대로이므로 복사·다운로드 결과에는 영향이 없습니다)
  function hoverShim(fit) {
    var st = fit.querySelector('style');
    if (!st || !st.sheet || st._shim) return;
    st._shim = true;
    var walk = function (list) {
      for (var i = list.length - 1; i >= 0; i--) {
        var r = list[i];
        if (r.cssRules && !r.selectorText) { walk(r.cssRules); continue; }
        var sel = r.selectorText;
        if (!sel || !/:(hover|active)/.test(sel) || /:not\([^)]*:(hover|active)/.test(sel)) continue;
        var alt = sel.replace(/:hover/g, '.g-hov').replace(/:active/g, '.g-act');
        try { (r.parentRule || st.sheet).insertRule(alt + '{' + r.style.cssText + '}', i + 1); } catch (e) { /* 규칙을 못 넣어도 시연은 계속됩니다 */ }
      }
    };
    try { walk(st.sheet.cssRules); } catch (e) { /* 무시 */ }
  }
  function attachPlayer(fit, idx, kind) {
    dropPlayer(fit);
    var it = ITEMS[idx];
    var P = { fit: fit, stage: fit.parentNode, host: hostOf(fit), idx: idx, kind: kind, steps: it.demo || [], on: false, gen: 0, dirty: false,
      user: false, lastUser: 0, mouseIn: false, vis: false, timers: [], hp: [], ht: null, down: null, muted: [], ghost: null, i: 0 };
    P.root = fit.querySelector(':scope > .ux');
    fit._pl = P;
    guardFit(fit);
    hoverShim(fit);
    var g = P.host.querySelector(':scope > .g-ghost');
    if (!g) { g = document.createElement('span'); g.className = 'g-ghost'; g.setAttribute('aria-hidden', 'true'); P.host.appendChild(g); }
    P.ghost = g;
    players.push(P);
    if (kind === 'tile') playIO.observe(P.stage);
    return P;
  }
  function dropPlayer(fit) {
    var P = fit && fit._pl;
    if (!P) return;
    stopPlayer(P);
    if (P.kind === 'tile') playIO.unobserve(P.stage);
    var i = players.indexOf(P);
    if (i >= 0) players.splice(i, 1);
    fit._pl = null;
  }
  function shouldRun(P) {
    return autoOn && P.vis && !P.user && P.steps.length > 0 && !document.hidden && !$('dialog[open]') &&
      P.fit.isConnected && (P.kind === 'tile' ? body.dataset.view === 'grid' : body.dataset.view === 'reel');
  }
  function syncPlayer(P) {
    var go = shouldRun(P);
    if (go && !P.on) startPlayer(P);
    else if (!go && P.on) stopPlayer(P);
  }
  function syncAll() { players.slice().forEach(syncPlayer); }

  function later(P, gen, ms, fn) {
    var id = setTimeout(function () {
      var k = P.timers.indexOf(id);
      if (k >= 0) P.timers.splice(k, 1);
      if (P.gen === gen && P.on) fn();
    }, ms);
    P.timers.push(id);
  }
  // 시연 중에는 요소의 안내 영역(aria-live)이 반복해서 읽히지 않게 잠시 끕니다
  function mute(P) {
    if (!P.root) return;
    $$('[aria-live], [role="status"], [role="alert"], [role="log"], [role="timer"]', P.root).forEach(function (el) {
      if (el.hasAttribute('data-g-live')) return;
      el.setAttribute('data-g-live', el.getAttribute('aria-live') || '');
      el.setAttribute('aria-live', 'off');
      P.muted.push(el);
    });
  }
  function unmute(P) {
    P.muted.forEach(function (el) {
      var v = el.getAttribute('data-g-live');
      el.removeAttribute('data-g-live');
      if (v) el.setAttribute('aria-live', v); else el.removeAttribute('aria-live');
    });
    P.muted = [];
  }
  function startPlayer(P) {
    P.on = true;
    P.gen += 1;
    var gen = P.gen;
    mute(P);
    if (P.dirty) softReset(P, gen, function () { P.i = 0; runStep(P, gen); });
    else { P.i = 0; runStep(P, gen); }
  }
  function stopPlayer(P) {
    if (!P.on && !P.timers.length) return;
    P.on = false;
    P.gen += 1;
    P.timers.forEach(clearTimeout);
    P.timers = [];
    if (P.raf) cancelAnimationFrame(P.raf);
    // 누르고 있던 시연 포인터는 놓고, 올려 둔 포인터는 빼서 요소가 눌린 채로 남지 않게 합니다
    if (P.down) { var d = P.down; P.down = null; d.el._demoCap = false; fire(P, d.el, 'pointerup', d.x, d.y, true, { button: 0, buttons: 0 }); }
    hoverTo(P, null, 0, 0);
    ghost(P, 'off');
    unmute(P);
  }
  // 처음 상태로 되돌립니다. 안 보일 때는 바로, 보일 때는 잠깐 흐려졌다가 새로 그립니다
  // 화면에 보이지 않을 때는 흐려지는 효과 없이 바로 처음 상태로 되돌려 둡니다. 다시 보일 때 깜빡이지 않습니다
  function quietReset(P) {
    var fit = P.fit;
    if (!fit.isConnected || P.on || fit._pl !== P) return;
    P.gen += 1;
    P.timers.forEach(clearTimeout); P.timers = [];
    fit.innerHTML = '';
    mountInto(fit, ITEMS[P.idx]);
    P.root = fit.querySelector(':scope > .ux');
    P.hp = []; P.ht = null; P.muted = []; P.user = false; P.i = 0;
    hoverShim(fit);
    (P.kind === 'tile' ? fitTile : fitSlide)(P.stage, fit);
    fit.style.transition = ''; fit.style.opacity = '';
    P.dirty = false;
  }
  function softReset(P, gen, done) {
    var fit = P.fit;
    var swap = function () {
      if (P.gen !== gen || !fit.isConnected) return;
      fit.innerHTML = '';
      mountInto(fit, ITEMS[P.idx]);
      P.root = fit.querySelector(':scope > .ux');
      P.hp = []; P.ht = null; P.muted = [];
      hoverShim(fit);
      (P.kind === 'tile' ? fitTile : fitSlide)(P.stage, fit);
      mute(P);
      P.dirty = false;
      fit.style.opacity = '';
      later(P, gen, reduce.matches ? 0 : 380, done);
    };
    if (reduce.matches) { swap(); return; }
    fit.style.transition = 'opacity .28s ease';
    fit.style.opacity = '0';
    later(P, gen, 300, swap);
  }

  // 대상 찾기: 선택자와 순번. 화면에 그려지지 않은 대상은 건너뜁니다
  function target(P, sel, n) {
    if (!P.root) return null;
    if (sel === ':root') return P.root;
    var list;
    try { list = P.root.querySelectorAll(sel); } catch (e) { return null; }
    // 순번이 음수면 뒤에서부터 셉니다(-1은 마지막)
    var el = list[n < 0 ? list.length + n : n || 0];
    if (!el) return null;
    var r = el.getBoundingClientRect();
    return r.width || r.height ? el : null;
  }
  function pointIn(el, fx, fy) {
    var r = el.getBoundingClientRect();
    return { x: r.left + r.width * (fx == null ? 0.5 : fx), y: r.top + r.height * (fy == null ? 0.5 : fy) };
  }
  function fire(P, el, type, x, y, bubbles, extra) {
    var init = { bubbles: bubbles !== false, cancelable: true, composed: true, view: window, clientX: x, clientY: y, screenX: x, screenY: y, button: 0, buttons: P.down ? 1 : 0, detail: 1 };
    if (extra) for (var k in extra) init[k] = extra[k];
    P.actT = performance.now();
    var ev;
    if (type.indexOf('pointer') === 0) {
      init.pointerId = PID; init.pointerType = P.pt || 'mouse'; init.isPrimary = true; init.width = 1; init.height = 1;
      init.pressure = init.buttons ? 0.5 : 0;
      if (type === 'pointermove' && !extra) init.button = -1;
      ev = new PointerEvent(type, init);
    } else ev = new MouseEvent(type, init);
    try { el.dispatchEvent(ev); } catch (e) { /* 요소 처리기 오류는 요소 쪽에서 보고됩니다 */ }
  }
  // 실제 포인터처럼 들어가고 나오는 순서대로 enter/leave, over/out을 보냅니다
  // 맥 커서처럼 요소의 cursor 값에 따라 화살표·손가락·I자로 바꿉니다
  var TEXTY = /^(text|search|email|password|url|tel|number)$/;
  function curOf(el) {
    if (!el || el.nodeType !== 1) return 'arrow';
    var c = getComputedStyle(el).cursor;
    if (c === 'pointer') return 'hand';
    if (c === 'text' || c === 'vertical-text') return 'text';
    if (c !== 'auto') return 'arrow';
    if (el.isContentEditable || el.tagName === 'TEXTAREA' || (el.tagName === 'INPUT' && TEXTY.test(el.type))) return 'text';
    return el.closest('a[href]') ? 'hand' : 'arrow';
  }
  function setCur(P, kind) { if (P.ghost && P.ghost.getAttribute('data-cur') !== kind) P.ghost.setAttribute('data-cur', kind); }
  function hoverTo(P, el, x, y) {
    var np = [];
    for (var e = el; e && e !== P.fit; e = e.parentElement) np.push(e);
    var op = P.hp || [];
    if (P.ht && P.ht !== el && P.ht.isConnected) fire(P, P.ht, 'pointerout', x, y, true);
    op.forEach(function (o) { if (np.indexOf(o) < 0) { o.classList.remove('g-hov', 'g-act'); if (o.isConnected) fire(P, o, 'pointerleave', x, y, false); } });
    np.forEach(function (o) { o.classList.add('g-hov'); });
    if (el && P.ht !== el) fire(P, el, 'pointerover', x, y, true);
    np.slice().reverse().forEach(function (o) { if (op.indexOf(o) < 0) fire(P, o, 'pointerenter', x, y, false); });
    if (el) fire(P, el, 'pointermove', x, y, true);
    P.hp = np; P.ht = el;
    setCur(P, curOf(el));
  }
  // 시연 포인터: 화면 좌표를 타일(또는 릴스 화면) 안 좌표로 바꿔 그립니다
  function ghost(P, mode, x, y, ms) {
    var g = P.ghost;
    if (!g) return;
    clearTimeout(P.restT);
    if (mode === 'off') { g.classList.remove('is-on', 'is-down'); P.gpos = false; return; }
    // 누른 뒤에는 결과가 가려지지 않게 포인터가 그 자리에서 사라집니다. 다음 동작은 그 자리에서 다시 나타납니다
    if (mode === 'rest') { P.restT = setTimeout(function () { g.classList.remove('is-on', 'is-down'); }, 420); return; }
    if (x != null) {
      P.gpos = true;
      var hr = P.host.getBoundingClientRect();
      g.style.transitionDuration = (reduce.matches ? 0 : (ms == null ? 420 : ms)) + 'ms, 300ms, 160ms';
      g.style.setProperty('--gx', (x - hr.left).toFixed(1) + 'px');
      g.style.setProperty('--gy', (y - hr.top).toFixed(1) + 'px');
    }
    if (mode === 'on') g.classList.add('is-on');
    if (mode === 'down') { g.classList.add('is-on', 'is-down'); g.classList.remove('is-tap'); void g.offsetWidth; g.classList.add('is-tap'); }
    if (mode === 'up') g.classList.remove('is-down');
  }
  function glideTo(P, gen, p, ms, then) {
    setCur(P, 'arrow');
    if (!P.gpos) { var hr = P.host.getBoundingClientRect(); ghost(P, null, hr.left + hr.width * 0.78, hr.top + hr.height * 1.05, 0); }
    // 위치를 먼저 잡은 뒤 다음 프레임에 미끄러지게 합니다
    requestAnimationFrame(function () {
      if (P.gen !== gen) return;
      ghost(P, 'on', p.x, p.y, ms);
      later(P, gen, reduce.matches ? 30 : ms, then);
    });
  }
  function txt(v) { return v && typeof v === 'object' ? (v[lang] || v.ko || '') : String(v == null ? '' : v); }
  function setValue(el, v, type, data) {
    var proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    var d = Object.getOwnPropertyDescriptor(proto, 'value');
    if (d && d.set) d.set.call(el, v); else el.value = v;
    var ev;
    try { ev = new InputEvent('input', { bubbles: true, inputType: type, data: data == null ? null : data }); } catch (e) { ev = new Event('input', { bubbles: true }); }
    el.dispatchEvent(ev);
  }

  // 단계 하나를 실행하고, 끝나면 다음 단계로 넘어갑니다
  function runStep(P, gen) {
    if (P.gen !== gen || !P.on) return;
    if (!P.fit.isConnected) { stopPlayer(P); return; }
    if (P.i >= P.steps.length) {
      P.i = 0;
      later(P, gen, 900, function () { runStep(P, gen); });
      return;
    }
    var st = P.steps[P.i++];
    var op = st[0];
    var next = function (ms) { later(P, gen, ms || 0, function () { runStep(P, gen); }); };
    P.dirty = true;
    if (P.log) P.log.push(op + ' ' + (st[1] || ''));
    if (op === 'wait') { next(st[1]); return; }
    if (op === 'reset') { hoverTo(P, null, 0, 0); ghost(P, 'off'); softReset(P, gen, function () { next(0); }); return; }
    if (op === 'leave') { hoverTo(P, null, 0, 0); ghost(P, 'off'); next(st[1] || 200); return; }
    if (op === 'js') {
      try { new Function('root', st[1])(P.root); } catch (e) { if (P.miss) P.miss.push('js ' + e.message); }
      next(st[2] || 0); return;
    }
    var el = target(P, st[1], st[2]);
    if (!el) { if (P.miss) P.miss.push(op + ' ' + st[1] + ' #' + (st[2] || 0)); next(60); return; }
    var o = (op === 'tap' || op === 'hold' || op === 'hover') ? (st[op === 'hold' ? 4 : 3] || {}) : {};
    P.pt = o.pt || 'mouse';

    if (op === 'tap' || op === 'hold' || op === 'hover') {
      var p = pointIn(el, o.fx, o.fy);
      glideTo(P, gen, p, o.glide == null ? 440 : o.glide, function () {
        if (!el.isConnected) { next(60); return; }
        p = pointIn(el, o.fx, o.fy);
        hoverTo(P, el, p.x, p.y);
        if (op === 'hover') { next(o.after == null ? 300 : o.after); return; }
        ghost(P, 'down', p.x, p.y, 0);
        P.down = { el: el, x: p.x, y: p.y };
        el._demoCap = true;
        P.hp.forEach(function (o) { o.classList.add('g-act'); });
        // {button:2}는 오른쪽 버튼: click 대신 contextmenu를 보냅니다
        var btn = o.button === 2 ? 2 : 0;
        fire(P, el, 'pointerdown', p.x, p.y, true, { button: btn, buttons: btn ? 2 : 1 });
        fire(P, el, 'mousedown', p.x, p.y, true, { button: btn, buttons: btn ? 2 : 1 });
        later(P, gen, op === 'hold' ? st[3] : 110, function () {
          P.down = null; el._demoCap = false;
          P.hp.forEach(function (o2) { o2.classList.remove('g-act'); });
          fire(P, el, 'pointerup', p.x, p.y, true, { button: btn, buttons: 0 });
          fire(P, el, 'mouseup', p.x, p.y, true, { button: btn, buttons: 0 });
          if (btn === 2) fire(P, el, 'contextmenu', p.x, p.y, true, { button: 2, buttons: 0 });
          else if (op === 'tap' || o.click) fire(P, el, 'click', p.x, p.y, true, { button: 0, buttons: 0 });
          ghost(P, 'up');
          ghost(P, 'rest');
          next(o.after == null ? 160 : o.after);
        });
      });
      return;
    }
    if (op === 'glide' || op === 'drag') {
      // [동작, 선택자, 순번, [x0,y0], [x1,y1], 시간(ms), {pt, frame, click}] : 좌표는 대상(또는 frame) 상자 안의 비율입니다
      var a = st[3] || [0.5, 0.5], b = st[4] || [0.5, 0.5], dur = st[5] || 900, oo = st[6] || {};
      P.pt = oo.pt || 'mouse';
      var fr = (oo.frame && target(P, oo.frame, 0)) || el;
      var p0 = pointIn(fr, a[0], a[1]);
      glideTo(P, gen, p0, 440, function () {
        if (!el.isConnected) { next(60); return; }
        var r = fr.getBoundingClientRect();
        var at = function (k) { return { x: r.left + r.width * (a[0] + (b[0] - a[0]) * k), y: r.top + r.height * (a[1] + (b[1] - a[1]) * k) }; };
        var s0 = at(0);
        hoverTo(P, el, s0.x, s0.y);
        if (op === 'drag') {
          ghost(P, 'down', s0.x, s0.y, 0);
          P.down = { el: el, x: s0.x, y: s0.y };
          el._demoCap = true;
          fire(P, el, 'pointerdown', s0.x, s0.y, true, { button: 0, buttons: 1 });
        }
        var t0 = performance.now();
        var tick = function (now) {
          if (P.gen !== gen || !P.on) return;
          var k = Math.min(1, (now - t0) / (reduce.matches ? 1 : dur));
          var e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
          var q = at(e);
          ghost(P, null, q.x, q.y, 0);
          if (P.down) { P.down.x = q.x; P.down.y = q.y; }
          fire(P, el, 'pointermove', q.x, q.y, true, { button: -1, buttons: op === 'drag' ? 1 : 0 });
          if (k < 1) { P.raf = requestAnimationFrame(tick); return; }
          if (op === 'drag') {
            P.down = null; el._demoCap = false;
            fire(P, el, 'pointerup', q.x, q.y, true, { button: 0, buttons: 0 });
            ghost(P, 'up');
            ghost(P, 'rest');
            if (oo.click) fire(P, el, 'click', q.x, q.y, true, { button: 0, buttons: 0 });
          }
          next(oo.after == null ? 200 : oo.after);
        };
        P.raf = requestAnimationFrame(tick);
      });
      return;
    }
    if (op === 'key') {
      // [key, 선택자, 순번, 키, 횟수, 간격, {shift,ctrl,meta}]
      var times = st[4] || 1, gap = st[5] || 260, mods = st[6] || {}, n = 0;
      var press = function () {
        var init = { key: st[3], code: st[3].length === 1 ? 'Key' + st[3].toUpperCase() : st[3], bubbles: true, cancelable: true, composed: true,
          shiftKey: !!mods.shift, ctrlKey: !!mods.ctrl, metaKey: !!mods.meta, altKey: !!mods.alt };
        try { el.dispatchEvent(new KeyboardEvent('keydown', init)); el.dispatchEvent(new KeyboardEvent('keyup', init)); } catch (e) { /* 무시 */ }
        n += 1;
        if (n < times) later(P, gen, gap, press); else next(gap);
      };
      press();
      return;
    }
    if (op === 'type') {
      // [type, 선택자, 순번, 글(문자열 또는 {ko,en}), 글자 간격]
      var s = txt(st[3]), per = st[4] || 85, k2 = 0;
      var one = function () {
        if (!el.isConnected) { next(60); return; }
        var ch = s.charAt(k2);
        setValue(el, el.value + ch, 'insertText', ch);
        k2 += 1;
        if (k2 < s.length) later(P, gen, per * (0.7 + Math.random() * 0.6), one); else next(per + 120);
      };
      one();
      return;
    }
    if (op === 'erase') {
      var cnt = st[3] === 'all' || st[3] == null ? el.value.length : st[3], per2 = st[4] || 45, k3 = 0;
      var del = function () {
        if (!el.isConnected || !el.value) { next(120); return; }
        setValue(el, el.value.slice(0, -1), 'deleteContentBackward', null);
        k3 += 1;
        if (k3 < cnt) later(P, gen, per2, del); else next(160);
      };
      del();
      return;
    }
    if (op === 'scroll') {
      // [scroll, 선택자, 순번, 이동량(px, 'end'), 시간] : 손가락으로 쓸어 올리듯 포인터를 움직이며 안쪽을 스크롤합니다
      var from = el.scrollTop, max = el.scrollHeight - el.clientHeight;
      var to = st[3] === 'end' ? max : st[3] === 'top' ? 0 : Math.max(0, Math.min(max, from + st[3]));
      var sd = st[4] || 900, pr = el.getBoundingClientRect(), up = to >= from;
      var g0 = { x: pr.left + pr.width * 0.62, y: pr.top + pr.height * (up ? 0.72 : 0.3) };
      glideTo(P, gen, g0, 420, function () {
        ghost(P, 'down', g0.x, g0.y, 0);
        var s0 = performance.now();
        var tk = function (now) {
          if (P.gen !== gen || !P.on) return;
          var k = Math.min(1, (now - s0) / (reduce.matches ? 1 : sd)), e = 1 - Math.pow(1 - k, 3);
          el.scrollTop = from + (to - from) * e;
          ghost(P, null, g0.x, g0.y + (up ? -1 : 1) * pr.height * 0.4 * e, 0);
          if (k < 1) { P.raf = requestAnimationFrame(tk); return; }
          ghost(P, 'up'); ghost(P, 'rest');
          next(200);
        };
        P.raf = requestAnimationFrame(tk);
      });
      return;
    }
    if (op === 'set') { setValue(el, txt(st[3]), 'insertReplacementText', txt(st[3])); next(st[4] || 120); return; }
    next(0);
  }

  // 사용자가 요소를 직접 만지면 시연을 멈추고, 손을 뗀 뒤 잠시 지나면 처음부터 다시 시연합니다
  function bindTakeover(host) {
    var P = function () { var f = $('.g-fit', host); return f && f._pl; };
    var touch = function (e) {
      if (!e.isTrusted) return;
      var p = P();
      if (!p || !e.target.closest || !e.target.closest('.ux')) return;
      // 시연의 클릭이 라벨을 거쳐 입력칸에 초점을 옮긴 경우는 사용자 조작이 아니므로 초점을 원래 자리로 돌려놓습니다
      // 라디오·체크박스 라벨을 누르면 브라우저가 보내는 input 이벤트도 시연이 만든 것입니다
      if (e.type === 'input' && p.on && performance.now() - (p.actT || 0) < 400) return;
      if (e.type === 'focusin' && p.on && performance.now() - (p.actT || 0) < 400) {
        var back = e.relatedTarget;
        if (back && document.contains(back) && !p.fit.contains(back)) nativeFocus.call(back, { preventScroll: true });
        else if (e.target.blur) e.target.blur();
        return;
      }
      p.lastUser = performance.now();
      if (!p.user) { p.user = true; stopPlayer(p); }
    };
    ['pointerdown', 'keydown', 'input', 'focusin'].forEach(function (type) { host.addEventListener(type, touch, true); });
    host.addEventListener('pointermove', function (e) { var p = P(); if (e.isTrusted && p && p.user) p.lastUser = performance.now(); }, true);
    host.addEventListener('pointerenter', function (e) { var p = P(); if (e.isTrusted && p && e.pointerType === 'mouse') p.mouseIn = true; });
    host.addEventListener('pointerleave', function (e) { var p = P(); if (e.isTrusted && p) { p.mouseIn = false; p.lastUser = Math.max(p.lastUser, performance.now() - 800); } });
  }
  setInterval(function () {
    var now = performance.now();
    players.forEach(function (P) {
      if (!P.user) return;
      var idle = P.kind === 'tile' ? 2600 : 6500;
      if (P.mouseIn || (document.activeElement && P.host.contains(document.activeElement) && document.activeElement !== P.host)) { P.lastUser = Math.max(P.lastUser, now - idle + 1200); return; }
      if (now - P.lastUser > idle) { P.user = false; P.dirty = true; syncPlayer(P); }
    });
  }, 500);
  document.addEventListener('visibilitychange', syncAll);

  // 타일은 60% 이상 보일 때 시연을 시작합니다(긴 타일은 화면 절반 이상)
  var playIO = new IntersectionObserver(function (entries) {
    entries.forEach(function (en) {
      var fit = en.target.firstElementChild, P = fit && fit._pl;
      if (!P) return;
      // 시작은 60% 이상 보일 때, 멈춤은 15% 아래로 가려질 때입니다(가장자리에서 멈췄다 섰다 하지 않게)
      var r = en.intersectionRatio, big = en.intersectionRect.height >= innerHeight * 0.5;
      P.vis = en.isIntersecting && (P.on ? (r >= 0.15 || big) : (r >= 0.6 || big));
      syncPlayer(P);
      // 거의 다 가려졌으면 그 자리에서 되돌려 둡니다. 다시 보일 때 깜빡이지 않습니다
      if (!P.vis && P.dirty && !P.on && r < 0.15) quietReset(P);
    });
  }, { threshold: [0, 0.15, 0.3, 0.6, 0.9] });

  function setAuto(v) {
    autoOn = !!v;
    store.set(AUTO_KEY, autoOn ? 'on' : 'off');
    syncAutoBtn();
    syncAll();
  }
  function syncAutoBtn() {
    $$('[data-auto]').forEach(function (b) {
      b.setAttribute('aria-pressed', String(autoOn));
      b.setAttribute('aria-label', autoOn ? t('autoOn') : t('autoOff'));
      b.title = t('autoText');
      b.classList.toggle('is-on', autoOn);
    });
  }
  $$('[data-auto]').forEach(function (b) { b.addEventListener('click', function () { setAuto(!autoOn); }); });

  /* ---------- 분류·검색 상태 ---------- */
  var CATS = [];
  ITEMS.forEach(function (it) { if (CATS.indexOf(it.category) < 0) CATS.push(it.category); });
  var activeCat = '전체';
  var query = '';
  // 한국어·영어 어느 쪽으로 찾아도 걸리도록 두 언어를 함께 넣어 둡니다
  var HAY = ITEMS.map(function (it) {
    var en = it.en || {};
    return [it.id, it.title, it.summary, it.category, CAT_EN[it.category] || '', it.tags.join(' '), en.title || '', en.summary || ''].join(' ').toLowerCase();
  });
  var visible = [];
  function computeVisible() {
    var words = query.split(/\s+/).filter(Boolean);
    visible = [];
    ITEMS.forEach(function (it, i) {
      var okC = activeCat === '전체' || it.category === activeCat;
      if (okC && words.every(function (w) { return HAY[i].indexOf(w) >= 0; })) visible.push(i);
    });
  }
  var isLooping = function () { return activeCat === '전체' && !query; };

  /* ---------- 타일 그리드: 3열(모바일 2열), 다섯 칸마다 긴 타일 하나 ---------- */
  var grid = $('#grid');
  var more = $('#more');
  var cols = mobileQ.matches ? 2 : 3;
  var orders = [];
  // 첫 바퀴는 원래 순서, 다음 바퀴부터는 고정된 난수로 섞어 같은 배열이 반복되지 않게 합니다
  function orderOf(loop) {
    if (!orders[loop]) {
      var arr = ITEMS.map(function (_, i) { return i; });
      if (loop > 0) {
        var seed = 7 + loop * 9973;
        for (var k = arr.length - 1; k > 0; k--) {
          seed = (Math.imul(seed, 1103515245) + 12345) & 0x7fffffff;
          var j = seed % (k + 1), tmp = arr[k]; arr[k] = arr[j]; arr[j] = tmp;
        }
      }
      orders[loop] = arr;
    }
    return orders[loop];
  }
  var stream, buffer, groupN, placed, done;
  function resetStream() { stream = { loop: 0, pos: 0 }; buffer = []; groupN = 0; placed = 0; done = false; }
  function nextIdx() {
    if (!isLooping()) return stream.pos < visible.length ? visible[stream.pos++] : -1;
    var seq = orderOf(stream.loop);
    if (stream.pos >= seq.length) { stream.loop += 1; stream.pos = 0; seq = orderOf(stream.loop); }
    return seq[stream.pos++];
  }
  function fillBuffer(n) {
    while (buffer.length < n) {
      var i = nextIdx();
      if (i < 0) break;
      buffer.push({ i: i, first: stream.loop === 0 });
    }
  }
  // 한 묶음은 두 줄입니다. 앞쪽에서 긴 요소를 찾으면 왼쪽·오른쪽 번갈아 두 줄 높이로 놓습니다
  function nextGroup() {
    var squares = (cols - 1) * 2;
    fillBuffer(squares + 1);
    if (!buffer.length) return null;
    var out = [];
    var ti = -1;
    for (var k = 0; k < Math.min(buffer.length, squares + 1); k++) {
      if (ITEMS[buffer[k].i].shape === 'tall') { ti = k; break; }
    }
    if (ti >= 0 && buffer.length > 1) {
      out.push({ e: buffer.splice(ti, 1)[0], tall: true, side: groupN % 2 ? 'last' : 'first' });
      for (k = 0; k < squares && buffer.length; k++) out.push({ e: buffer.shift() });
    } else {
      for (k = 0; k < cols * 2 && buffer.length; k++) out.push({ e: buffer.shift() });
    }
    groupN += 1;
    return out;
  }
  function tileText(el, it) {
    var c = loc(it);
    $('.g-cap span', el).textContent = c.title;
    $('.g-exp', el).setAttribute('aria-label', T[lang].open(c.title));
  }
  function makeTile(slot, delay) {
    var it = ITEMS[slot.e.i];
    var el = document.createElement('article');
    el.className = 'g-tile is-new' + (slot.tall ? ' is-tall at-' + slot.side : '');
    el.dataset.idx = String(slot.e.i);
    el.style.setProperty('--h', it.hue);
    el.style.setProperty('--h2', it.hue2);
    el.style.setProperty('--d', delay + 'ms');
    if (slot.e.first) el.id = 'tile-' + it.id;
    el.innerHTML =
      '<button class="g-open" type="button" tabindex="-1" aria-hidden="true" data-open="' + slot.e.i + '"></button>' +
      '<div class="g-stage"><div class="g-fit' + (it.fluid ? ' is-fluid' : '') + '"></div></div>' +
      '<p class="g-cap"><b>' + it.id + '</b><span></span></p>' +
      '<button class="g-exp" type="button" data-open="' + slot.e.i + '">' + ICON.open + '</button>';
    tileText(el, it);
    bindTakeover(el);
    el.addEventListener('animationend', function () { el.classList.remove('is-new'); }, { once: true });
    return el;
  }
  function mountTile(stage) {
    var fit = stage.firstElementChild, idx = +stage.parentNode.dataset.idx;
    mountInto(fit, ITEMS[idx]);
    fitTile(stage, fit);
    attachPlayer(fit, idx, 'tile');
  }
  // 화면 1.3배(모바일 1.1배) 앞에서 미리 붙여 두고, 2.2배(모바일 1.6배) 넘게 멀어져야 뗍니다(경계에서 붙였다 뗐다 하지 않게 간격을 둡니다).
  // 붙일 때는 화면에 가까운 타일부터 한 프레임에 8ms 안에서만 붙여 스크롤이 끊기지 않게 합니다
  var mountQ = [], qRaf = 0;
  function distOf(st) { var r = st.getBoundingClientRect(); return r.bottom < 0 ? -r.bottom : r.top > innerHeight ? r.top - innerHeight : 0; }
  function queueMount(st) {
    if (mountQ.indexOf(st) < 0) mountQ.push(st);
    if (!qRaf) qRaf = requestAnimationFrame(drainMount);
  }
  function drainMount() {
    qRaf = 0;
    if (body.dataset.view !== 'grid') { mountQ = []; return; }
    mountQ.sort(function (a, b) { return distOf(a) - distOf(b); });
    var t0 = performance.now(), n = 0;
    while (mountQ.length && (n === 0 || performance.now() - t0 < 8)) {
      var st = mountQ.shift();
      if (st.isConnected && st._near && !st.firstElementChild.firstChild) { mountTile(st); n += 1; }
    }
    if (mountQ.length) qRaf = requestAnimationFrame(drainMount);
  }
  var tileIO = new IntersectionObserver(function (entries) {
    entries.forEach(function (en) {
      var st = en.target;
      st._near = en.isIntersecting;
      if (en.isIntersecting && !st.firstElementChild.firstChild) queueMount(st);
    });
  }, { rootMargin: mobileQ.matches ? '110% 0px' : '130% 0px' });
  var keepIO = new IntersectionObserver(function (entries) {
    entries.forEach(function (en) {
      var fit = en.target.firstElementChild;
      if (!en.isIntersecting && fit.firstChild) unmount(fit);
    });
  }, { rootMargin: mobileQ.matches ? '160% 0px' : '220% 0px' });
  function watchStage(st) { tileIO.observe(st); keepIO.observe(st); }
  function unwatchAll() { tileIO.disconnect(); keepIO.disconnect(); mountQ = []; }
  var tileRO = new ResizeObserver(function (entries) {
    entries.forEach(function (en) {
      var fit = en.target.firstElementChild;
      if (fit.firstChild) fitTile(en.target, fit);
    });
  });
  function appendGroups(n) {
    var frag = document.createDocumentFragment();
    var d = 0;
    for (var g = 0; g < n && !done; g++) {
      var grp = nextGroup();
      if (!grp) { done = true; break; }
      grp.forEach(function (slot) {
        var tl = makeTile(slot, Math.min(d, 420));
        d += 45;
        frag.appendChild(tl);
        placed += 1;
      });
    }
    var fresh = $$('.g-tile', frag);
    $$('.g-stage', frag).forEach(function (st) { watchStage(st); tileRO.observe(st); });
    grid.appendChild(frag);
    // 화면 아래에서 미리 붙는 타일은 떠오르는 등장 효과 없이 바로 제자리에 둡니다(빠르게 내려와도 비어 보이지 않게)
    fresh.forEach(function (tl) { if (tl.getBoundingClientRect().top > innerHeight) tl.classList.remove('is-new'); });
  }
  function fillIfNeeded() {
    if (body.dataset.view !== 'grid') return;
    var guard = 0;
    while (!done && guard++ < 6 && more.getBoundingClientRect().top < innerHeight + 1400) appendGroups(2);
  }
  new IntersectionObserver(function (en) {
    if (en.some(function (e) { return e.isIntersecting; })) fillIfNeeded();
  }, { rootMargin: '1400px 0px' }).observe(more);

  function rebuildGrid() {
    computeVisible();
    resetStream();
    $$('.g-fit', grid).forEach(function (f) { dropPlayer(f); });
    unwatchAll();
    tileRO.disconnect();
    grid.innerHTML = '';
    $('#count').textContent = visible.length;
    $('#empty').hidden = visible.length !== 0;
    reelDirty = true;
    if (visible.length) appendGroups(3);
    fillIfNeeded();
  }
  mobileQ.addEventListener && mobileQ.addEventListener('change', function () {
    cols = mobileQ.matches ? 2 : 3;
    rebuildGrid();
  });

  grid.addEventListener('click', function (e) {
    // 요소도 data-open을 쓸 수 있으므로 갤러리 버튼만 봅니다
    var b = e.target.closest('.g-open, .g-exp');
    if (b && !b.closest('.ux')) openReel(+b.dataset.open, b.closest('.g-tile'));
  });

  /* ---------- 분류 칩: 고른 칩 뒤로 알약이 미끄러집니다 ---------- */
  var cats = $('#cats');
  var pill = $('.g-cats-pill', cats);
  function renderCats() {
    $$('.g-cat', cats).forEach(function (b) { b.remove(); });
    cats.insertAdjacentHTML('beforeend', ['전체'].concat(CATS).map(function (c) {
      var n = c === '전체' ? ITEMS.length : ITEMS.filter(function (it) { return it.category === c; }).length;
      return '<button class="g-cat" type="button" data-cat="' + esc(c) + '" aria-pressed="' + (c === activeCat) + '">' + esc(catLabel(c)) + '<i>' + n + '</i></button>';
    }).join(''));
  }
  function movePill(animate) {
    var b = $('.g-cat[aria-pressed="true"]', cats);
    if (!b) return;
    if (!animate) cats.classList.add('no-anim');
    pill.style.setProperty('--x', b.offsetLeft + 'px');
    pill.style.setProperty('--w', b.offsetWidth + 'px');
    if (!animate) requestAnimationFrame(function () { cats.classList.remove('no-anim'); });
  }
  cats.addEventListener('click', function (e) {
    var b = e.target.closest('[data-cat]');
    if (!b || b.dataset.cat === activeCat) return;
    activeCat = b.dataset.cat;
    $$('.g-cat', cats).forEach(function (c) { c.setAttribute('aria-pressed', String(c === b)); });
    movePill(true);
    b.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: reduce.matches ? 'auto' : 'smooth' });
    rebuildGrid();
    scrollToGridTop();
  });
  function scrollToGridTop() {
    var bar = $('#bar');
    var top = bar.getBoundingClientRect().top + scrollY;
    if (scrollY > top) window.scrollTo({ top: top, behavior: 'auto' });
  }
  window.addEventListener('resize', function () { movePill(false); });

  /* ---------- 검색: 아이콘이 입력창으로 펼쳐집니다 ---------- */
  var search = $('#search');
  var q = $('#q');
  var searchBtn = $('#search-btn');
  function openSearch() {
    search.classList.add('is-open');
    searchBtn.setAttribute('aria-expanded', 'true');
    q.tabIndex = 0;
    q.focus();
  }
  function closeSearch() {
    search.classList.remove('is-open');
    searchBtn.setAttribute('aria-expanded', 'false');
    q.tabIndex = -1;
  }
  searchBtn.addEventListener('click', function () {
    if (search.classList.contains('is-open')) { q.focus(); return; }
    openSearch();
  });
  var qT = 0;
  q.addEventListener('input', function () {
    clearTimeout(qT);
    qT = setTimeout(function () {
      query = q.value.trim().toLowerCase();
      search.classList.toggle('has-q', !!query);
      rebuildGrid();
      scrollToGridTop();
    }, 120);
  });
  q.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { e.preventDefault(); if (q.value) { q.value = ''; q.dispatchEvent(new Event('input')); } else { closeSearch(); searchBtn.focus(); } }
    if (e.key === 'Enter' && !e.isComposing && e.keyCode !== 229) { e.preventDefault(); var first = $('.g-tile .g-exp', grid); if (first) first.focus(); }
  });
  q.addEventListener('blur', function () { setTimeout(function () { if (!q.value && document.activeElement !== q) closeSearch(); }, 120); });
  $('#empty-reset').addEventListener('click', function () {
    q.value = ''; query = ''; search.classList.remove('has-q'); closeSearch();
    activeCat = '전체';
    $$('.g-cat', cats).forEach(function (c) { c.setAttribute('aria-pressed', String(c.dataset.cat === '전체')); });
    movePill(true);
    rebuildGrid();
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === '/' && body.dataset.view === 'grid' && !e.target.closest('input, textarea, select, [contenteditable], .ux') && !$('dialog[open]')) {
      e.preventDefault();
      openSearch();
    }
  });

  /* ---------- 도구줄이 위에 붙으면 아랫선을 보입니다 ---------- */
  var sentinel = document.createElement('div');
  sentinel.setAttribute('aria-hidden', 'true');
  $('#bar').before(sentinel);
  new IntersectionObserver(function (en) { $('#bar').classList.toggle('is-stuck', !en[0].isIntersecting); }).observe(sentinel);

  /* ---------- 프롬프트·코드 생성 ---------- */
  var GUIDE = {
    ko: [
      '아래 UI 요소를 제 프로젝트에 적용해 주세요.',
      '',
      '[먼저 확인할 것]',
      '1. 프로젝트의 프레임워크(React, Next, Vue, Svelte, 순수 HTML 등), 스타일 방식(CSS 모듈, Tailwind, 전역 CSS), 기존 테마 방식(data-theme, dark 클래스, CSS 변수)을 찾아 확인하세요.',
      '2. 삽입 위치의 파일과 기존 요소를 먼저 찾고, 그 요소가 어디서 쓰이는지 보고하세요.',
      '',
      '[적용 방법]',
      '3. 삽입 위치에 새 컴포넌트로 추가하세요. 교체 대상이 있으면 그 요소를 아래 요소로 바꾸세요.',
      '4. 기존 데이터, props, 이벤트 핸들러, 폼 값, 접근성 속성(라벨, aria, 키보드 조작)은 그대로 유지하세요.',
      '5. 아래 코드의 구조, 형태, 모션 값(시간, 곡선, 지연)을 기준으로 옮기세요. 프레임워크에 맞게 컴포넌트와 상태로 바꾸되, 디자인을 새로 추측해 바꾸지 마세요.',
      '6. 색은 아래 --ux-* 토큰을 프로젝트의 기존 테마 변수에 연결하세요. 라이트와 다크 두 값을 모두 유지하고, 두 테마에서 확인하세요.',
      '7. 스타일은 이 요소의 클래스(.uNNN) 안에만 두고, 전역 CSS나 전역 스크립트는 바꾸지 마세요. 클래스 이름이 기존 요소와 겹치지 않게 하세요.',
      '8. 예시 문구와 예시 데이터는 프로젝트의 실제 데이터로 바꾸세요. 갤러리 전용 화면과 시연 코드는 가져오지 마세요. 코드 맨 위의 라이선스 주석 한 줄은 새 컴포넌트 파일 맨 위에 남겨 두세요.',
      '9. prefers-reduced-motion을 켠 상태에서도 기능과 최종 상태가 그대로 작동하는지 확인하세요.',
      '',
      '[완료 보고]',
      '10. 변경한 파일 목록, 기존 요소와 달라진 동작, 확인한 범위(두 테마, 모바일 너비, 키보드), 확인하지 못한 항목을 알려 주세요.',
      '',
      '[삽입 위치] 여기에 페이지나 컴포넌트 이름을 적으세요',
      '[교체 대상] 기존 요소의 파일 경로나 컴포넌트 이름을 적으세요. 없으면 "없음"'
    ].join('\n'),
    en: [
      'Please add the UI element below to my project.',
      '',
      '[Check first]',
      '1. Find out the project’s framework (React, Next, Vue, Svelte, plain HTML, etc.), styling approach (CSS modules, Tailwind, global CSS) and existing theming approach (data-theme, a dark class, CSS variables).',
      '2. Locate the file and any existing element at the insertion point first, and report where that element is used.',
      '',
      '[How to apply]',
      '3. Add it as a new component at the insertion point. If there is a replacement target, replace that element with the one below.',
      '4. Keep existing data, props, event handlers, form values and accessibility attributes (labels, aria, keyboard support) as they are.',
      '5. Port the structure, shapes and motion values (durations, curves, delays) of the code below as they are. Convert it into components and state for the framework, but do not guess a new design.',
      '6. Map the --ux-* color tokens below to the project’s existing theme variables. Keep both the light and dark values and check both themes.',
      '7. Keep styles inside this element’s class (.uNNN) and do not change global CSS or global scripts. Make sure the class names do not clash with existing ones.',
      '8. Replace the sample copy and sample data with the project’s real data. Do not bring over gallery-only screens or demo code. Keep the one-line license comment at the top of the new component file.',
      '9. Check that the feature and its final states still work with prefers-reduced-motion turned on.',
      '',
      '[Report when done]',
      '10. List the files you changed, behavior that differs from the old element, what you checked (both themes, mobile width, keyboard) and anything you could not check.',
      '',
      '[Insertion point] Write the page or component name here',
      '[Replacement target] Write the file path or component name of the existing element, or "none"'
    ].join('\n')
  };
  // 복사·다운로드되는 코드 맨 위에 붙는 출처·라이선스 한 줄
  function licenseOf(it) {
    return '<!-- Lucian UX/UI Prompt #' + it.id + ' · MIT License (c) 2026 Seokwoooo · https://lucianlabs.dev/uxui-prompt/#' + it.id + ' -->\n';
  }
  function codeOf(it) {
    var c = loc(it);
    return licenseOf(it) + '<style>\n' + tokens() + '\n<\/style>\n\n' + c.html + '\n\n<script>\n' + c.js + '\n<\/script>\n';
  }
  function promptOf(it) {
    var c = loc(it);
    if (lang === 'en') {
      return '[Element] ' + c.title + ' (' + it.id + ', ' + c.category + ')\n' +
        '[What it does] ' + c.summary + '\n' +
        (c.hint ? '[How to use it] ' + c.hint + '\n' : '') + '\n' +
        GUIDE.en + '\n\n' +
        '--- Code start (this whole code is the working original) ---\n' +
        codeOf(it) +
        '--- Code end ---\n';
    }
    return '[요소] ' + c.title + ' (' + it.id + ', ' + c.category + ')\n' +
      '[요소 설명] ' + c.summary + '\n' +
      (c.hint ? '[조작] ' + c.hint + '\n' : '') + '\n' +
      GUIDE.ko + '\n\n' +
      '--- 코드 시작 (이 코드 전체가 실제로 동작하는 원본입니다) ---\n' +
      codeOf(it) +
      '--- 코드 끝 ---\n';
  }
  // 단독 파일: 토큰(라이트·다크), 요소, 테마 전환 버튼을 한 파일에 담습니다
  function standaloneOf(it) {
    var c = loc(it);
    return '<!doctype html>\n' + licenseOf(it) + '<html lang="' + lang + '">\n<head>\n<meta charset="utf-8">\n' +
      '<meta name="viewport" content="width=device-width,initial-scale=1">\n' +
      '<title>' + esc(c.title) + ' · lucianLabs UI</title>\n' +
      '<style>\n' + tokens() + '\n<\/style>\n' +
      '<style>\nbody{margin:0;min-height:100vh;display:grid;place-items:center;padding:48px 24px;background:var(--ux-page);box-sizing:border-box}\n' +
      '.ux-theme-btn{position:fixed;top:16px;right:16px;height:38px;padding:0 16px;border-radius:999px;border:1px solid var(--ux-line-2);background:var(--ux-surface);color:var(--ux-ink);font:600 13px/1 system-ui,sans-serif;cursor:pointer}\n<\/style>\n' +
      '</head>\n<body>\n' + c.html + '\n' +
      '<button class="ux-theme-btn" type="button" id="ux-theme-btn">' + esc(t('themeBtn')) + '</button>\n' +
      '<script>\n' + c.js + '\n<\/script>\n' +
      '<script>\n(function(){var r=document.documentElement,b=document.getElementById("ux-theme-btn"),K="ux-theme";' +
      'try{var s=localStorage.getItem(K);if(s)r.setAttribute("data-theme",s)}catch(e){}' +
      'b.addEventListener("click",function(){var dark=r.getAttribute("data-theme")==="dark"||(!r.hasAttribute("data-theme")&&matchMedia("(prefers-color-scheme: dark)").matches);' +
      'var next=dark?"light":"dark";r.setAttribute("data-theme",next);try{localStorage.setItem(K,next)}catch(e){}});})();\n<\/script>\n' +
      '</body>\n</html>\n';
  }
  function legacyCopy(text) {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    (document.querySelector('dialog[open]') || body).appendChild(ta);
    ta.select();
    var ok = false;
    try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
    ta.remove();
    return ok;
  }
  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text).then(function () { return true; }, function () { return legacyCopy(text); });
    }
    return Promise.resolve(legacyCopy(text));
  }
  function download(it) {
    var blob = new Blob([standaloneOf(it)], { type: 'text/html;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = 'ux-' + it.id + '-' + it.slug + (lang === 'en' ? '-en' : '') + '.html';
    body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 4000);
  }

  /* ---------- 알림과 완료 표시 ---------- */
  var toastEl = $('#toast');
  var toastT = 0;
  function toast(msg) {
    toastEl.innerHTML = ICON.check.replace('<svg', '<svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"') + '<span></span>';
    toastEl.lastChild.textContent = msg;
    toastEl.classList.add('is-on');
    clearTimeout(toastT);
    toastT = setTimeout(function () { toastEl.classList.remove('is-on'); }, 2000);
  }
  function markDone(btn) {
    btn.classList.add('is-done');
    clearTimeout(btn._t);
    btn._t = setTimeout(function () { btn.classList.remove('is-done'); }, 1500);
  }

  /* ---------- 프롬프트 시트: 프롬프트와 코드를 탭으로 오갑니다 ---------- */
  var dlgPrompt = $('#dlg-prompt');
  var prText = $('#pr-text');
  var prIdx = 0;
  var prTab = 'prompt';
  var segPill = $('.g-seg-pill', dlgPrompt);
  function setTab(tab) {
    prTab = tab;
    var it = ITEMS[prIdx];
    var b = $('#tab-' + tab);
    $('#tab-prompt').setAttribute('aria-selected', String(tab === 'prompt'));
    $('#tab-code').setAttribute('aria-selected', String(tab === 'code'));
    segPill.style.setProperty('--x', (b.offsetLeft - 4) + 'px');
    segPill.style.setProperty('--w', b.offsetWidth + 'px');
    prText.value = tab === 'prompt' ? promptOf(it) : codeOf(it);
    prText.setAttribute('aria-label', tab === 'prompt' ? t('areaPrompt') : t('areaCode'));
    prText.scrollTop = 0;
    $('#pr-copy span').textContent = tab === 'prompt' ? t('copyPrompt') : t('copyCode');
    var n = prText.value.length.toLocaleString(t('num'));
    $('#pr-hint').textContent = tab === 'prompt' ? T[lang].hintPrompt(n) : T[lang].hintCode(n);
  }
  function openPrompt(i) {
    prIdx = i;
    var c = loc(ITEMS[i]);
    $('#pr-num').textContent = ITEMS[i].id;
    $('#pr-cat').textContent = c.category;
    $('#pr-title').textContent = c.title;
    $('#pr-skill').textContent = T[lang].skillAskId(ITEMS[i].id);
    openDialog(dlgPrompt);
    setTab('prompt');
  }
  $('#tab-prompt').addEventListener('click', function () { setTab('prompt'); });
  $('#tab-code').addEventListener('click', function () { setTab('code'); });
  $('.g-seg', dlgPrompt).addEventListener('keydown', function (e) {
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
      e.preventDefault();
      var nx = prTab === 'prompt' ? 'code' : 'prompt';
      setTab(nx);
      $('#tab-' + nx).focus();
    }
  });
  $('#pr-copy').addEventListener('click', function (e) {
    var btn = e.currentTarget;
    copyText(prText.value).then(function (ok) {
      if (ok) { markDone(btn); toast(prTab === 'prompt' ? t('tPromptCopied') : t('tCodeCopied')); }
      else { prText.focus(); prText.select(); toast(t('tSelect')); }
    });
  });
  $('#pr-dl').addEventListener('click', function () { download(ITEMS[prIdx]); toast(t('tSaved')); });
  $$('[data-close]').forEach(function (b) { b.addEventListener('click', function () { closeDialog(b.closest('dialog')); }); });
  $$('dialog').forEach(function (d) {
    d.addEventListener('click', function (e) { if (e.target === d) closeDialog(d); });
    d.addEventListener('close', function () { markDialogs(); syncAll(); });
  });
  $('#to-guide').addEventListener('click', function () { openDialog($('#dlg-guide')); });
  // 에이전트 스킬 안내: 적용 방법 대화상자를 열고 스킬 블록으로 바로 갑니다
  function openSkill() {
    if (dlgPrompt.open) closeDialog(dlgPrompt);
    openDialog($('#dlg-guide'));
    var sec = $('#guide-skill');
    sec.scrollIntoView({ block: 'start' });
    sec.focus({ preventScroll: true });
  }
  $$('#to-skill, [data-open-skill]').forEach(function (b) { b.addEventListener('click', openSkill); });
  // 명령 한 줄 복사: 버튼 옆 code의 글을 복사하고, 안 되면 그 글을 선택해 둡니다
  $$('[data-copy]').forEach(function (b) {
    b.addEventListener('click', function () {
      var code = b.parentNode.querySelector('code');
      copyText(code.textContent).then(function (ok) {
        if (ok) { markDone(b); toast(t('tCmdCopied')); return; }
        var sel = window.getSelection();
        sel.removeAllRanges(); sel.selectAllChildren(code);
        toast(t('tSelect'));
      });
    });
  });

  /* ---------- 릴스: 한 화면에 요소 하나, 위아래로 넘깁니다 ---------- */
  var reel = $('#reel');
  var reelList = [];
  var reelDirty = true;
  var slides = [];
  var cur = -1;
  var mounted = {};
  var opener = null;
  function slideMeta(s, it) {
    var c = loc(it);
    s.setAttribute('aria-label', it.id + ' ' + c.title);
    $('.g-slide-meta', s).innerHTML =
      '<p class="g-slide-kick"><b>' + it.id + '</b> · ' + esc(c.category) + '</p>' +
      '<h2 class="g-slide-t">' + esc(c.title) + '</h2>' +
      '<p class="g-slide-s">' + esc(c.summary) + '</p>' +
      (c.hint ? '<p class="g-slide-hint">' + ICON.hand + '<span>' + esc(c.hint) + '</span></p>' : '');
    $('.g-rail', s).innerHTML =
      '<button class="g-rb" type="button" data-act="prompt"><i>' + ICON.prompt + '</i><span>' + esc(t('railPrompt')) + '</span></button>' +
      '<button class="g-rb" type="button" data-act="copy"><i>' + ICON.copy + '</i><span>' + esc(t('railCopy')) + '</span></button>' +
      '<button class="g-rb" type="button" data-act="code"><i>' + ICON.code + '</i><span>' + esc(t('railCode')) + '</span></button>';
  }
  function buildReel(all) {
    Object.keys(mounted).forEach(function (k) { unmountSlide(+k); });
    reelList = visible.length && !all ? visible.slice() : ITEMS.map(function (_, i) { return i; });
    reel.innerHTML = '';
    // 200장을 한 번에 그리면 여는 순간이 끊기므로, 높이만 있는 빈 화면을 만들고 내용은 fillSlide가 채웁니다
    var frag = document.createDocumentFragment();
    slides = reelList.map(function (idx, p) {
      var s = document.createElement('section');
      s.className = 'g-slide';
      s.dataset.p = String(p);
      s.setAttribute('aria-label', ITEMS[idx].id + ' ' + loc(ITEMS[idx]).title);
      frag.appendChild(s);
      return s;
    });
    reel.appendChild(frag);
    mounted = {};
    cur = -1;
    reelDirty = false;
  }
  function fillSlide(p) {
    var s = slides[p];
    if (!s || s._filled) return;
    var it = ITEMS[reelList[p]];
    s.style.setProperty('--h', it.hue);
    s.style.setProperty('--h2', it.hue2);
    s.innerHTML =
      '<div class="g-slide-bg" aria-hidden="true"></div>' +
      '<div class="g-slide-stage"><div class="g-fit' + (it.fluid ? ' is-fluid' : '') + '"></div></div>' +
      '<div class="g-slide-meta"></div>' +
      '<div class="g-rail"></div>';
    slideMeta(s, it);
    if (!s._bound) { bindTakeover(s); s._bound = true; }
    s._filled = true;
  }
  // 멀어진 화면은 다시 비워 둡니다(요소가 올라가 있으면 그대로 둡니다)
  function emptySlide(p) {
    var s = slides[p];
    if (!s || !s._filled || mounted[p]) return;
    s.innerHTML = '';
    s._filled = false;
  }
  function stageOf(p) { fillSlide(p); return slides[p].querySelector('.g-slide-stage'); }
  // 좁은 화면에서는 설명 블록의 실제 높이만큼 무대를 띄워 요소와 설명이 겹치지 않게 합니다
  function placeStage(p) {
    var s = slides[p], st = stageOf(p), m = $('.g-slide-meta', s);
    if (wideQ.matches || !m) { st.style.bottom = ''; return; }
    st.style.bottom = Math.ceil(m.offsetHeight + (parseFloat(getComputedStyle(m).bottom) || 0) + 20) + 'px';
  }
  function mountSlide(p) {
    if (mounted[p]) return;
    var st = stageOf(p);
    mountInto(st.firstElementChild, ITEMS[reelList[p]]);
    mounted[p] = true;
    placeStage(p);
    fitSlide(st, st.firstElementChild);
    attachPlayer(st.firstElementChild, reelList[p], 'slide');
  }
  function unmountSlide(p) {
    if (!mounted[p]) return;
    if (slides[p]) unmount(stageOf(p).firstElementChild);
    delete mounted[p];
  }
  function setCurrent(p) {
    if (p === cur || p < 0 || p >= slides.length) return;
    if (cur >= 0 && slides[cur]) slides[cur].classList.remove('is-on');
    cur = p;
    slides[p].classList.add('is-on');
    for (var k = Math.max(0, p - 2); k <= Math.min(slides.length - 1, p + 2); k++) fillSlide(k);
    [p - 1, p, p + 1].forEach(function (k) { if (k >= 0 && k < slides.length) mountSlide(k); });
    slides.forEach(function (s, k) { if (s._filled && Math.abs(k - p) > 4) emptySlide(k); });
    Object.keys(mounted).forEach(function (k) { k = +k; if (Math.abs(k - p) > 1) unmountSlide(k); });
    // 지금 화면의 요소만 시연하고, 이웃 화면은 멈춰 둡니다
    Object.keys(mounted).forEach(function (k) {
      var f = stageOf(+k).firstElementChild, P = f._pl;
      if (P) {
        P.vis = +k === p; syncPlayer(P);
        // 옆 화면은 흐려지며 사라진 뒤(0.7초)에 되돌려 둡니다
        if (!P.vis && P.dirty) setTimeout(function () { if (!P.vis && !P.on) quietReset(P); }, 700);
      }
    });
    var it = ITEMS[reelList[p]];
    $('#prog-n').textContent = it.id;
    $('#prog-t').textContent = String(slides.length).padStart(3, '0');
    $('#prog-bar').style.setProperty('--p', ((p + 1) / slides.length).toFixed(4));
    if (body.dataset.view === 'reel') history.replaceState({ reel: true }, '', '#' + it.id);
  }
  var scrollRaf = 0;
  reel.addEventListener('scroll', function () {
    if (scrollRaf) return;
    scrollRaf = requestAnimationFrame(function () {
      scrollRaf = 0;
      var h = reel.clientHeight || 1;
      setCurrent(Math.round(reel.scrollTop / h));
    });
  }, { passive: true });
  function goTo(p, smooth) {
    p = Math.max(0, Math.min(slides.length - 1, p));
    reel.scrollTo({ top: p * reel.clientHeight, behavior: smooth && !reduce.matches ? 'smooth' : 'auto' });
    if (!smooth) setCurrent(p);
  }
  var gridOffT = 0;
  function openReel(idx, fromTile, noPush) {
    if (reelDirty || !slides.length) buildReel();
    var p = reelList.indexOf(idx);
    if (p < 0) { buildReel(true); reelDirty = true; p = reelList.indexOf(idx); }
    opener = fromTile || null;
    body.dataset.view = 'reel';
    reel.setAttribute('aria-hidden', 'false');
    // 그리드의 요소는 잠시 해제해서 릴스만 움직이게 합니다. 여는 순간 한꺼번에 내리면 첫 화면이 끊기므로 릴스가 펼쳐진 뒤에 내립니다
    unwatchAll();
    clearTimeout(gridOffT);
    gridOffT = setTimeout(function () {
      if (body.dataset.view !== 'reel') return;
      $$('.g-fit', grid).forEach(function (f) { if (f.firstChild) unmount(f); });
    }, 700);
    if (!noPush) history.pushState({ reel: true }, '', '#' + ITEMS[idx].id);
    requestAnimationFrame(function () {
      goTo(p, false);
      var s = slides[p];
      s.setAttribute('tabindex', '-1');
      s.focus({ preventScroll: true });
      syncAll();
    });
  }
  function closeReel(fromPop) {
    if (body.dataset.view !== 'reel') return;
    body.dataset.view = 'grid';
    reel.setAttribute('aria-hidden', 'true');
    Object.keys(mounted).forEach(function (k) { unmountSlide(+k); });
    cur = -1;
    $$('.g-stage', grid).forEach(function (st) { watchStage(st); });
    if (!fromPop) {
      if (history.state && history.state.reel) history.back();
      else history.replaceState(null, '', location.pathname + location.search);
    }
    var back = opener && opener.isConnected ? $('.g-exp', opener) : null;
    if (back) back.focus({ preventScroll: true });
  }
  window.addEventListener('popstate', function () {
    var m = /^#(\d{3})$/.exec(location.hash);
    var idx = m ? ITEMS.findIndex(function (it) { return it.id === m[1]; }) : -1;
    if (idx >= 0) { if (body.dataset.view !== 'reel') openReel(idx, null, true); else goTo(reelList.indexOf(idx), true); }
    else closeReel(true);
  });
  $('#to-reel').addEventListener('click', function () {
    var first = visible.length ? visible[0] : 0;
    openReel(first, null);
  });
  reel.addEventListener('click', function (e) {
    var b = e.target.closest('[data-act]');
    if (!b || b.closest('.ux')) return;
    var p = +b.closest('.g-slide').dataset.p;
    var it = ITEMS[reelList[p]];
    var act = b.dataset.act;
    if (act === 'prompt') openPrompt(reelList[p]);
    else if (act === 'copy') {
      copyText(promptOf(it)).then(function (ok) {
        if (ok) { markDone(b); toast(t('tPromptCopied')); }
        else { openPrompt(reelList[p]); toast(t('tCopyIn')); }
      });
    } else if (act === 'code') { download(it); markDone(b); toast(t('tSaved')); }
  });
  $('#hud').addEventListener('click', function (e) {
    var b = e.target.closest('[data-act]');
    if (!b) return;
    if (b.dataset.act === 'back') closeReel(false);
    if (b.dataset.act === 'theme') toggleTheme(b);
  });
  document.addEventListener('keydown', function (e) {
    if (body.dataset.view !== 'reel' || $('dialog[open]')) return;
    var inEl = e.target.closest && e.target.closest('.ux');
    var k = e.key;
    if (k === 'Escape') {
      e.preventDefault();
      // 요소 안에 초점이 있으면 먼저 요소에서 빠져나오고, 한 번 더 누르면 그리드로 돌아갑니다
      if (inEl) { slides[cur].focus({ preventScroll: true }); return; }
      closeReel(false);
      return;
    }
    if (inEl || e.target.matches('input, textarea, select')) return;
    if (k === 'ArrowDown' || k === 'PageDown' || k === 'j' || (k === ' ' && !e.shiftKey)) { e.preventDefault(); goTo(cur + 1, true); }
    else if (k === 'ArrowUp' || k === 'PageUp' || k === 'k' || (k === ' ' && e.shiftKey)) { e.preventDefault(); goTo(cur - 1, true); }
    else if (k === 'Home') { e.preventDefault(); goTo(0, true); }
    else if (k === 'End') { e.preventDefault(); goTo(slides.length - 1, true); }
  });
  var rT = 0;
  window.addEventListener('resize', function () {
    clearTimeout(rT);
    rT = setTimeout(function () {
      Object.keys(mounted).forEach(function (k) { var st = stageOf(+k); placeStage(+k); fitSlide(st, st.firstElementChild); });
      if (body.dataset.view === 'reel' && cur >= 0) reel.scrollTop = cur * reel.clientHeight;
    }, 120);
  });

  /* ---------- 언어 적용: 정적 문구, 분류, 타일, 릴스, 열린 대화상자까지 한 번에 바꿉니다 ---------- */
  function applyStatic() {
    root.setAttribute('lang', lang);
    document.title = t('docTitle');
    var md = $('meta[name="description"]');
    if (md) md.setAttribute('content', t('docDesc'));
    $$('[data-i18n]').forEach(function (el) { el.textContent = t(el.getAttribute('data-i18n')); });
    $$('[data-i18n-html]').forEach(function (el) { el.innerHTML = t(el.getAttribute('data-i18n-html')); });
    $$('[data-i18n-attr]').forEach(function (el) {
      el.getAttribute('data-i18n-attr').split(';').forEach(function (pair) {
        var kv = pair.split(':');
        if (kv.length === 2) el.setAttribute(kv[0].trim(), t(kv[1].trim()));
      });
    });
    $('#count-wrap').innerHTML = T[lang].count(visible.length || ITEMS.length);
    $('#guide-steps').innerHTML = T[lang].guideSteps.map(function (s) { return '<li>' + s + '</li>'; }).join('');
    $$('.g-lang-b').forEach(function (b) { b.setAttribute('aria-pressed', String(b.dataset.lang === lang)); });
    var on = $('.g-lang-b[aria-pressed="true"]');
    var lp = $('.g-lang-pill');
    if (on && lp) { lp.style.setProperty('--x', on.offsetLeft + 'px'); lp.style.setProperty('--w', on.offsetWidth + 'px'); }
    syncTheme();
    syncAutoBtn();
  }
  function setLang(next) {
    if (next !== 'ko' && next !== 'en') return;
    store.set(LANG_KEY, next);
    if (next === lang) return;
    lang = next;
    applyStatic();
    renderCats();
    movePill(false);
    // 타일은 자리를 그대로 두고 문구와 요소만 바꿉니다
    $$('.g-tile', grid).forEach(function (el) {
      var it = ITEMS[+el.dataset.idx];
      if (!it) return;
      tileText(el, it);
      var stage = $('.g-stage', el), fit = stage && stage.firstElementChild;
      if (fit && fit.firstChild) { unmount(fit); mountTile(stage); }
    });
    if (slides.length) {
      if (body.dataset.view === 'reel' && cur >= 0) {
        var keep = cur;
        slides.forEach(function (s, p) {
          var it = ITEMS[reelList[p]];
          if (s._filled) slideMeta(s, it); else s.setAttribute('aria-label', it.id + ' ' + loc(it).title);
        });
        Object.keys(mounted).forEach(function (k) { unmountSlide(+k); });
        cur = -1;
        setCurrent(keep);
      } else reelDirty = true;
    }
    if (dlgPrompt.open) openPrompt(prIdx);
  }
  $$('.g-lang-b').forEach(function (b) { b.addEventListener('click', function () { setLang(b.dataset.lang); }); });

  /* ---------- 시작 ---------- */
  computeVisible();
  applyStatic();
  renderCats();
  rebuildGrid();
  movePill(false);
  root.classList.remove('i18n-wait');
  requestAnimationFrame(function () { $('.g-head').classList.add('is-ready'); applyStatic(); });
  var m0 = /^#(\d{3})$/.exec(location.hash);
  if (m0) {
    var i0 = ITEMS.findIndex(function (it) { return it.id === m0[1]; });
    if (i0 >= 0) { history.replaceState(null, '', location.pathname + location.search); openReel(i0, null); }
  }

  // 자동 점검과 다른 스크립트가 쓰는 도구입니다
  window.UXG = {
    ITEMS: ITEMS, promptOf: promptOf, codeOf: codeOf, standaloneOf: standaloneOf, openReel: openReel, closeReel: closeReel,
    openPrompt: openPrompt, toggleTheme: toggleTheme, isDark: isDark, loc: loc, setLang: setLang, setAuto: setAuto,
    lang: function () { return lang; }, auto: function () { return autoOn; }, players: players, localize: uxLocalize
  };
})();
