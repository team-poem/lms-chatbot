// 서버 통신 계층: fetch 와 SSE 파싱만 담당한다. DOM 을 만지지 않는다.

export async function fetchHealth() {
  try {
    const r = await fetch("/health");
    return await r.json();
  } catch (e) { return {}; }
}

export async function postConsent(userLabel) {
  const r = await fetch("/consent", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify({user_label: userLabel})});
  return r.json();
}

export function postChat(body) {
  return fetch("/chat", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(body)});
}

// /chat 응답 본문(SSE)을 이벤트 객체 단위로 흘리는 async generator.
export async function* sseEvents(resp) {
  const reader = resp.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  while (true) {
    const {value, done} = await reader.read();
    if (done) break;
    buf += dec.decode(value, {stream: true});
    const lines = buf.split("\n\n");
    buf = lines.pop();
    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      yield JSON.parse(line.slice(6));
    }
  }
}

export async function fetchFaqQuestions() {
  try {
    const r = await fetch("/faq");
    if (r.ok) return (await r.json()).questions || [];
  } catch (e) {}
  return [];
}

export async function fetchCatalog() {
  try {
    const r = await fetch("/catalog");
    return r.ok ? ((await r.json()).manuals || []) : [];
  } catch (e) { return []; }
}

export function postFeedback(turnId, rating) {
  return fetch("/feedback", {
    method: "POST",
    headers: {"content-type": "application/json"},
    body: JSON.stringify({turn_id: turnId, rating}),
  });
}

export function postPurge(sessionId) {
  return fetch("/purge", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify({session_id: sessionId})});
}

export async function fetchEntry() {
  try { const r = await fetch("/entry"); return r.ok ? await r.json() : null; }
  catch (e) { return null; }
}

export async function fetchAnswer(id) {
  try { const r = await fetch(`/answer/${encodeURIComponent(id)}`); return r.ok ? await r.json() : null; }
  catch (e) { return null; }
}

export async function searchNodes(q) {
  try {
    const r = await fetch(`/search?q=${encodeURIComponent(q)}`);
    return r.ok ? ((await r.json()).candidates || []) : [];
  } catch (e) { return []; }
}
