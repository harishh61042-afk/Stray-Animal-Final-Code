"""The sliding-window limiter that slows down guessing on the report-tracking page."""
from types import SimpleNamespace

import pytest

from app.utils import ratelimit
from app.utils.ratelimit import SlidingWindowLimiter


class FakeClock:
    """A clock the test moves by hand, so no test has to wait."""

    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def move(self, seconds):
        self.now += seconds


@pytest.fixture()
def clock(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr(ratelimit, "time", SimpleNamespace(monotonic=fake))  # only this module sees the fake clock
    return fake


def test_a_new_key_is_not_blocked(clock):
    assert SlidingWindowLimiter(limit=3, window_seconds=60).blocked("203.0.113.5") is False


def test_blocking_starts_when_the_limit_is_reached(clock):
    limiter = SlidingWindowLimiter(limit=3, window_seconds=60)
    for _ in range(2):
        limiter.hit("203.0.113.5")
    assert limiter.blocked("203.0.113.5") is False
    limiter.hit("203.0.113.5")
    assert limiter.blocked("203.0.113.5") is True


def test_every_key_has_its_own_allowance(clock):
    limiter = SlidingWindowLimiter(limit=2, window_seconds=60)
    limiter.hit("203.0.113.5")
    limiter.hit("203.0.113.5")
    assert limiter.blocked("203.0.113.5") is True
    assert limiter.blocked("198.51.100.7") is False


def test_old_attempts_stop_counting_after_the_window(clock):
    limiter = SlidingWindowLimiter(limit=2, window_seconds=60)
    limiter.hit("a")
    limiter.hit("a")
    assert limiter.blocked("a") is True
    clock.move(30)
    assert limiter.blocked("a") is True  # still inside the window
    clock.move(31)
    assert limiter.blocked("a") is False  # both attempts are now older than 60 seconds


def test_the_window_slides_instead_of_resetting_all_at_once(clock):
    limiter = SlidingWindowLimiter(limit=2, window_seconds=60)
    limiter.hit("a")  # at 0 s
    clock.move(40)
    limiter.hit("a")  # at 40 s
    assert limiter.blocked("a") is True
    clock.move(25)  # 65 s: the first attempt has expired, the second has not
    assert limiter.blocked("a") is False
    limiter.hit("a")
    assert limiter.blocked("a") is True


def test_reset_forgets_one_key_or_all_keys(clock):
    limiter = SlidingWindowLimiter(limit=1, window_seconds=60)
    limiter.hit("a")
    limiter.hit("b")
    limiter.reset("a")
    assert limiter.blocked("a") is False and limiter.blocked("b") is True
    limiter.reset()
    assert limiter.blocked("b") is False


def test_memory_stays_bounded_when_many_different_visitors_appear(clock, monkeypatch):
    monkeypatch.setattr(SlidingWindowLimiter, "MAX_KEYS", 10)
    limiter = SlidingWindowLimiter(limit=5, window_seconds=60)
    for number in range(10):
        limiter.hit(f"old-{number}")
    clock.move(120)  # all of them are out of date now
    limiter.hit("new-visitor")  # the 11th key triggers the clean-up
    assert list(limiter._hits) == ["new-visitor"]


def test_the_tracking_limiter_allows_eight_misses_per_ten_minutes():
    assert ratelimit.track_limiter.limit == 8
    assert ratelimit.track_limiter.window == 600
