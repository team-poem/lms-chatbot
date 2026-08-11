"""요청 상한. 위협은 트래픽이 아니라 Gemini 과금이므로, 각 층이 '우회당해도
다음 층이 받는다'를 확인한다."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ratelimit import KST, Limits, RateLimiter, client_ip

T0 = datetime(2026, 8, 11, 3, 0, tzinfo=timezone.utc)   # KST 12:00


def test_session_cap_blocks_after_limit():
    rl = RateLimiter(Limits(chat_per_session=3, consent_per_ip_hour=0, chat_per_day=0))
    for _ in range(3):
        assert rl.check_chat("s1", T0).allowed
    denied = rl.check_chat("s1", T0)
    assert not denied.allowed
    assert "질문 수" in denied.reason


def test_session_cap_is_per_session():
    rl = RateLimiter(Limits(chat_per_session=1, consent_per_ip_hour=0, chat_per_day=0))
    assert rl.check_chat("s1", T0).allowed
    assert not rl.check_chat("s1", T0).allowed
    # 다른 세션은 영향 없다 — 그래서 2층(IP당 세션 발급)이 따로 필요하다.
    assert rl.check_chat("s2", T0).allowed


def test_daily_cap_catches_session_rotation():
    """세션을 새로 파며 1층을 우회해도 3층이 받는다 — 비용의 최종 방어선."""
    rl = RateLimiter(Limits(chat_per_session=1, consent_per_ip_hour=0, chat_per_day=3))
    for i in range(3):
        assert rl.check_chat(f"s{i}", T0).allowed
    denied = rl.check_chat("s99", T0)
    assert not denied.allowed
    assert "오늘" in denied.reason
    assert denied.retry_after > 0


def test_daily_cap_resets_on_kst_date_change():
    rl = RateLimiter(Limits(chat_per_session=0, consent_per_ip_hour=0, chat_per_day=1))
    assert rl.check_chat("s1", T0).allowed
    assert not rl.check_chat("s2", T0).allowed
    # KST 기준 다음 날
    tomorrow = T0 + timedelta(days=1)
    assert rl.check_chat("s3", tomorrow).allowed


def test_consent_cap_is_per_ip_and_hourly():
    rl = RateLimiter(Limits(chat_per_session=0, consent_per_ip_hour=2, chat_per_day=0))
    assert rl.check_consent("1.1.1.1", T0).allowed
    assert rl.check_consent("1.1.1.1", T0).allowed
    assert not rl.check_consent("1.1.1.1", T0).allowed
    # 다른 IP 는 독립
    assert rl.check_consent("2.2.2.2", T0).allowed
    # 다음 시각 버킷이면 리셋
    assert rl.check_consent("1.1.1.1", T0 + timedelta(hours=1)).allowed


def test_zero_disables_each_layer():
    rl = RateLimiter(Limits(chat_per_session=0, consent_per_ip_hour=0, chat_per_day=0))
    for i in range(50):
        assert rl.check_chat("s1", T0).allowed
        assert rl.check_consent("1.1.1.1", T0).allowed


def test_purge_forgets_session_counter():
    """/purge 는 개인정보 삭제다. 카운터가 남으면 지운 세션의 흔적이 남는다."""
    rl = RateLimiter(Limits(chat_per_session=1, consent_per_ip_hour=0, chat_per_day=0))
    assert rl.check_chat("s1", T0).allowed
    assert not rl.check_chat("s1", T0).allowed
    rl.forget_session("s1")
    assert rl.check_chat("s1", T0).allowed


def test_snapshot_reports_today_only():
    rl = RateLimiter(Limits(chat_per_session=0, consent_per_ip_hour=0, chat_per_day=10))
    rl.check_chat("s1", T0)
    assert rl.snapshot(T0)["chat_today"] == 1
    # 날짜가 바뀌면 오늘 사용량은 0 으로 보고된다.
    assert rl.snapshot(T0 + timedelta(days=1))["chat_today"] == 0


def test_retry_after_points_into_the_future():
    rl = RateLimiter(Limits(chat_per_session=0, consent_per_ip_hour=1, chat_per_day=0))
    rl.check_consent("1.1.1.1", T0)
    d = rl.check_consent("1.1.1.1", T0)
    assert 0 < d.retry_after <= 3600


class _Req:
    def __init__(self, headers=None, host="9.9.9.9"):
        self.headers = headers or {}
        self.client = type("C", (), {"host": host})()


def test_client_ip_prefers_forwarded_header():
    assert client_ip(_Req({"x-forwarded-for": "5.5.5.5, 10.0.0.1"})) == "5.5.5.5"
    assert client_ip(_Req()) == "9.9.9.9"
    assert client_ip(_Req(host="")) == "unknown"


def test_counters_do_not_grow_without_bound():
    """상시 가동 서버에서 세션 카운터가 무한히 쌓이면 안 된다. /purge 로만
    정리되던 구조에서는 30일에 6000개가 남았다(대부분 사용자는 purge 를 부르지
    않는다)."""
    rl = RateLimiter(Limits(chat_per_session=100, consent_per_ip_hour=0, chat_per_day=0))
    for day in range(30):
        t = T0 + timedelta(days=day)
        for i in range(200):
            rl.check_chat(f"d{day}-s{i}", t)
    assert len(rl._session_chats) == 200          # 마지막 하루치만

    rl2 = RateLimiter(Limits(chat_per_session=0, consent_per_ip_hour=1000, chat_per_day=0))
    for h in range(48):
        t = T0 + timedelta(hours=h)
        for i in range(50):
            rl2.check_consent(f"10.0.0.{i}", t)
    assert len(rl2._ip_consents) == 50            # 마지막 한 시간치만


def test_session_cap_resets_next_day():
    """버킷을 비우는 대가 — 하루 넘긴 세션은 카운터가 초기화된다. 돈을 지키는
    것은 3층(일일 전체 상한)이므로 무방하다."""
    rl = RateLimiter(Limits(chat_per_session=1, consent_per_ip_hour=0, chat_per_day=0))
    assert rl.check_chat("s1", T0).allowed
    assert not rl.check_chat("s1", T0).allowed
    assert rl.check_chat("s1", T0 + timedelta(days=1)).allowed
