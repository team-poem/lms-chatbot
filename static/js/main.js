// 엔트리: 세션 상태(localStorage)·이벤트 바인딩을 소유하고 api(통신)와 ui(렌더)를 잇는다.
import * as api from "./api.js";
import * as ui from "./ui.js";

let session = null;
const CONSULT = new URLSearchParams(location.search).get("mode") === "consult";
const navStack = [];          // 방문한 노드 id (뒤로가기)
const cardCache = new Map();  // id → card (뒤로 시 재요청·재로그 없음)
// 폴백 답변의 'e-Class QnA 게시판' 문구를 하이퍼링크로 걸 때 쓸 게시판 URL(로드 시 1회 조회).
let qnaBoardUrl = "";
api.fetchHealth().then(d => { qnaBoardUrl = d.qna_board_url || ""; });

let catalogCache = null;
async function loadCatalog() {
  if (catalogCache) return catalogCache;
  catalogCache = await api.fetchCatalog();
  return catalogCache;
}

// 2뎁스 전개: CMS 문서는 manual='CMS' 스코프로 보내 LMS 검색에 섞이지 않게
// 한다(LMS 는 자동 라우팅이라 스코프 생략).
function onPickCategory(manualName, cat) {
  const scope = manualName === "LMS" ? undefined : manualName;
  ui.appendCategoryBlock(cat, doc => ask(doc, scope));
}

// 세션 발급. /consent 는 서버에 동의 버전을 기록하는 자리이기도 하다 — 모달을
// 걷어냈어도 이 호출은 남긴다(무엇을 어느 버전으로 고지했는지의 기록).
// 고지 본문은 푸터의 /privacy 링크가 상시 제공한다.
async function newSession(userLabel) {
  const d = await api.postConsent(userLabel);
  session = d.session_id;
  localStorage.setItem("lms_session", session);
  localStorage.setItem("lms_consent", d.consent_version);
  if (userLabel) {
    localStorage.setItem("lms_label", userLabel);
    ui.setUserLabel(userLabel);
  }
  return d;
}

async function start() {
  await newSession(null);
  ui.setChatEnabled(true);
  ui.focusComposer();
  if (CONSULT) enterMenu(); else showFaqSuggestions();
}

// ── 선택형 상담 모드 (?mode=consult) ────────────────────────────
async function enterMenu() {
  const entry = await api.fetchEntry();
  navStack.length = 0;
  if (!entry) { ui.renderEntry([], null, ask); return; }   // 폴백: 레거시 진입
  ui.renderEntryMenu(entry, selectNode);
}

async function selectNode(id) {
  let card = cardCache.get(id);
  if (!card) {
    const stopLoading = ui.appendLoading(null, "안내를 불러오는 중");  // 캐시 히트는 즉답이라 생략
    card = await api.fetchAnswer(id);
    stopLoading();
    if (!card) { return; }
    cardCache.set(id, card);
  }
  navStack.push(id);
  ui.renderAnswerCard(card, {
    onSelect: selectNode,
    onBack: goBack,
    showBack: navStack.length > 1,
  });
}

function goBack() {
  navStack.pop();                       // 현재 제거
  const prev = navStack.pop();          // 직전(다시 push 됨)
  if (prev) selectNode(prev);
  else enterMenu();
}

async function consultSearch(q) {
  const stopLoading = ui.appendLoading(q, "관련 항목을 찾는 중");
  const candidates = await api.searchNodes(q);
  stopLoading();
  ui.appendCandidateBlock(q, candidates, selectNode);
}

