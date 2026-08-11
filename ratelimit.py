"""요청 상한. Gemini API 과금이 무방비로 열리는 것을 막는 3층 방어.

위협은 트래픽이 아니라 **돈**이다. /consent 는 인증 없이 세션을 무제한 발급하고
/chat 은 그 세션으로 매번 Gemini 를 호출하므로, 공개 배포되는 순간 누구든(또는
크롤러가) 청구서를 열 수 있다.

층을 셋으로 나눈 이유 — 어느 하나도 혼자서는 충분하지 않다:

  1. 세션당 질문 수: 한 세션의 폭주를 막는다. 세션을 새로 파면 우회된다.
  2. IP당 세션 발급(시간당): 위 우회를 막는다. 다만 **대학 캠퍼스망은 NAT 뒤에
     여러 사용자가 한 IP 를 공유**하므로 넉넉히 잡아야 한다. 빡빡하게 걸면 강의동
     하나가 통째로 막힌다.
  3. 전체 일일 질문 수: 비용의 최종 백스톱. 1·2 를 모두 우회당해도 하루치 손실로
     막힌다. 대가는 소진 시 정상 사용자도 막힌다는 것인데, '돈이 계속 새는 것'
     보다는 '하루 멈추는 것'이 낫다는 판단이다(로그에 남으므로 감지도 된다).

각 상한은 0 으로 두면 비활성이다. 카운터는 메모리에 있고 프로세스 수명을 따른다
— **uvicorn 워커가 여럿이면 워커 수만큼 실질 상한이 곱해진다.** 현재 배포는
단일 워커(docker-compose)라 문제없지만, 워커를 늘리면 Redis 같은 공유 저장소로
옮겨야 한다.
"""
from __future__ import annotations
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))


@dataclass(frozen=True)
class Limits:
    """0 = 해당 층 비활성."""
    chat_per_session: int = 100
    consent_per_ip_hour: int = 100
    chat_per_day: int = 3000


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str = ""
    retry_after: int = 0   # 초. 0 이면 힌트 없음.


def _kst_date(now: datetime) -> str:
    return now.astimezone(KST).strftime("%Y-%m-%d")


def _hour_bucket(now: datetime) -> str:
    return now.astimezone(KST).strftime("%Y-%m-%dT%H")


class RateLimiter:
    """스레드 안전 카운터. FastAPI 의 동기 엔드포인트가 스레드풀에서 도는 것을
    고려해 락을 건다."""

    def __init__(self, limits: Limits | None = None):
        self.limits = limits or Limits()
        self._lock = threading.Lock()
        # 카운터는 전부 시각 버킷에 묶어 두고, 버킷이 넘어가는 순간 옛것을 버린다.
        # 이렇게 하지 않으면 상시 가동 서버에서 무한히 쌓인다 — 세션 카운터는
        # /purge 를 부르는 사용자만 정리되는데 대부분 부르지 않는다.
        self._session_chats: dict[str, int] = {}
        self._session_day = ""                               # 위 dict 가 속한 KST 날짜
        self._ip_consents: dict[str, int] = {}               # ip → 수
        self._ip_hour = ""                                   # 위 dict 가 속한 시각 버킷
        self._day_chats: tuple[str, int] = ("", 0)           # (KST 날짜, 수)

    # ── 조회(부작용 없음) ─────────────────────────────────────────────
    def snapshot(self, now: datetime | None = None) -> dict:
        now = now or datetime.now(timezone.utc)
        with self._lock:
            day, count = self._day_chats
            today = _kst_date(now)
            return {
                "chat_today": count if day == today else 0,
                "chat_per_day": self.limits.chat_per_day,
                "sessions_tracked": len(self._session_chats),
            }

    # ── 소비(카운터 증가) ─────────────────────────────────────────────
    def check_consent(self, ip: str, now: datetime | None = None) -> Decision:
        if self.limits.consent_per_ip_hour <= 0:
            return Decision(True)
        now = now or datetime.now(timezone.utc)
        bucket = _hour_bucket(now)
        with self._lock:
            if bucket != self._ip_hour:      # 시각이 넘어갔다 — 통째로 버린다
                self._ip_consents = {}
                self._ip_hour = bucket
            used = self._ip_consents.get(ip, 0)
            if used >= self.limits.consent_per_ip_hour:
                return Decision(
                    False,
                    "잠시 후 다시 시도해 주세요. (동일 네트워크에서 접속이 많습니다)",
                    retry_after=_seconds_to_next_hour(now),
                )
            self._ip_consents[ip] = used + 1
        return Decision(True)

    def check_chat(self, session_id: str, now: datetime | None = None) -> Decision:
        now = now or datetime.now(timezone.utc)
        today = _kst_date(now)
        with self._lock:
            # 3층: 전체 일일 상한 — 비용 백스톱이므로 가장 먼저 본다.
            day, day_count = self._day_chats
            if day != today:
                day, day_count = today, 0
            if self.limits.chat_per_day > 0 and day_count >= self.limits.chat_per_day:
                return Decision(
                    False,
                    "오늘 전체 이용량 한도에 도달했습니다. 내일 다시 이용해 주세요.",
                    retry_after=_seconds_to_next_kst_midnight(now),
                )

            # 1층: 세션당 질문 수. 날짜가 넘어가면 통째로 버린다 — 하루를 넘긴
            # 세션은 카운터가 초기화되지만, 돈을 지키는 것은 3층이라 무방하다.
            if today != self._session_day:
                self._session_chats = {}
                self._session_day = today
            used = self._session_chats.get(session_id, 0)
            if self.limits.chat_per_session > 0 and used >= self.limits.chat_per_session:
                return Decision(
                    False,
                    "이 대화의 질문 수 한도에 도달했습니다. 새로고침 후 다시 시작해 주세요.",
                )

            self._session_chats[session_id] = used + 1
            self._day_chats = (today, day_count + 1)
        return Decision(True)

    def forget_session(self, session_id: str) -> None:
        """세션 삭제(/purge) 시 카운터도 정리한다."""
        with self._lock:
            self._session_chats.pop(session_id, None)

def _seconds_to_next_hour(now: datetime) -> int:
    nxt = (now.astimezone(KST) + timedelta(hours=1)).replace(
        minute=0, second=0, microsecond=0
    )
    return max(1, int((nxt - now.astimezone(KST)).total_seconds()))


def _seconds_to_next_kst_midnight(now: datetime) -> int:
    k = now.astimezone(KST)
    nxt = (k + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, int((nxt - k).total_seconds()))


def client_ip(request) -> str:
    """프록시 뒤를 고려한 클라이언트 IP. X-Forwarded-For 의 첫 값을 쓴다.

    주의: 이 헤더는 신뢰 경계 밖에서 위조 가능하다. 리버스 프록시(Traefik/nginx)가
    앞단에서 덮어쓰는 배포에서만 의미가 있고, 그렇지 않으면 공격자가 IP 를 바꿔가며
    2층을 우회한다 — 그래서 3층(전체 일일 상한)이 따로 있는 것이다."""
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return getattr(getattr(request, "client", None), "host", "") or "unknown"
