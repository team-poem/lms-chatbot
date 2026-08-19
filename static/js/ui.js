// 프레젠테이션 계층: DOM 생성·렌더만 담당한다. 서버 통신 없음(콜백 주입).

export const $ = (s) => document.querySelector(s);

export function escapeHtml(s) { return s.replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c])); }

// 답변 텍스트를 렌더한다(평문). 단 게시판 문구('e-Class QnA 게시판', 'Q&A 바로가기'
// 등)는 게시판 하이퍼링크로 건다 — 안내 시 게시판으로 바로 이동할 수 있게.
const QNA_LINK_PHRASES = ["e-Class QnA 게시판", "Q&A 바로가기", "Q&A 게시판"];

// 게시판 URL 은 모듈이 들고 있는다. 호출부마다 넘기게 두면 넘기는 걸 잊은 곳만
// 조용히 맨 텍스트가 된다 — 실제로 상담 카드(renderAnswerCard)가 빈 문자열을
// 넘기고 있었고, 후보 블록은 아예 textContent 로 찍고 있었다.
let qnaBoardUrl = "";
export function setQnaBoardUrl(url) { qnaBoardUrl = url || ""; }

// 이스케이프 뒤의 텍스트에서 URL 을 링크로 바꾼다. FAQ 답변(사람이 쓴 원문)에
// 자료 다운로드 링크를 넣으면 그대로 클릭 가능해진다 — 새 자료가 생길 때 코드
// 수정 없이 노션 FAQ 행 추가만으로 끝나게 하는 연결 고리다.
// 이스케이프 이후에 돌므로 정규식은 &amp; 가 섞인 형태를 만난다(쿼리스트링).
// 끝에 붙은 문장부호(.,)·괄호)는 링크에서 뗀다 — "…하세요. https://x)." 방지.
const URL_RE = /https?:\/\/[^\s<>"']+/g;
function linkifyUrls(html) {
  return html.replace(URL_RE, (url) => {
    const trimmed = url.replace(/[.,)\u3002]+$/, "");
    const rest = url.slice(trimmed.length);
    return `<a href="${trimmed}" target="_blank" rel="noopener noreferrer">${trimmed}</a>${rest}`;
  });
}

export function setAnswerText(el, text) {
  let html = linkifyUrls(escapeHtml(text));
  if (qnaBoardUrl) {
    QNA_LINK_PHRASES.forEach(phrase => {
      const a = `<a href="${escapeHtml(qnaBoardUrl)}" target="_blank" rel="noopener noreferrer">${escapeHtml(phrase)}</a>`;
      html = html.split(escapeHtml(phrase)).join(a);
    });
  }
  el.innerHTML = html;
}

const ICON_PAPERCLIP = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.44 11.05-9.19 9.19a6 6 0 1 1-8.49-8.49l8.57-8.57A4 4 0 1 1 17.93 8.8L9.41 17.32a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>';
const ICON_DOC = '<svg width="14" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zm-1 7V3.5L18.5 9H13z"/></svg>';
const ICON_THUMBS_UP = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 10v12"/><path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H7V10l4.66-9.32a.5.5 0 0 1 .66-.22l1.06.53a2 2 0 0 1 1.02 2.4L15 5.88Z"/></svg>';
const ICON_THUMBS_DOWN = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 14V2"/><path d="M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H17v12l-4.66 9.32a.5.5 0 0 1-.66.22l-1.06-.53a2 2 0 0 1-1.02-2.4L9 18.12Z"/></svg>';

// ── 입력 게이트 ─────────────────────────────────────────────────
export function setChatEnabled(enabled) {
  $("#q").disabled = !enabled;
  $("#form button[type=submit]").disabled = !enabled;
}

export function setUserLabel(label) { $("#user-label").textContent = label; }

export function focusComposer() { $("#q").focus(); }

// ── 대화 턴 ──────────────────────────────────────────────────────
export function appendUserBubble(text) {
  const log = $("#log");
  if (log.querySelector(".empty")) log.innerHTML = "";
  const div = document.createElement("div");
  div.className = "turn";
  div.innerHTML = `<div class="q">${escapeHtml(text)}</div>`;
  log.appendChild(div);
}

// 대기 문구는 호출부가 정한다 — 지금 실제로 무엇을 기다리는지(검색/불러오기)를
// 그대로 쓴다. 문구가 곧 진행 단계라 임의의 일반 문구를 넣지 않는다.
const loadingHtml = (label) => `<span class="loading">${escapeHtml(label)}</span>`;

