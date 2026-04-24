"""Scraping da API não oficial do SofaScore para validação de resultados."""

from __future__ import annotations

import difflib

import httpx

_BASE = "https://api.sofascore.com/api/v1"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8",
    "Referer": "https://www.sofascore.com/",
    "Origin": "https://www.sofascore.com",
}
_MATCH_THRESHOLD = 0.5


async def _get_scheduled_events(date_str: str) -> list[dict]:
    """Retorna todos os eventos de futebol do dia no SofaScore."""
    url = f"{_BASE}/sport/football/scheduled-events/{date_str}"
    async with httpx.AsyncClient(headers=_HEADERS, timeout=15) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json().get("events", [])


async def _get_incidents(event_id: int) -> list[dict]:
    """Retorna os incidentes (cartões, gols, etc.) de um evento."""
    url = f"{_BASE}/event/{event_id}/incidents"
    async with httpx.AsyncClient(headers=_HEADERS, timeout=15) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json().get("incidents", [])


def _similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


async def find_event(date_str: str, home_team: str, away_team: str) -> dict | None:
    """Busca o evento no SofaScore pelo nome dos times (matching fuzzy)."""
    events = await _get_scheduled_events(date_str)
    best: dict | None = None
    best_score = 0.0

    for ev in events:
        h = ev.get("homeTeam", {}).get("name", "")
        a = ev.get("awayTeam", {}).get("name", "")
        score = (_similarity(home_team, h) + _similarity(away_team, a)) / 2
        if score > best_score:
            best_score = score
            best = ev

    if best_score >= _MATCH_THRESHOLD:
        return best
    return None


async def get_red_cards(event_id: int) -> int:
    """Conta o total de cartões vermelhos de um evento (soma dos dois times)."""
    incidents = await _get_incidents(event_id)
    return sum(
        1 for inc in incidents
        if inc.get("incidentType") == "card" and inc.get("cardType") == "red"
    )
