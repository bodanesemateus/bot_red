"""Testes do scraper SofaScore."""

from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from src import sofascore


# ── Fixtures de resposta da API ────────────────────────────────────────────────

SCHEDULED_RESPONSE = {
    "events": [
        {
            "id": 99001,
            "homeTeam": {"name": "Flamengo"},
            "awayTeam": {"name": "Corinthians"},
            "status": {"type": "finished"},
        },
        {
            "id": 99002,
            "homeTeam": {"name": "Santos"},
            "awayTeam": {"name": "Palmeiras"},
            "status": {"type": "inprogress"},
        },
        {
            "id": 99003,
            "homeTeam": {"name": "Real Madrid"},
            "awayTeam": {"name": "Barcelona"},
            "status": {"type": "finished"},
        },
    ]
}

INCIDENTS_WITH_RED = {
    "incidents": [
        {"incidentType": "card", "cardType": "red", "time": 55, "isHome": True},
        {"incidentType": "card", "cardType": "yellow", "time": 30, "isHome": False},
        {"incidentType": "card", "cardType": "red", "time": 80, "isHome": False},
        {"incidentType": "goal", "time": 10, "isHome": True},
    ]
}

INCIDENTS_NO_RED = {
    "incidents": [
        {"incidentType": "card", "cardType": "yellow", "time": 20, "isHome": True},
        {"incidentType": "goal", "time": 45, "isHome": False},
    ]
}


# ── Testes de find_event ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_find_event_exact_match():
    with patch("src.sofascore._get_scheduled_events", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = SCHEDULED_RESPONSE["events"]
        event = await sofascore.find_event("2026-04-24", "Flamengo", "Corinthians")
    assert event is not None
    assert event["id"] == 99001


@pytest.mark.asyncio
async def test_find_event_fuzzy_match():
    with patch("src.sofascore._get_scheduled_events", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = SCHEDULED_RESPONSE["events"]
        event = await sofascore.find_event("2026-04-24", "Fla", "Corint")
    assert event is not None
    assert event["id"] == 99001


@pytest.mark.asyncio
async def test_find_event_not_found():
    with patch("src.sofascore._get_scheduled_events", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = SCHEDULED_RESPONSE["events"]
        event = await sofascore.find_event("2026-04-24", "Time X", "Time Y")
    assert event is None


# ── Testes de get_red_cards ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_red_cards_counts_correctly():
    with patch("src.sofascore._get_incidents", new_callable=AsyncMock) as mock_inc:
        mock_inc.return_value = INCIDENTS_WITH_RED["incidents"]
        count = await sofascore.get_red_cards(99001)
    assert count == 2


@pytest.mark.asyncio
async def test_get_red_cards_zero_when_none():
    with patch("src.sofascore._get_incidents", new_callable=AsyncMock) as mock_inc:
        mock_inc.return_value = INCIDENTS_NO_RED["incidents"]
        count = await sofascore.get_red_cards(99001)
    assert count == 0