// 응답을 기다리는 동안만 띄우는 대기 턴. 반환한 함수를 부르면 통째로 사라진다.
// (선택형 상담 경로처럼 스켈레톤에 답변을 채워 넣지 않는 곳에서 쓴다.)
export function appendLoading(userText, label) {
  const log = $("#log");
  if (log.querySelector(".empty")) log.innerHTML = "";
  const div = document.createElement("div");
  div.className = "turn";
  div.innerHTML = (userText ? `<div class="q">${escapeHtml(userText)}</div>` : "")
    + `<div class="a">${loadingHtml(label)}</div>`;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
  return () => div.remove();
}

// 질문 말풍선 + 대기 문구 + 빈 답변/이미지/출처/피드백 영역을 가진 턴 스켈레톤.
export function appendTurnSkeleton(query, label) {
  const log = $("#log");
  if (log.querySelector(".empty")) log.innerHTML = "";
  const div = document.createElement("div");
  div.className = "turn";
  div.innerHTML = `<div class="q">${escapeHtml(query)}</div><div class="a">${loadingHtml(label)}</div><div class="imgs"></div><div class="src"></div><div class="fb"></div>`;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
  let loadingActive = true;
  const removeLoading = () => {
    if (!loadingActive) return;
    loadingActive = false;
    const a = div.querySelector(".a");
    const l = a.querySelector(".loading");
    if (l) { a.removeChild(l); }
  };
  return {div, removeLoading};
}

export function setAnswerPlain(turnDiv, text) {
  turnDiv.querySelector(".a").textContent = text;
}

export function appendAnswerDelta(turnDiv, delta) {
  turnDiv.querySelector(".a").textContent += delta;
  const log = $("#log");
  log.scrollTop = log.scrollHeight;
}

export function renderImages(turnDiv, images) {
  const imgs = turnDiv.querySelector(".imgs");
  images.forEach(src => {
    const i = document.createElement("img");
    i.src = src;
    i.loading = "lazy";
    i.alt = "";
    // 자산이 없는 경로(404)는 X 박스 대신 자리 제거
    i.onerror = () => i.remove();
    i.onclick = () => openLightbox(src);
    imgs.appendChild(i);
  });
}

export function renderSources(turnDiv, sources) {
  const srcEl = turnDiv.querySelector(".src");
  srcEl.innerHTML = "";
  const h = document.createElement("h4");
  h.innerHTML = ICON_PAPERCLIP + " <span>관련 문서</span>";
  srcEl.appendChild(h);
  const ul = document.createElement("ul");
  sources.forEach(s => {
    const title = typeof s === "string" ? s : (s.title || "");
    const url = typeof s === "object" ? (s.url || "") : "";
    const li = document.createElement("li");
    li.insertAdjacentHTML("beforeend", ICON_DOC);
    if (url) {
      const a = document.createElement("a");
      a.href = url;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.textContent = title;
      li.appendChild(a);
    } else {
      const span = document.createElement("span");
      span.textContent = title;
      li.appendChild(span);
      li.classList.add("no-link");
    }
    ul.appendChild(li);
  });
  srcEl.appendChild(ul);
}

// onRate(turnId, rating) -> Promise — 통신은 호출부(main)가 주입한다.
export function renderFeedback(turnDiv, turnId, onRate) {
  const fb = turnDiv.querySelector(".fb");
  fb.innerHTML = "";
  const q = document.createElement("span");
  q.className = "q";
  q.textContent = "이 응답이 도움이 되었습니까?";
  fb.appendChild(q);
  // "예"(긍정)를 먼저 배치
  [["예", 3, ICON_THUMBS_UP, "yes"], ["아니오", 1, ICON_THUMBS_DOWN, "no"]].forEach(([text, rating, icon, cls]) => {
    const b = document.createElement("button");
    b.className = cls;
    b.innerHTML = icon + " <span>" + text + "</span>";
    b.onclick = () => onRate(turnId, rating).then(() => {
      fb.innerHTML = '<span class="thanks">피드백 감사합니다.</span>';
    });
    fb.appendChild(b);
  });
}

// ── 라이트박스 ───────────────────────────────────────────────────
export function openLightbox(src) {
  const lb = document.getElementById("lightbox");
  document.getElementById("lightbox-img").src = src;
  lb.classList.add("open");
}

export function closeLightbox() {
  document.getElementById("lightbox").classList.remove("open");
  document.getElementById("lightbox-img").src = "";
}

export function initLightbox() {
  document.getElementById("lightbox").addEventListener("click", closeLightbox);
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") closeLightbox();
  });
}

