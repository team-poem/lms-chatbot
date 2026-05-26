# 맥미니 배포 가이드

LMS 챗봇을 맥미니에 도커로 배포하고 운영하는 절차서.

## 아키텍처
```
[Mac mini]
├── Ollama (native, brew install)   ← Metal GPU 가속
│   └── gemma3:4b
└── Docker
    └── lms-chatbot 컨테이너
        ├── FastAPI (port 8080)
        ├── BGE-M3 임베딩 (이미지에 baked)
        └── 데이터 디렉터리는 호스트에서 볼륨 마운트
```

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

### 2.1 Ollama
```bash
brew install ollama
brew services start ollama
ollama pull gemma3:4b      # 3.3GB, 1회만
```

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
```

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
| `/chat` 호출 후 5분 무응답 + 404 | Ollama 가 안 떠 있음. `ollama list` 로 확인, `brew services restart ollama` |
| `Connection refused` to ollama | `host.docker.internal` 매핑 실패. compose 의 `extra_hosts` 항목 유지 필요 |
| 첫 부팅 후 `/health` 503 | BGE-M3 로드 중 (최대 2분). `start_period: 180s` 동안 unhealthy 정상 |
| 응답이 느림 (>30초) | gemma3:4b 콜드 스타트. Ollama 의 `keep_alive` 기본 5분이라 이후엔 빠름 |
| 디스크 부족 | `docker system prune -a -f` 로 옛 이미지 정리 |
| 이미지 푸시 실패 (denied) | `docker login -u amazon7737` 재로그인. Docker Hub 계정 활성 상태 확인 |
