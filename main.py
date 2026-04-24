#!/usr/bin/env python3
"""Bot Red Card v2 — Monitor Under Cartão Vermelho (Betano).

Arquitetura híbrida:
- Fase 1: curl_cffi busca eventos ao vivo via API REST (TLS fingerprint bypass)
- Fase 2: Playwright com Sessão Quente escaneia mercados de cartão (stealth)

Fallback em 3 estágios para discovery de eventos ao vivo:
  Estágio 1: curl_cffi + cookies do Playwright         (~200ms)
  Estágio 2: fetch() na aba persistente                (~1-2s)
  Estágio 3: fetch_json com nova aba (comportamento anterior) (~8-15s)
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta

from curl_cffi import requests as curl_requests

from src.browser import BrowserEngine
from src.config import settings
from src.models import GameContext
from src.scanner import Scanner
from src import opportunity_log
from src.sofascore import validate_all
from src import telegram_notifier as telegram


def _build_curl_session(cookies: list[dict], user_agent: str) -> curl_requests.Session:
    """Cria Session curl_cffi autenticada com cookies do Playwright.

    O Playwright passa no challenge Cloudflare e recebe cookies de sessão
    (incluindo cf_clearance). Transferir esses cookies para o curl_cffi
    permite requests diretas (~200ms) sem precisar do browser.
    """
    session = curl_requests.Session(impersonate="chrome131")

    for c in cookies:
        session.cookies.set(
            c["name"],
            c["value"],
            domain=c.get("domain", "").lstrip("."),
            path=c.get("path", "/"),
        )

    session.headers.update({
        "User-Agent": user_agent,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": f"{settings.base_url}/sport/futebol/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    })

    return session


async def _refresh_curl_session(browser: "BrowserEngine") -> curl_requests.Session | None:
    """Extrai cookies do browser e cria/atualiza a Session curl_cffi."""
    try:
        cookies = await browser.export_cookies()
        ua = browser.user_agent
        if not cookies or not ua:
            return None
        session = _build_curl_session(cookies, ua)
        print(f"  [Session] curl_cffi atualizada com {len(cookies)} cookies")
        return session
    except Exception as e:
        print(f"  [Session] Erro ao exportar cookies: {e}")
        return None


def _resolve_competition(event: dict, leagues: dict, regions: dict) -> str:
    """Resolve o nome da competição de um evento.

    Tenta múltiplos caminhos na resposta da API:
    1. Campo direto no evento (leagueName, competitionName)
    2. Objeto aninhado (league.name, tournament.name)
    3. Resolução via leagueId no dicionário top-level de leagues
    4. Resolução via regionId no dicionário top-level de regions
    """
    # Caminho 1: campo direto no evento
    name = (
        event.get("leagueName")
        or event.get("competitionName")
        or event.get("regionLeagueName")
    )
    if name:
        return name

    # Caminho 2: objeto aninhado
    league_obj = event.get("league")
    if isinstance(league_obj, dict) and league_obj.get("name"):
        return league_obj["name"]

    tournament_obj = event.get("tournament")
    if isinstance(tournament_obj, dict) and tournament_obj.get("name"):
        return tournament_obj["name"]

    # Caminho 3: resolver via leagueId no dict top-level
    league_id = event.get("leagueId") or event.get("league_id") or event.get("competitionId")
    if league_id is not None:
        league_data = leagues.get(str(league_id), {})
        league_name = league_data.get("name") or league_data.get("description")
        if league_name:
            # Tentar enriquecer com região
            region_id = event.get("regionId") or event.get("region_id") or event.get("zoneId")
            if region_id is not None:
                region_data = regions.get(str(region_id), {})
                region_name = region_data.get("name")
                if region_name:
                    return f"{region_name} - {league_name}"
            return league_name

    # Caminho 4: só região como último recurso
    region_id = event.get("regionId") or event.get("region_id") or event.get("zoneId")
    if region_id is not None:
        region_data = regions.get(str(region_id), {})
        region_name = region_data.get("name")
        if region_name:
            return region_name

    return "Desconhecida"


def _extract_live_games(data: dict) -> list[GameContext]:
    """Extrai jogos de futebol ao vivo da resposta da API."""
    events = data.get("events", {})
    leagues = data.get("leagues", {})
    regions = data.get("regions", {}) or data.get("zones", {})
    result: list[GameContext] = []

    # Log de debug (apenas 1x) para mapear estrutura da API
    _logged_debug = False

    for eid, event in events.items():
        if event.get("sportId") != "FOOT":
            continue

        if not _logged_debug:
            print(f"  [DEBUG] Top-level keys: {list(data.keys())}")
            print(f"  [DEBUG] Event keys: {sorted(event.keys())}")
            if leagues:
                first_league = next(iter(leagues.values()), {})
                print(f"  [DEBUG] League keys: {sorted(first_league.keys()) if isinstance(first_league, dict) else first_league}")
            if regions:
                first_region = next(iter(regions.values()), {})
                print(f"  [DEBUG] Region keys: {sorted(first_region.keys()) if isinstance(first_region, dict) else first_region}")
            _logged_debug = True

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

        # Competição (resolução robusta)
        competition = _resolve_competition(event, leagues, regions)

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


async def _fetch_live_events(
    browser: "BrowserEngine",
    curl_session: curl_requests.Session | None = None,
) -> tuple[list[GameContext], bool]:
    """Busca eventos ao vivo com fallback em 3 estágios.

    Retorna (jogos, needs_cookie_refresh).
    needs_cookie_refresh=True indica que os cookies expiraram e devem
    ser renovados antes do próximo ciclo.

    Estágio 1: curl_cffi + cookies do Playwright  (~200ms)
    Estágio 2: fetch() na aba persistente          (~1-2s)
    Estágio 3: fetch_json com nova aba             (~8-15s)
    """
    needs_refresh = False

    # ── Estágio 1: curl_cffi + cookies do Playwright (~200ms) ──────
    if curl_session:
        try:
            print(f"  [API] curl_cffi+cookies GET {settings.overview_url[:80]}...")
            response = curl_session.get(settings.overview_url, timeout=15)
            print(f"  [API] curl_cffi+cookies HTTP {response.status_code} | {len(response.content)} bytes")
            if response.status_code == 200:
                data = response.json()
                games = _extract_live_games(data)
                print(f"  [API] curl_cffi+cookies OK | {len(games)} jogos")
                for g in games[:5]:
                    print(f"    - {g.label} | Min: {g.minute}' | Mercados: {g.total_markets}")
                if len(games) > 5:
                    print(f"    ... e mais {len(games) - 5} jogos")
                return games, False
            print(f"  [API] curl_cffi+cookies falhou ({response.status_code}) → fallback browser")
            needs_refresh = True
        except Exception as e:
            print(f"  [API] curl_cffi+cookies erro ({e}) → fallback browser")
            needs_refresh = True

    # ── Estágio 2/3: browser (aba persistente ou nova aba) ─────────
    try:
        print(f"  [API] Browser fetch {settings.overview_url[:80]}...")
        data = await browser.fetch_json(settings.overview_url)
        if not data:
            print("  [API] Browser fetch retornou vazio")
            return [], needs_refresh

        games = _extract_live_games(data)
        print(f"  [API] Browser OK | {len(games)} jogos")
        for g in games[:5]:
            print(f"    - {g.label} | Min: {g.minute}' | Mercados: {g.total_markets}")
        if len(games) > 5:
            print(f"    ... e mais {len(games) - 5} jogos")
        return games, needs_refresh

    except Exception as e:
        print(f"  [API] Browser fetch falhou: {e}")
        return [], needs_refresh


async def _sleep_until(hour: int, minute: int) -> None:
    """Dorme até o próximo HH:MM do dia (ou do dia seguinte se já passou)."""
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    delta = (target - now).total_seconds()
    print(f"  [DailyReporter] Próximo relatório em {delta / 3600:.1f}h ({target.strftime('%d/%m %H:%M')})")
    await asyncio.sleep(delta)


async def daily_reporter() -> None:
    """Task paralela: às 23:45 valida oportunidades do dia e envia relatório."""
    while True:
        await _sleep_until(23, 45)
        print("\n[DailyReporter] Iniciando validação do dia...")

        entries = opportunity_log.load_today()
        if entries:
            print(f"[DailyReporter] {len(entries)} oportunidade(s) para validar")
            results = await validate_all(entries)
            sent = telegram.send_daily_report(results)
            print(f"[DailyReporter] Relatório enviado: {'OK' if sent else 'FALHOU'}")
        else:
            print("[DailyReporter] Nenhuma oportunidade hoje — relatório suprimido")

        opportunity_log.delete_today()
        await asyncio.sleep(60)


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

    # Criar session curl_cffi com cookies do Playwright (Estágio 1)
    curl_session = await _refresh_curl_session(browser)

    scanner = Scanner(browser)

    # Task paralela de relatório diário
    asyncio.create_task(daily_reporter())

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
    last_cleanup = time.time()

    try:
        while True:
            cycle += 1
            print(f"\n{'=' * 60}")
            print(f"CICLO {cycle} | {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
            print(f"{'=' * 60}")

            # Limpeza de alertas a cada 30 min
            if time.time() - last_cleanup >= 1800:
                print(f"  [Cleanup] Limpando {len(alerted_events)} alertas da memória")
                alerted_events.clear()
                last_cleanup = time.time()

            # Reciclagem periódica (stop + start + warm_session internamente)
            if cycle > 1 and cycle % settings.recycle_every_n_cycles == 0:
                await browser.recycle()
                curl_session = await _refresh_curl_session(browser)

            # Refresh proativo de cookies a cada 5 ciclos (~25 min com cooldown=300s)
            elif cycle > 1 and cycle % 5 == 0:
                curl_session = await _refresh_curl_session(browser) or curl_session

            # Fase 1: buscar eventos ao vivo (3 estágios)
            games, needs_refresh = await _fetch_live_events(browser, curl_session)

            # Se cookies expiraram (403 no Estágio 1), renovar antes do próximo ciclo
            if needs_refresh:
                curl_session = await _refresh_curl_session(browser) or curl_session

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
                opportunity_log.append(opp)
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