// ── FAQ 칩 / 가이드 네비게이션(3뎁스) ───────────────────────────
export function makeChip(label, cls, onClick, withArrow) {
  const b = document.createElement("button");
  b.className = cls;
  b.type = "button";
  if (withArrow) b.innerHTML = escapeHtml(label) + ' <span class="arrow">›</span>';
  else b.textContent = label;
  b.onclick = onClick;
  return b;
}

// 항목은 문자열(리롤: 표시=전송) 또는 {label, text}(첫 진입: 메달 이모지는 표시만).
export function faqRowOf(questions, onAsk) {
  const row = document.createElement("div");
  row.className = "faq-row";
  questions.forEach(q => {
    const label = q.label || q, text = q.text || q;
    row.appendChild(makeChip(label, "faq-chip", () => onAsk(text)));
  });
  return row;
}

// 1뎁스: 매뉴얼별 대분류 칩 섹션(엘리먼트 반환, 데이터 없으면 null).
// onPickCategory(manualName, cat) — 2뎁스 전개는 호출부가 결정.
export function buildCatalogSection(manuals, introText, onPickCategory) {
  if (!manuals.length) return null;
  const sec = document.createElement("div");
  sec.className = "cat-section";
  const intro = document.createElement("p");
  intro.className = "cat-intro";
  intro.textContent = introText;
  sec.appendChild(intro);
  manuals.forEach(m => {
    const block = document.createElement("div");
    block.className = "manual-block";
    const label = document.createElement("span");
    label.className = "manual-label";
    label.textContent = m.title;
    block.appendChild(label);
    const grid = document.createElement("div");
    grid.className = "chip-grid";
    m.categories.forEach(cat =>
      grid.appendChild(makeChip(cat.name, "cat-chip", () => onPickCategory(m.name, cat), true)));
    block.appendChild(grid);
    sec.appendChild(block);
  });
  return sec;
}

// 2뎁스: 선택한 대분류의 하위 문서 칩 블록을 로그에 덧붙인다.
// onAskDoc(docTitle) — 매뉴얼 스코프 결정은 호출부(main) 책임.
export function appendCategoryBlock(cat, onAskDoc) {
  const log = $("#log");
  const wrap = document.createElement("div");
  wrap.className = "faq";
  const intro = document.createElement("p");
  intro.className = "faq-intro";
  intro.textContent = "‘" + cat.name + "’ 관련 안내입니다. 궁금한 항목을 선택해 주세요.";
  wrap.appendChild(intro);
  const row = document.createElement("div");
  row.className = "faq-row";
  cat.docs.forEach(doc => row.appendChild(makeChip(doc, "faq-chip", () => onAskDoc(doc))));
  wrap.appendChild(row);
  log.appendChild(wrap);
  log.scrollTop = log.scrollHeight;
}

// 첫 진입 화면: 인트로 + 고정 FAQ TOP 칩 + (있으면) 가이드 대분류 섹션. 로그를 비우고 채운다.
export function renderEntry(questions, catalogSectionEl, onAsk) {
  const log = $("#log");
  log.innerHTML = "";
  const wrap = document.createElement("div");
  wrap.className = "faq";
  const intro = document.createElement("p");
  intro.className = "faq-intro";
  intro.textContent = "자주하는 질문(FAQ) TOP 5";
  wrap.appendChild(intro);
  if (questions.length) wrap.appendChild(faqRowOf(questions, onAsk));
  if (catalogSectionEl) wrap.appendChild(catalogSectionEl);
  log.appendChild(wrap);
}

// "다른 질문 보여줘": 새 랜덤 FAQ 칩 블록을 덧붙인다(대화 유지).
export function appendRerollBlock(questions, onAsk) {
  const log = $("#log");
  const wrap = document.createElement("div");
  wrap.className = "faq";
  const intro = document.createElement("p");
  intro.className = "faq-intro";
  intro.textContent = "다른 추천 질문입니다. 궁금한 것을 선택해 주세요.";
  wrap.appendChild(intro);
  if (questions.length) wrap.appendChild(faqRowOf(questions, onAsk));
  log.appendChild(wrap);
  log.scrollTop = log.scrollHeight;
}

// 가이드 언급 시: 안내 가능한 대분류 목록(또는 실패 문구)을 덧붙인다.
export function appendCatalogListBlock(catalogSectionEl) {
  const log = $("#log");
  const wrap = document.createElement("div");
  wrap.className = "faq";
  if (catalogSectionEl) {
    wrap.appendChild(catalogSectionEl);
  } else {
    const p = document.createElement("p");
    p.className = "faq-intro";
    p.textContent = "안내 가능한 가이드 목록을 불러오지 못했습니다.";
    wrap.appendChild(p);
  }
  log.appendChild(wrap);
  log.scrollTop = log.scrollHeight;
}

