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


# ── Testes de validate_opportunity ────────────────────────────────────────────

ENTRY_UNDER_05 = {
    "event_id": "abc",
    "home_team": "Flamengo",
    "away_team": "Corinthians",
    "competition": "Brasileirão",
    "selection_name": "Menos de 0.5",
    "odd": 1.85,
    "alerted_at": "2026-04-24T14:00:00",
}

ENTRY_UNDER_15 = {**ENTRY_UNDER_05, "selection_name": "Menos de 1.5", "odd": 1.40}


@pytest.mark.asyncio
async def test_validate_opportunity_won_under_05_no_red_cards():
    event = {"id": 99001, "homeTeam": {"name": "Flamengo"}, "awayTeam": {"name": "Corinthians"}, "status": {"type": "finished"}}
    with patch("src.sofascore.find_event", new_callable=AsyncMock, return_value=event), \
         patch("src.sofascore.get_red_cards", new_callable=AsyncMock, return_value=0):
        result = await sofascore.validate_opportunity(ENTRY_UNDER_05, "2026-04-24")
    assert result.status == "won"
    assert result.won is True
    assert result.red_cards == 0


@pytest.mark.asyncio
async def test_validate_opportunity_lost_under_05_with_red_card():
    event = {"id": 99001, "homeTeam": {"name": "Flamengo"}, "awayTeam": {"name": "Corinthians"}, "status": {"type": "finished"}}
    with patch("src.sofascore.find_event", new_callable=AsyncMock, return_value=event), \
         patch("src.sofascore.get_red_cards", new_callable=AsyncMock, return_value=1):
        result = await sofascore.validate_opportunity(ENTRY_UNDER_05, "2026-04-24")
    assert result.status == "lost"
    assert result.won is False
    assert result.red_cards == 1


@pytest.mark.asyncio
async def test_validate_opportunity_won_under_15_one_red_card():
    event = {"id": 99001, "homeTeam": {"name": "Flamengo"}, "awayTeam": {"name": "Corinthians"}, "status": {"type": "finished"}}
    with patch("src.sofascore.find_event", new_callable=AsyncMock, return_value=event), \
         patch("src.sofascore.get_red_cards", new_callable=AsyncMock, return_value=1):
        result = await sofascore.validate_opportunity(ENTRY_UNDER_15, "2026-04-24")
    assert result.status == "won"
    assert result.won is True


@pytest.mark.asyncio
async def test_validate_opportunity_unverified_when_not_found():
    with patch("src.sofascore.find_event", new_callable=AsyncMock, return_value=None):
        result = await sofascore.validate_opportunity(ENTRY_UNDER_05, "2026-04-24")
    assert result.status == "unverified"
    assert result.won is None
    assert result.red_cards == -1


@pytest.mark.asyncio
async def test_validate_opportunity_polls_until_finished():
    """Verifica que o polling re-checa o status quando o jogo está em andamento."""
    in_progress = {"id": 99001, "homeTeam": {"name": "Flamengo"}, "awayTeam": {"name": "Corinthians"}, "status": {"type": "inprogress"}}
    finished = {"id": 99001, "homeTeam": {"name": "Flamengo"}, "awayTeam": {"name": "Corinthians"}, "status": {"type": "finished"}}

    find_side_effects = [in_progress, finished]
    with patch("src.sofascore.find_event", new_callable=AsyncMock, side_effect=find_side_effects), \
         patch("src.sofascore.get_red_cards", new_callable=AsyncMock, return_value=0), \
         patch("asyncio.sleep", new_callable=AsyncMock):
        result = await sofascore.validate_opportunity(ENTRY_UNDER_05, "2026-04-24", poll_interval=0, max_polls=3)
    assert result.status == "won"
