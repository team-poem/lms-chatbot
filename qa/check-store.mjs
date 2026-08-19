// static/js/store.js 자체 점검. 프레임워크 없이 node 로 바로 돈다.
//
//   npm run qa:store
//
// 표적은 하나다: localStorage 접근이 **던져도** 챗봇이 계속 도는가.
// 노션 embed 처럼 교차 출처 iframe 에서 서드파티 저장소가 차단되면 실제로 던진다.
import assert from "node:assert/strict";

const MOD = new URL("../static/js/store.js", import.meta.url).href;

function throwingLocalStorage() {
  // 차단된 환경의 재현: 속성 접근 시점에 SecurityError 가 난다.
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    get() {
      throw new DOMException("The operation is insecure.", "SecurityError");
    },
  });
}

function workingLocalStorage() {
  const map = new Map();
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: k => (map.has(k) ? map.get(k) : null),
      setItem: (k, v) => map.set(k, String(v)),
    },
  });
  return map;
}

globalThis.DOMException ??= class DOMException extends Error {
  constructor(msg, name) { super(msg); this.name = name; }
};

// 1) 정상 환경 — localStorage 에 실제로 쓴다.
const map = workingLocalStorage();
const ok = await import(MOD + "?case=ok");
ok.setItem("lms_session", "sid-1");
assert.equal(map.get("lms_session"), "sid-1", "정상 환경에서는 localStorage 에 써야 한다");
assert.equal(ok.getItem("lms_session"), "sid-1");
assert.equal(ok.getItem("없는키"), null);

// 2) 차단 환경 — 던지지 않고 메모리로 떨어진다.
throwingLocalStorage();
const blocked = await import(MOD + "?case=blocked");
assert.doesNotThrow(() => blocked.setItem("lms_session", "sid-2"), "setItem 이 던지면 모듈이 죽는다");
assert.doesNotThrow(() => blocked.getItem("lms_session"), "getItem 이 던지면 모듈이 죽는다");
assert.equal(blocked.getItem("lms_session"), "sid-2", "메모리로 이어져야 한다");
assert.equal(blocked.getItem("없는키"), null);

// 3) 중간에 막혀도 이미 넣은 값은 유지된다.
workingLocalStorage();
const mid = await import(MOD + "?case=mid");
mid.setItem("lms_label", "김교수");
throwingLocalStorage();
assert.equal(mid.getItem("lms_label"), "김교수", "저장소가 중간에 막혀도 세션이 이어져야 한다");

console.log("OK — store.js 9 checks passed");