// ── 선택형 상담 플로우 ───────────────────────────────────────────
// 빠른 링크/바로가기(외부 URL) 칩.
function linkChip(label, url) {
  const a = document.createElement("a");
  a.className = "link-chip";
  a.href = url; a.target = "_blank"; a.rel = "noopener noreferrer";
  a.textContent = label;
  return a;
}

// 첫 화면: 환영 카드 + 카테고리(드릴다운) + 추천 FAQ + 빠른 링크. #log 를 채운다.
export function renderEntryMenu(entry, onSelect) {
  const log = $("#log");
  log.innerHTML = "";
  const wrap = document.createElement("div");
  wrap.className = "consult-entry";

  const hello = document.createElement("div");
  hello.className = "welcome-card";
  hello.textContent = entry.welcome || "";
  wrap.appendChild(hello);

  if (entry.recommended?.length) {
    const rec = document.createElement("div");
    rec.className = "faq";
    const p = document.createElement("p");
    p.className = "faq-intro";
    p.textContent = "자주 묻는 질문";
    rec.appendChild(p);
    const row = document.createElement("div");
    row.className = "faq-row";
    entry.recommended.forEach(n => row.appendChild(makeChip(n.label, "faq-chip", () => onSelect(n.id))));
    rec.appendChild(row);
    wrap.appendChild(rec);
  }

  (entry.categories || []).forEach(cat => {
    const block = document.createElement("div");
    block.className = "cat-block";
    const head = makeChip(cat.label, "cat-chip", () => {
      const open = block.querySelector(".cat-docs");
      if (open) { open.remove(); return; }   // 토글
      const docs = document.createElement("div");
      docs.className = "cat-docs faq-row";
      cat.nodes.forEach(n => docs.appendChild(makeChip(n.label, "faq-chip", () => onSelect(n.id))));
      block.appendChild(docs);
    }, true);
    block.appendChild(head);
    wrap.appendChild(block);
  });

  if (entry.quick_links?.length) {
    const ql = document.createElement("div");
    ql.className = "quick-links";
    entry.quick_links.forEach(l => ql.appendChild(linkChip(l.label, l.url)));
    wrap.appendChild(ql);
  }

  log.appendChild(wrap);
  log.scrollTop = 0;
}

// 확정 답변 카드: 사용자 말풍선(질문) + 좌측 카드(본문·이미지·바로가기·관련·뒤로·출처).
export function renderAnswerCard(card, {onSelect, onBack, showBack}) {
  const log = $("#log");
  if (log.querySelector(".empty") || log.querySelector(".consult-entry")) log.innerHTML = "";

  const turn = document.createElement("div");
  turn.className = "turn";
  turn.innerHTML = `<div class="q">${escapeHtml(card.question)}</div>`
    + `<div class="a card"></div><div class="imgs"></div>`
    + `<div class="links"></div><div class="related"></div>`
    + `<div class="src"></div>`;
  log.appendChild(turn);

  setAnswerText(turn.querySelector(".a"), card.answer);
  renderImages(turn, card.images || []);

  if (card.links?.length) {
    const box = turn.querySelector(".links");
    card.links.forEach(l => box.appendChild(linkChip(l.label, l.url)));
  }

  const rel = turn.querySelector(".related");
  if (showBack && card.parent) {
    rel.appendChild(makeChip("‹ 뒤로", "back-chip", () => onBack()));
  }
  (card.related || []).forEach(r => rel.appendChild(makeChip(r.label, "rel-chip", () => onSelect(r.id))));

  if (card.sources?.length) renderSources(turn, card.sources);
  log.scrollTop = log.scrollHeight;
}

// 자유 입력 → 후보 노드 추천(또는 안내). userText 는 말풍선으로.
export function appendCandidateBlock(userText, candidates, onSelect) {
  appendUserBubble(userText);
  const log = $("#log");
  const wrap = document.createElement("div");
  wrap.className = "faq";
  const p = document.createElement("p");
  p.className = "faq-intro";
  if (candidates.length) {
    p.textContent = "관련 있어 보이는 항목입니다. 선택해 주세요.";
    wrap.appendChild(p);
    const row = document.createElement("div");
    row.className = "faq-row";
    candidates.forEach(c => row.appendChild(makeChip(c.label, "faq-chip", () => { wrap.remove(); onSelect(c.id); })));
    wrap.appendChild(row);
  } else {
    setAnswerText(p, "준비된 안내에서 찾지 못했습니다. e-Class QnA 게시판으로 문의 부탁드립니다.");
    wrap.appendChild(p);
  }
  log.appendChild(wrap);
  log.scrollTop = log.scrollHeight;
}
