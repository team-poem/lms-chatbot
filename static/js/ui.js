// 프레젠테이션 계층: DOM 생성·렌더만 담당한다. 서버 통신 없음(콜백 주입).

export const $ = (s) => document.querySelector(s);

export function escapeHtml(s) { return s.replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c])); }

// 답변 텍스트를 렌더한다(평문). 단 게시판 문구('e-Class QnA 게시판', 'Q&A 바로가기'
// 등)는 게시판 하이퍼링크로 건다 — 안내 시 게시판으로 바로 이동할 수 있게.
const QNA_LINK_PHRASES = ["e-Class QnA 게시판", "Q&A 바로가기", "Q&A 게시판"];
export function setAnswerText(el, text, qnaBoardUrl) {
  let html = escapeHtml(text);
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

// ── 입력/모달 게이트 ─────────────────────────────────────────────
export function setChatEnabled(enabled) {
  $("#q").disabled = !enabled;
  $("#form button[type=submit]").disabled = !enabled;
}

export function showConsentModal(show) {
  $("#modal").style.display = show ? "flex" : "none";
}

export function setUserLabel(label) { $("#user-label").textContent = label; }

export function focusComposer() { $("#q").focus(); }

export function renderDenied() {
  document.body.innerHTML = "<div style='padding:40px;text-align:center'>동의하지 않으시면 챗봇을 사용하실 수 없습니다.</div>";
}

// ── 대화 턴 ──────────────────────────────────────────────────────
export function appendUserBubble(text) {
  const log = $("#log");
  if (log.querySelector(".empty")) log.innerHTML = "";
  const div = document.createElement("div");
  div.className = "turn";
  div.innerHTML = `<div class="q">${escapeHtml(text)}</div>`;
  log.appendChild(div);
}

// 질문 말풍선 + 로딩 점 3개 + 빈 답변/이미지/출처/피드백 영역을 가진 턴 스켈레톤.
export function appendTurnSkeleton(query) {
  const log = $("#log");
  if (log.querySelector(".empty")) log.innerHTML = "";
  const div = document.createElement("div");
  div.className = "turn";
  div.innerHTML = `<div class="q">${escapeHtml(query)}</div><div class="a"><span class="loading"><span class="dot"></span><span class="dot"></span><span class="dot"></span></span></div><div class="imgs"></div><div class="src"></div><div class="fb"></div>`;
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

export function faqRowOf(questions, onAsk) {
  const row = document.createElement("div");
  row.className = "faq-row";
  questions.forEach(q => row.appendChild(makeChip(q, "faq-chip", () => onAsk(q))));
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

// 첫 진입 화면: 인트로 + 랜덤 FAQ 칩 + (있으면) 가이드 대분류 섹션. 로그를 비우고 채운다.
export function renderEntry(questions, catalogSectionEl, onAsk) {
  const log = $("#log");
  log.innerHTML = "";
  const wrap = document.createElement("div");
  wrap.className = "faq";
  const intro = document.createElement("p");
  intro.className = "faq-intro";
  intro.textContent = "저는 동서대학교 LMS 교수자 가이드를 담당하고 있습니다. 아래와 같은 질문을 주시면 빠르게 답변해 드립니다.";
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
