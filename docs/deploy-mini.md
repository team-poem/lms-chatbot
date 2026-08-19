# 맥미니 배포 가이드

LMS 챗봇을 맥미니에 도커로 배포하고 운영하는 절차서.

## 아키텍처
```
[Mac mini]
└── Docker
    └── lms-chatbot 컨테이너
        ├── FastAPI (port 8080)
        ├── BGE-M3 임베딩 (이미지에 baked, 로컬 추론)
        ├── 답변 생성 → Gemini API (외부 호출)
        └── 데이터 디렉터리는 호스트에서 볼륨 마운트
```

답변 생성이 Gemini API 로 넘어가면서 맥미니에 Ollama 를 띄울 필요가 없어졌다
(2.1 절 삭제). 임베딩은 여전히 컨테이너 안에서 로컬로 돈다 — 인덱스 벡터 공간을
바꾸지 않기 위해서다. 되돌리려면 `.env` 에 `LLM_PROVIDER=ollama` 를 넣고 아래
"부록: Ollama 로 되돌리기" 를 따른다.

## 1회만 — 개발 머신 셋업

### 1.1 Docker Hub 인증
이미 Docker Desktop 에 `amazon7737` 으로 로그인되어 있으면 추가 작업 불필요.
확인: `cat ~/.docker/config.json` → `credsStore: desktop` + Docker Desktop 우상단 사용자 메뉴.

문제 시:
```bash
docker login -u amazon7737
```

### 1.2 buildx 확인 (Docker Desktop 기본 설치되어 있음)
```bash
docker buildx version
```

### 1.3 이미지 빌드 + 푸시 (3~10분 소요, 첫 빌드는 더 오래)
```bash
./scripts/build-and-push.sh           # latest 태그
./scripts/build-and-push.sh v0.2      # 버전 명시
```

이미지 크기 약 **3.5GB** (BGE-M3 모델 포함). 첫 푸시 시간은 회선에 따라.

이미지는 `hub.docker.com/r/amazon7737/lms-chatbot` 에 올라감.

## 1회만 — 맥미니 셋업

### 2.1 Gemini API 키
https://aistudio.google.com/apikey 에서 발급받아 2.4 의 `.env` 에 넣는다.
맥미니에 별도 설치할 런타임은 없다.

### 2.2 Docker Desktop
```bash
brew install --cask docker
open -a Docker            # 첫 실행 시 권한 동의 + Apple Silicon 자동 인식
```

### 2.3 Docker Hub 로그인 (또는 Docker Desktop 에서 GUI 로그인)
```bash
docker login -u amazon7737
```

### 2.4 배포 디렉터리 + 데이터 + compose
```bash
mkdir -p ~/lms-chatbot && cd ~/lms-chatbot

# docker-compose.yml 가져오기 (private repo 라 gh auth 필요하거나, scp 로 옮기기)
# 가장 간단: 개발 머신에서 scp 로 한 번에 보내기
#   scp docker-compose.yml <user>@<mini-ip>:~/lms-chatbot/
# 또는 repo 가 public 이면:
#   curl -fsSLO https://raw.githubusercontent.com/team-poem/lms-chatbot/main/docker-compose.yml

# 인덱스 데이터 옮기기: 개발 머신에서 만든 것을 그대로 보내기
# 개발 머신에서:
#   scp -r data/chroma data/bm25.pkl data/assets <user>@<mini-ip>:~/lms-chatbot/data/
# 맥미니에서 빈 SQLite 로그 파일 생성:
mkdir -p data
touch data/chat_logs.db

# compose 가 읽을 .env — 키는 이미지에 굽지 않고 여기서 주입한다
cat > .env <<'EOF'
GEMINI_API_KEY=<발급받은 키>
# 예비 키(선택). 무료 티어 제한은 키마다 따로 차므로, 앞 키가 429 면 기다리지 않고
# 다음 키로 넘어간다. 학기 초처럼 몰리는 구간에서 폴백 문구가 뜨는 것을 줄인다.
GEMINI_API_KEY2=
GEMINI_API_KEY3=
# 관리자 토큰. 비우면 /admin/logs 와 /admin/usage 가 404 라 **오늘 얼마나 쓰였는지
# 볼 수단이 없다.** 요청 상한을 걸어두고 소진 여부를 못 보면 비용 사고를 사후에도
# 모른다. 운영에서는 반드시 강한 값으로 채울 것 — openssl rand -hex 24
ADMIN_TOKEN=<강한 무작위 문자열>
EOF
chmod 600 .env
```

### 2.4-b 운영 스위치 (선택 — 기본값으로도 동작한다)

`.env` 에 추가하면 compose 가 컨테이너로 넘긴다. 값을 넣지 않으면 괄호 안 기본값이다.

| 변수 | 기본 | 용도 |
|---|---|---|
| `RL_CHAT_PER_SESSION` | 100 | 한 세션이 보낼 수 있는 질문 수 |
| `RL_CONSENT_PER_IP_HOUR` | 100 | IP당 시간당 세션 발급 수 |
| `RL_CHAT_PER_DAY` | 3000 | **전체 일일 질문 수 — 비용 최종 방어선** |
| `EMBED_PROVIDER` | `local` | 임베딩 백엔드. 아래 경고 참조 |
| `GEMINI_MODEL` | `gemini-2.5-flash` | 생성 모델. `-latest` 별칭 금지 |
| `QNA_BOARD_URL` | (내장) | 매뉴얼 밖 질문 안내용 게시판 |

