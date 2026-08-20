---
name: notion-sync
description: 노션 매뉴얼 변경분을 수집해 챗봇 인덱스를 갱신한다. "노션 갱신", "매뉴얼 갱신", "notion sync", "데이터 갱신해줘" 가 트리거. Notion MCP(notion 서버) 연결이 전제이며, 수집→재인덱싱→검증까지 하고 배포(rsync)는 사용자 몫으로 넘긴다.
---

# 노션 → 챗봇 인덱스 갱신

노션에서 고친 매뉴얼을 챗봇이 알게 만드는 절차. 카탈로그·상담 노드·자동 핀은
전부 인덱스에서 기동 시 도출되므로, **이 절차 + 서버 재시작이면 코드 수정 없이
끝난다.**

## 갱신 가능 범위 (정직하게)

| 소스 | 접근 | 비고 |
|---|---|---|
| LMS 매뉴얼 트리 | ✅ MCP | TOC: page `42c457931cd28376a857813f9ab4ecec` (Joh's Notion) |
| LMS FAQ DATABASE | ❌ 404 | 옛 계보(`3560163e…`) — 이 MCP 연결의 워크스페이스에 없음 |
| CMS 매뉴얼 | ❌ 404 | 같은 이유(`34f0163e…`) |

FAQ·CMS 가 바뀌면 노션 export 를 받아 `data/raw` 에 교체하거나, 해당 페이지를
연결된 워크스페이스로 공유받아야 한다. 모르면 사용자에게 물어라.

## 사전 조건

- `mcp__notion__notion-fetch` 사용 가능(지연 로드면 ToolSearch 로 먼저 로드).
  없으면: `claude mcp list` 로 notion 연결 확인 → 세션 재시작 필요를 알려라.
- 앱 루트(이 저장소)의 `.venv` 존재. 이하 모든 경로는 앱 루트 기준.

## 절차

### 1. 원격 목록 → 대조 계획

1. TOC 페이지를 fetch 하고 `sync.mcp_md.toc_markdown` 으로 (md, 자식 목록)을 얻는다.
2. 자식 목록을 `[{"page_id":…, "title":…}]` JSON 으로 저장하고 대조한다:
   ```bash
   .venv/bin/python scripts/sync_manifest.py plan <원격목록.json>
   ```
   신규/삭제는 여기서 확정된다. TOC 는 수정 시각을 주지 않으므로 기존 문서는
   '확인필요'로 나온다 — 실변경 여부는 4단계의 내용 해시로 가른다.
3. TOC 자체가 바뀌었으면(카테고리·문서 추가/삭제) 변환된 TOC md 로
   `data/raw/Private & Shared/LMS 매뉴얼 <TOC id>.md` 를 교체한다.

### 2. 문서 수집 (문서당, 순서 엄수)

1. `notion-fetch` 로 페이지를 받는다.
2. 응답 text 의 `<content>…</content>` 구간을 **한 글자도 바꾸지 말고** 임시
   파일로 저장한다(Write). 이미지 서명 URL 이 깨지면 다운로드가 전부 실패한다.
3. **즉시** 변환한다 — 이미지 URL 이 fetch 후 5분에 만료된다:
   ```bash
   .venv/bin/python scripts/mcp_ingest_doc.py <임시파일> <page_id> "<제목>" "LMS 매뉴얼"
   ```
   제목 끝의 `(📄)` 류 장식은 떼고 넘긴다. 스크립트가 `/`→`-` 등 파일명
   위생 처리를 한다. 이미지 실패 시 종료코드 1 — 그 문서만 fetch 부터 재시도(2회).
4. 문서가 10편 넘으면 수집 서브에이전트로 분할하라(2026-08-19 에 3×27 검증).
   에이전트 지침에 반드시: 코드 수정 금지 / git 금지 / ingest 금지 / fetch→변환
   지체 금지. 완료 후 **디스크 기준으로 검수하라** — 에이전트의 "성공" 보고와
   파일 개수가 어긋난 실사례가 있다.

### 3. 삭제 반영

plan 의 [삭제] 항목은 노션에서 사라진 문서다. 해당 md 와 같은 이름의 이미지
폴더를 `data/raw` 에서 지운다. 확신이 없으면 지우기 전에 사용자에게 목록을 보여라.

### 4. 실변경 판별 → 재인덱싱

받아온 문서가 실제로 바뀌었는지 내용 해시로 가른다(공백·표기 차이는 안 잡힘):
```bash
.venv/bin/python scripts/sync_manifest.py hash "<변환된 md 경로>"   # 장부의 content_hash 와 비교
```
바뀐 것이 하나라도 있으면:
```bash
.venv/bin/python -m ingest.cli                      # 재인덱싱 (data/chroma·bm25.pkl·assets)
.venv/bin/python scripts/embed_baseline.py          # 검색 품질 실측
.venv/bin/python scripts/sync_manifest.py scan      # 장부 갱신
```
기준선 분리도(separation)가 직전 기록(`docs/baselines/`)보다 눈에 띄게 떨어지면
**멈추고 보고하라** — 인덱스가 상했다는 신호다.

### 5. 로컬 검증

서버를 재시작하고(카탈로그·핀은 기동 시 1회 도출) 기동 로그를 본다:
```
[startup] 노드 레지스트리 N개
[startup] 핀 답변 N개          ← '카탈로그 핀 대상 없음' 이 찍히면 그 문서를 조사하라
```
`/catalog` 응답과, 바뀐 문서 1~2건을 `/chat` 에 실호출해 확인한다.

### 6. 배포 핸드오프 (사용자 몫)

맥미니 접속은 못 하므로 아래를 안내하고 끝낸다. **실호스트 주소를 저장소·PR 에
쓰지 마라**(2026-08-19 결정 — 플레이스홀더 사용):
```bash
rsync -av --delete data/chroma data/assets data/bm25.pkl "data/raw/Private & Shared" <user>@<배포호스트>:~/lms-chatbot/data/
# 맥미니에서: docker compose restart
# 확인: curl -s https://<배포호스트>/health  +  기동 로그의 핀 개수
```

## 자주 밟는 함정

- **이미지 만료(5분)**: fetch 와 변환 사이에 다른 작업을 끼우지 마라.
- **제목 표기 흔들림**: `/`·`?`·`.` 는 소스마다 다르게 떨어진다. 조인은
  `generation/nodes._norm` 이 접어주지만, 새 변형이 보이면 `_norm` 과
  `tests/test_nodes.py` 의 접기 테스트에 추가하라.
- **빈 답변**: 수집 직후 답변이 비면 인덱스가 아니라 Gemini 쪽 일시 오류일 수
  있다(서버 로그 확인). 빈 답변은 폴백으로 변환된다(stream.py 가드).
- **`data/` 는 git 밖이다**: 수집 결과는 커밋 대상이 아니다. 커밋할 것은 코드·
  스킬·기준선 기록(`docs/baselines/`)뿐.
