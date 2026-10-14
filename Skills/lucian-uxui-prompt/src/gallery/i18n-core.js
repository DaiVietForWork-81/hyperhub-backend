/* 요소 코드의 영어판을 만드는 공용 변환기입니다. 빌드(검사)와 갤러리(미리보기·복사·다운로드)가 같은 함수를 씁니다.
   1) 한글이 든 주석을 지우고 2) 요소별 번역 목록(map)을 긴 문구부터 한 번에 바꿉니다. */
function uxLocalize(code, kind, pairs) {
  var HANGUL = /[ㄱ-ㆎ가-힣]/;
  var out = String(code);
  if (kind === 'html') {
    out = out.replace(/<!--[\s\S]*?-->/g, function (m) { return HANGUL.test(m) ? '' : m; });
    out = out.replace(/\/\*[\s\S]*?\*\//g, function (m) { return HANGUL.test(m) ? '' : m; });
  } else {
    out = out.replace(/\/\*[\s\S]*?\*\//g, function (m) { return HANGUL.test(m) ? '' : m; });
    out = out.split('\n').filter(function (line) { return !(/^\s*\/\//.test(line) && HANGUL.test(line)); }).join('\n');
    out = out.replace(/([^\s:'"\\])([ \t]+)\/\/ [^\n'"]*$/gm, function (m, a) { return HANGUL.test(m) ? a : m; });
  }
  if (pairs && pairs.length) {
    var dict = {};
    var keys = [];
    pairs.forEach(function (p) { if (!(p[0] in dict)) keys.push(p[0]); dict[p[0]] = p[1]; });
    keys.sort(function (a, b) { return b.length - a.length; });
    var re = new RegExp(keys.map(function (k) { return k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }).join('|'), 'g');
    out = out.replace(re, function (m) { return dict[m]; });
  }
  return out;
}