`/chat` 은 호출마다 Gemini 과금이고 `/consent` 는 인증 없이 세션을 발급한다. 공개
노출 시 위 `RL_*` 이 유일한 비용 방어선이다. 캠퍼스망은 NAT 뒤에 여러 사용자가 한
IP 를 쓰므로 `RL_CONSENT_PER_IP_HOUR` 를 빡빡하게 조이면 강의동 하나가 통째로 막힌다.

오늘 사용량 확인:

```bash
curl -s -H "X-Admin-Token: <ADMIN_TOKEN>" http://localhost:8080/admin/usage
# {"chat_today": 42, "chat_per_day": 3000, "sessions_tracked": 7}
```

> ⚠️ **`EMBED_PROVIDER` 를 바꾸면 `data/chroma` 를 반드시 같은 백엔드로 재인덱싱해야
> 한다.** 인덱스와 조회 백엔드가 어긋나면 검색이 실패하는 게 아니라 **엉뚱한 문서를
> 자신 있게 찾아온다 — 에러도 로그도 없다.** `tuning.py` 의 유사도 임계값도 함께
> 재보정해야 한다(`docs/baselines/` 와 `scripts/embed_baseline.py` 참조).
> 현재 배포 이미지는 `local`(BGE-M3) 기준이다.

> **모델 버전은 고정한다.** `GEMINI_MODEL` 에 `-latest` 별칭을 넣지 말 것 —
> 2026-08-12 확인 결과 별칭이 넘어가면서 API 계약까지 바뀌어 생성이 통째로 실패했다
> (`docs/2026-08-12-model-alias-decision.md`).

### 2.5 실행
```bash
docker compose pull
docker compose up -d

# 로그 확인 (BGE-M3 모델 로드 약 10~20초 — startup hook 출력 보임)
docker compose logs -f

# 브라우저
open http://localhost:8080
```

## 운영

### 코드/이미지 업데이트
개발 머신에서:
```bash
git pull            # 변경 받아서
./scripts/build-and-push.sh v0.3
```
맥미니에서:
```bash
# docker-compose.yml 의 image 태그를 :v0.3 으로 바꾸거나 :latest 그대로 두고
docker compose pull
docker compose up -d   # 무중단 재시작
```

### 가이드 문서 업데이트 (인덱스 재빌드)
가이드 변경은 데이터 갱신이라 이미지 재빌드 불필요. 개발 머신에서 인덱싱한 결과를 그대로 복사:
```bash
# 개발 머신
.venv/bin/python -m ingest.cli       # data/chroma, bm25.pkl, assets 재생성
rsync -av --delete data/chroma data/assets data/bm25.pkl <user>@<mini-ip>:~/lms-chatbot/data/

# 맥미니
docker compose restart       # 컨테이너 인덱스 핸들 새로 잡게 재시작
```

### 로그 / 통계
대화 로그는 호스트 `~/lms-chatbot/data/chat_logs.db` 에 SQLite 로 누적. 그대로 백업 가능.

```bash
sqlite3 ~/lms-chatbot/data/chat_logs.db "SELECT COUNT(*) FROM turns;"
```

### 중단 / 제거
```bash
docker compose down              # 정지
docker compose down -v           # 정지 + 볼륨 제거 (데이터는 호스트에 있어서 영향 없음)
docker rmi ghcr.io/team-poem/lms-chatbot:latest  # 이미지 삭제
```

## 트러블슈팅

| 증상 | 원인 / 해결 |
|------|-------------|
| 부팅 즉시 크래시 + `GEMINI_API_KEY 가 비어 있습니다` | `.env` 의 키 누락. compose 는 호스트 `.env` 를 읽는다 (`docker compose config` 로 주입 확인). `GEMINI_API_KEY2·3` 은 선택이라 비어도 된다 |
| 로그에 `429 — 다음 키로 전환 (키 #2/3)` | 1번 키 쿼터 소진. 정상 동작이다(자동 전환). 자주 보이면 키를 늘리거나 `RL_*` 상한을 조인다 |
| 답변이 계속 비고 폴백 문구만 나옴 | Gemini 401/429. `docker compose logs` 확인 — 관련성 게이트는 예외를 삼키므로(통과 정책) 증상이 빈 답변으로만 보인다 |
| 첫 부팅 후 `/health` 503 | BGE-M3 로드 중 (최대 2분). `start_period: 180s` 동안 unhealthy 정상 |
| 응답이 느림 (>30초) | 네트워크 또는 Gemini 지연. `LLM_PROVIDER=ollama` 로 돌린 상태면 gemma3:4b 콜드 스타트(`keep_alive` 기본 5분) |
| 디스크 부족 | `docker system prune -a -f` 로 옛 이미지 정리 |
| 이미지 푸시 실패 (denied) | `docker login -u amazon7737` 재로그인. Docker Hub 계정 활성 상태 확인 |

## 부록: Ollama 로 되돌리기

외부 API 를 못 쓰는 상황(망 분리·비용)에서의 탈출구. 이미지 재빌드는 필요 없다.

```bash
brew install ollama && brew services start ollama
ollama pull gemma3:4b                      # 3.3GB
echo 'LLM_PROVIDER=ollama' >> ~/lms-chatbot/.env
docker compose up -d
```

compose 의 `extra_hosts: host.docker.internal` 매핑이 이 경로에서만 쓰인다 — Gemini
로 운영하더라도 항목은 지우지 말 것.
