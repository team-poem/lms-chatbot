// 세션 저장소. localStorage 를 쓰되 **접근 자체가 실패할 수 있다**는 전제로 감싼다.
//
// 노션 embed 처럼 교차 출처 iframe 안에서 돌 때, 사용자가 서드파티 쿠키·저장소를
// 차단해 두면 localStorage 는 값을 못 읽는 정도가 아니라 **속성 접근에서
// SecurityError 를 던진다**(Chrome·Safari 공통). main.js 는 모듈 최상위에서 세션을
// 읽으므로, 던지는 순간 그 아래 초기화가 전부 중단되고 화면이 백지가 된다.
// 2026-08-19 에 캐시 스큐로 똑같은 증상을 겪었다 — 원인은 달라도 결과는 같다.
//
// 실패하면 메모리로 떨어진다. 탭을 닫으면 세션이 사라질 뿐 챗봇은 정상 동작한다.
// 저장이 안 되는 것보다 화면이 안 뜨는 것이 훨씬 나쁘다.
const memory = new Map();

export function getItem(key) {
  try {
    return localStorage.getItem(key);
  } catch {
    return memory.has(key) ? memory.get(key) : null;
  }
}

export function setItem(key, value) {
  memory.set(key, value);   // 항상 메모리에도 둔다 — localStorage 가 중간에 막혀도 이어진다
  try {
    localStorage.setItem(key, value);
  } catch {
    /* 차단·용량 초과. 메모리 값으로 계속 간다. */
  }
}