async function ask(query, manual) {
  const {div, removeLoading} = ui.appendTurnSkeleton(query, "가이드를 찾는 중");

  const body = {session_id: session, query};
  // 가이드 네비에서 CMS 문서를 누른 경우만 manual='CMS' 로 스코프 전송. LMS/자유
  // 입력은 생략 → 서버가 직접 언급 라우팅(기본 LMS)으로 처리.
  if (manual) body.manual = manual;
  const resp = await api.postChat(body);
  // 세션이 서버에 없으면(컨테이너 재시작·DB 리셋으로 캐시 세션이 만료) 403.
  // 옛 세션을 비우고 동의 모달을 다시 띄워 재동의 → 새 세션을 받게 한다.
  // 컨테이너 재시작·DB 리셋으로 캐시 세션이 서버에 없으면 403. 새 세션을 바로
  // 발급하고 다시 물어봐 달라고만 안내한다(여기서 자동 재전송하면 실패가 반복될
  // 때 무한 루프가 된다).
  if (resp.status === 403) {
    removeLoading();
    await newSession(localStorage.getItem("lms_label"));
    ui.setAnswerPlain(div, "연결이 끊겨 새로 시작했습니다. 한 번만 다시 물어봐 주세요.");
    return;
  }
  if (!resp.ok || !resp.body) {
    removeLoading();
    ui.setAnswerPlain(div, "일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.");
    return;
  }
  for await (const evt of api.sseEvents(resp)) {
    if (evt.type === "text") {
      removeLoading();
      ui.appendAnswerDelta(div, evt.delta);
    } else if (evt.type === "text_final") {
      removeLoading();
      ui.setAnswerText(div.querySelector(".a"), evt.text, qnaBoardUrl);
    } else if (evt.type === "done") {
      removeLoading();
      ui.renderImages(div, evt.images);
      if (evt.sources?.length) ui.renderSources(div, evt.sources);
    } else if (evt.type === "turn_id") {
      ui.renderFeedback(div, evt.turn_id, (tid, rating) => api.postFeedback(tid, rating));
    }
  }
}

// 첫 진입 화면: 랜덤 FAQ 칩 + 가이드 대분류 네비.
async function showFaqSuggestions() {
  const questions = await api.fetchFaqQuestions();
  const sec = ui.buildCatalogSection(
    await loadCatalog(),
    "이외에도 아래 주제들을 안내해 드릴 수 있습니다. 주제를 선택하면 세부 항목을 보여드립니다.",
    onPickCategory);
  if (!questions.length && !sec) return;
  ui.renderEntry(questions, sec, ask);
}

async function appendRerollSuggestions(userText) {
  ui.appendUserBubble(userText);
  const questions = await api.fetchFaqQuestions();
  ui.appendRerollBlock(questions, ask);
}

async function appendCatalogList(userText) {
  ui.appendUserBubble(userText);
  const sec = ui.buildCatalogSection(
    await loadCatalog(),
    "아래와 같은 가이드를 안내해 드릴 수 있습니다. 주제를 선택해 주세요.",
    onPickCategory);
  ui.appendCatalogListBlock(sec);
}

// "다른/또 추천 질문 보여줘" → 랜덤 FAQ 리롤. "가이드/매뉴얼 뭐 있어" → 대분류 목록.
const RE_REROLL = /(다른|또|새|다시)\s*(추천\s*)?질문|질문\s*(다시|더|또)/;
const RE_GUIDE = /(가이드|매뉴얼|메뉴얼)\s*(목록|리스트|종류|항목|뭐|무엇|어떤|있|보여|안내)|(뭐|무슨|어떤|무엇)\s*(가이드|매뉴얼|메뉴얼)|^\s*(가이드|매뉴얼|메뉴얼)\s*$/;

ui.$("#form").addEventListener("submit", e => {
  e.preventDefault();
  const q = ui.$("#q").value.trim();
  if (!q) return;
  ui.$("#q").value = "";
  if (CONSULT) { consultSearch(q); return; }
  if (RE_REROLL.test(q)) { appendRerollSuggestions(q); return; }
  if (RE_GUIDE.test(q)) { appendCatalogList(q); return; }
  ask(q);
});

ui.$("#purge").addEventListener("click", async e => {
  e.preventDefault();
  if (!session) return;
  if (!confirm("이 세션의 대화 기록을 모두 삭제합니다. 진행할까요?")) return;
  await api.postPurge(session);
  localStorage.removeItem("lms_session");
  localStorage.removeItem("lms_consent");
  localStorage.removeItem("lms_label");
  location.reload();
});

ui.initLightbox();

const saved = localStorage.getItem("lms_session");
if (saved) {
  session = saved;
  ui.setChatEnabled(true);
  const lbl = localStorage.getItem("lms_label");
  if (lbl) ui.setUserLabel(lbl);
  if (CONSULT) enterMenu(); else showFaqSuggestions();
} else {
  start();
}
