"""Scraping da API não oficial do SofaScore para validação de resultados."""

from __future__ import annotations

import asyncio
import difflib
from datetime import date as _date

import httpx

from src.models import MatchResult

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


_POLL_INTERVAL_SECONDS = 300   # 5 minutos
_MAX_POLLS = 18                # 90 minutos máximo


def _is_under_won(selection_name: str, red_cards: int) -> bool:
    """Determina se aposta Under venceu baseado na linha e nos cartões vermelhos."""
    name = selection_name.lower()
    if "0.5" in name or "0,5" in name:
        return red_cards == 0
    if "1.5" in name or "1,5" in name:
        return red_cards <= 1
    # Fallback: "não"/"nao" → Under 0.5
    return red_cards == 0


async def validate_opportunity(
    entry: dict,
    date_str: str,
    poll_interval: int = _POLL_INTERVAL_SECONDS,
    max_polls: int = _MAX_POLLS,
) -> MatchResult:
    """Valida uma oportunidade consultando o SofaScore.

    Faz polling até o jogo terminar ou atingir max_polls tentativas.
    """
    home = entry["home_team"]
    away = entry["away_team"]
    _unverified = MatchResult(
        home_team=home,
        away_team=away,
        competition=entry.get("competition", ""),
        selection_name=entry["selection_name"],
        odd=entry["odd"],
        red_cards=-1,
        won=None,
        status="unverified",
    )

    for attempt in range(max_polls):
        event = await find_event(date_str, home, away)

        if event is None:
            return _unverified

        status_type = event.get("status", {}).get("type", "")

        if status_type == "finished":
            red_cards = await get_red_cards(event["id"])
            won = _is_under_won(entry["selection_name"], red_cards)
            return MatchResult(
                home_team=home,
                away_team=away,
                competition=entry.get("competition", ""),
                selection_name=entry["selection_name"],
                odd=entry["odd"],
                red_cards=red_cards,
                won=won,
                status="won" if won else "lost",
            )

        # Jogo em andamento — aguardar e tentar novamente
        if attempt < max_polls - 1:
            print(f"  [SofaScore] {home} x {away} ainda em andamento, aguardando {poll_interval}s...")
            await asyncio.sleep(poll_interval)

    return _unverified


async def validate_all(entries: list[dict], date_str: str | None = None) -> list[MatchResult]:
    """Valida todas as oportunidades em paralelo."""
    if date_str is None:
        date_str = _date.today().isoformat()
    tasks = [validate_opportunity(e, date_str) for e in entries]
    return list(await asyncio.gather(*tasks))
