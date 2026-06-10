import os
from utils.collect_config import ai_throttle_seconds


def test_default_when_unset(monkeypatch):
    monkeypatch.delenv("AI_THROTTLE_SEC", raising=False)
    assert ai_throttle_seconds() == 2.0


def test_reads_env(monkeypatch):
    monkeypatch.setenv("AI_THROTTLE_SEC", "0.5")
    assert ai_throttle_seconds() == 0.5


def test_invalid_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("AI_THROTTLE_SEC", "abc")
    assert ai_throttle_seconds() == 2.0


def test_negative_clamped_to_zero(monkeypatch):
    monkeypatch.setenv("AI_THROTTLE_SEC", "-3")
    assert ai_throttle_seconds() == 0.0
