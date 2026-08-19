// setAnswerText 의 URL 링크화 점검. 프레임워크 없이 node 로 바로 돈다.
//
//   npm run qa:linkify
//
// 표적: FAQ 답변에 넣은 자료 링크가 클릭 가능해지는가, XSS 가 안 뚫리는가.
import assert from "node:assert/strict";

const el = { innerHTML: "" };
globalThis.document = { querySelector: () => null };
const ui = await import(new URL("../static/js/ui.js", import.meta.url).href);

// 1) 평문 URL → 앵커. 새 탭 + noopener.
ui.setAnswerText(el, "자료는 https://ex.com/guide.pdf 에서 내려받으세요");
assert.match(el.innerHTML, /<a href="https:\/\/ex\.com\/guide\.pdf" target="_blank" rel="noopener noreferrer">/);

// 2) 쿼리스트링의 & 는 이스케이프된 채로 href 에 남는다(유효한 HTML).
ui.setAnswerText(el, "https://ex.com/f?a=1&b=2 확인");
assert.match(el.innerHTML, /href="https:\/\/ex\.com\/f\?a=1&amp;b=2"/);

// 3) 문장 끝 마침표·괄호는 링크에 안 들어간다.
ui.setAnswerText(el, "내려받아 확인해 주세요. (https://ex.com/x).");
assert.match(el.innerHTML, /<a href="https:\/\/ex\.com\/x"[^>]*>https:\/\/ex\.com\/x<\/a>\)\./);

// 4) XSS: 스크립트는 이스케이프돼 텍스트로만 남는다.
ui.setAnswerText(el, '<script>alert(1)</script> https://ex.com');
assert.doesNotMatch(el.innerHTML, /<script>/);
assert.match(el.innerHTML, /&lt;script&gt;/);

// 5) javascript: 스킴은 링크가 되지 않는다(http/https 만 매치).
ui.setAnswerText(el, "javascript:alert(1) 를 누르세요");
assert.doesNotMatch(el.innerHTML, /<a /);

// 6) URL 없는 평문은 그대로.
ui.setAnswerText(el, "일반 답변입니다");
assert.equal(el.innerHTML, "일반 답변입니다");

console.log("OK — linkify 6 checks passed");
