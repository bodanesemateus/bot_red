"""Testes do relatório diário no Telegram."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.models import MatchResult
from src import telegram_notifier as telegram


def _result(status: str, red_cards: int = 0, won: bool | None = None, **kw) -> MatchResult:
    defaults = dict(
        home_team="Time A",
        away_team="Time B",
        competition="Liga X",
        selection_name="Menos de 0.5",
        odd=1.85,
        red_cards=red_cards,
        won=won,
        status=status,
    )
    defaults.update(kw)
    return MatchResult(**defaults)


def test_send_daily_report_calls_post():
    results = [
        _result("won", red_cards=0, won=True),
        _result("lost", red_cards=1, won=False),
        _result("unverified", red_cards=-1, won=None),
    ]
    with patch("src.telegram_notifier._post", return_value=True) as mock_post:
        telegram.send_daily_report(results, report_date="24/04/2026")
    mock_post.assert_called_once()
    text = mock_post.call_args[0][0]
    assert "RELATÓRIO DIÁRIO" in text
    assert "24/04/2026" in text
    assert "✅" in text
    assert "❌" in text
    assert "⏳" in text
    assert "Taxa de acerto" in text


def test_send_daily_report_accuracy_excludes_unverified():
    results = [
        _result("won", red_cards=0, won=True),
        _result("won", red_cards=0, won=True),
        _result("lost", red_cards=1, won=False),
        _result("unverified", red_cards=-1, won=None),
    ]
    with patch("src.telegram_notifier._post", return_value=True) as mock_post:
        telegram.send_daily_report(results, report_date="24/04/2026")
    text = mock_post.call_args[0][0]
    # 2 de 3 verificados = 67%
    assert "67%" in text or "2/3" in text


def test_send_daily_report_all_unverified_no_accuracy_line():
    results = [_result("unverified", red_cards=-1, won=None)]
    with patch("src.telegram_notifier._post", return_value=True) as mock_post:
        telegram.send_daily_report(results, report_date="24/04/2026")
    text = mock_post.call_args[0][0]
    assert "Taxa de acerto" not in text
