#!/usr/bin/env python3
"""Bot Red Card v2 — Monitor Under Cartão Vermelho (Betano).

Arquitetura híbrida:
- Fase 1: curl_cffi busca eventos ao vivo via API REST (TLS fingerprint bypass)
- Fase 2: Playwright com Sessão Quente escaneia mercados de cartão (stealth)
"""

import asyncio
import time
from datetime import datetime

from curl_cffi import requests as curl_requests

from src.browser import BrowserEngine
from src.config import settings
from src.models import GameContext
from src.scanner import Scanner
from src import telegram_notifier as telegram


def _extract_live_games(data: dict) -> list[GameContext]:
    """Extrai jogos de futebol ao vivo da resposta da API."""
    events = data.get("events", {})
    result: list[GameContext] = []

    for eid, event in events.items():
        if event.get("sportId") != "FOOT":
            continue

        participants = event.get("participants", [])
        if any("esports" in p.get("name", "").lower() for p in participants):
            continue

        # Minuto do jogo
        try:
            seconds = event["liveData"]["clock"]["secondsSinceStart"]
            minute = int(seconds) // 60
        except (KeyError, TypeError, ValueError):
            minute = 0

        if minute < settings.min_match_minute:
            continue

        home = participants[0].get("name", "?") if len(participants) > 0 else "?"
        away = participants[1].get("name", "?") if len(participants) > 1 else "?"

        # Competição
        competition = (
            event.get("league", {}).get("name")
            or event.get("tournament", {}).get("name")
            or event.get("leagueName")
            or "Desconhecida"
        )

        # Placar ao vivo
        live_data = event.get("liveData", {})
        score_data = live_data.get("score", {})
        score_home = score_data.get("home", 0)
        score_away = score_data.get("away", 0)
        score = f"{score_home} x {score_away}"

        result.append(
            GameContext(
                id=str(eid),
                home=home,
                away=away,
                url=event.get("url", ""),
                minute=minute,
                total_markets=event.get("totalMarketsAvailable", 0),
                competition=competition,
                score=score,
            )
        )

    # Priorizar jogos com mais mercados
    result.sort(key=lambda g: g.total_markets, reverse=True)
    return result


def _fetch_live_events() -> list[GameContext]:
    """Busca eventos ao vivo via curl_cffi (TLS fingerprint bypass).

    Usa impersonate="chrome120" para falsificar o TLS handshake e passar
    pelo Cloudflare/WAF sem problemas. Rápido e confiável para a API REST.
    """
    try:
        print(f"  [API] GET {settings.overview_url[:80]}...")
        response = curl_requests.get(
            settings.overview_url,
            headers={"Accept": "application/json"},
            impersonate="chrome120",
            timeout=30,
        )
        print(f"  [API] HTTP {response.status_code} | {len(response.content)} bytes")

        if response.status_code != 200:
            print(f"  [API] Erro: HTTP {response.status_code}")
            return []

        data = response.json()
        games = _extract_live_games(data)
        print(f"  [API] Futebol ao vivo (>= {settings.min_match_minute} min): {len(games)} jogos")
        for g in games[:5]:
            print(f"    - {g.label} | Min: {g.minute}' | Mercados: {g.total_markets}")
        if len(games) > 5:
            print(f"    ... e mais {len(games) - 5} jogos")
        return games

    except Exception as e:
        print(f"  [API] Erro ao buscar eventos: {e}")
        return []


async def run() -> None:
    print("=" * 60)
    print("BOT RED CARD v2 — Monitor Under Cartão Vermelho")
    print("=" * 60)
    print(f"Cooldown: {settings.cooldown_seconds}s | Max eventos: {settings.max_events_per_cycle}")
    print(f"Delay entre eventos: {settings.delay_between_events}s")
    print(f"Odd mínima: {settings.min_odd_threshold} | Minuto mínimo: {settings.min_match_minute}")
    print(f"Telegram: {'Ativo' if settings.telegram_enabled else 'Desativado'}")
    print(f"Início: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print("=" * 60)

    # Iniciar browser com sessão quente
    browser = BrowserEngine()
    await browser.start()
    await browser.warm_session()

    scanner = Scanner(browser)

    # Notificar início
    telegram.send_message(
        f"<b>BOT RED CARD v2 iniciado</b>\n\n"
        f"Linhas: Under 0.5 e 1.5\n"
        f"Cooldown: {settings.cooldown_seconds}s\n"
        f"Max eventos: {settings.max_events_per_cycle}\n"
        f"Odd mínima: {settings.min_odd_threshold}\n"
        f"Horário: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
    )

    cycle = 0
    total_opportunities = 0
    alerted_events: set[str] = set()

    try:
        while True:
            cycle += 1
            print(f"\n{'=' * 60}")
            print(f"CICLO {cycle} | {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
            print(f"{'=' * 60}")

            # Reciclagem periódica
            if cycle > 1 and cycle % settings.recycle_every_n_cycles == 0:
                await browser.recycle()

            # Fase 1: buscar eventos ao vivo via curl_cffi (rápido)
            games = _fetch_live_events()

            # Escanear mercados
            start = time.time()
            opportunities = await scanner.scan_all(games)
            elapsed = time.time() - start

            # Filtrar já alertadas (chave: event_id + selection para permitir
            # Under 0.5 e Under 1.5 no mesmo jogo como alertas distintos)
            new_opps = [
                o for o in opportunities
                if f"{o.event_id}:{o.selection_name}" not in alerted_events
            ]
            print(f"Tempo: {elapsed:.0f}s | Oportunidades: {len(opportunities)} ({len(new_opps)} novas)")

            for opp in new_opps:
                print(f"  >> {opp.label} | {opp.selection_name} | Odd: {opp.odd:.2f}")
                sent = telegram.send_opportunity_alert(opp)
                print(f"  [Telegram] {'OK' if sent else 'FALHOU'}")
                alerted_events.add(f"{opp.event_id}:{opp.selection_name}")

            total_opportunities += len(new_opps)

            print(f"Aguardando {settings.cooldown_seconds}s...")
            await asyncio.sleep(settings.cooldown_seconds)

    except KeyboardInterrupt:
        print("\nEncerrando...")
    finally:
        await browser.stop()
        print(f"\nTotal de oportunidades: {total_opportunities}")


if __name__ == "__main__":
    asyncio.run(run())
