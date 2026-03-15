"""Scanner de mercados de Cartão Vermelho na Betano.

Estratégia v2:
- Usa BrowserEngine (sessão quente + stealth) para toda navegação
- Intercepta respostas JSON da SPA para extrair mercados/seleções
- Clica na aba "Cartões" para forçar o carregamento dos mercados
- Detecta splash screen e faz retry com reload
"""

import asyncio
from typing import Optional

from playwright.async_api import Page, Response

from src.browser import BrowserEngine
from src.config import settings
from src.models import GameContext, Opportunity

# ── Termos de mercado (herdados do scanner original) ──────────────
VALID_MARKET_NAMES: list[str] = [
    "total de cartões vermelhos",
    "total de cartoes vermelhos",
    "cartão vermelho",
    "cartao vermelho",
    "cartões vermelhos",
    "cartoes vermelhos",
    "expulsão",
    "expulsao",
]

# Seleções Under (match exato)
UNDER_SELECTIONS: list[str] = [
    "não",
    "nao",
    "menos de 0.5",
    "under 0.5",
]

# Seletores para a aba de Cartões na SPA
_TAB_SELECTORS: list[str] = [
    "span.GTM-tab-name:has-text('Cartões')",
    "span.GTM-tab-name:has-text('Cartoes')",
    "li.events-tabs-container__tab__item:has-text('Cartões')",
]


class Scanner:
    """Scanner de odds Under Cartão Vermelho usando BrowserEngine."""

    def __init__(self, browser: BrowserEngine) -> None:
        self._browser = browser

    # ── API pública ────────────────────────────────────────────────

    async def scan_event(self, game: GameContext) -> Optional[Opportunity]:
        """Escaneia um jogo buscando mercado Under Cartão Vermelho.

        Fluxo:
        1. Abre página do jogo no contexto quente
        2. Instala interceptor de respostas JSON
        3. Espera SPA renderizar as abas do evento
        4. Clica na aba "Cartões" → dispara lazy-loading dos mercados
        5. Aguarda 3s para o interceptor capturar os JSONs de mercados
        6. Varre os mercados capturados buscando Under Cartão Vermelho
        """
        page: Optional[Page] = None
        try:
            page = await self._browser.new_page()

            # Interceptor de respostas JSON (mercados + seleções)
            captured_markets: dict = {}
            captured_selections: dict = {}

            async def _on_response(response: Response) -> None:
                try:
                    ct = response.headers.get("content-type", "")
                    if "json" not in ct:
                        return
                    url = response.url
                    if "events" not in url and "market" not in url:
                        return
                    body = await response.json()
                    if not isinstance(body, dict):
                        return
                    new_m = body.get("markets", {})
                    new_s = body.get("selections", {})
                    if new_m:
                        captured_markets.update(new_m)
                    if new_s:
                        captured_selections.update(new_s)
                    if new_m or new_s:
                        print(
                            f"    [Intercept] +{len(new_m)} mercados, "
                            f"+{len(new_s)} seleções | {url[:80]}..."
                        )
                except Exception:
                    pass

            page.on("response", _on_response)

            # 1. Navegar para o jogo via contexto quente
            full_url = f"{settings.base_url}{game.url}"
            print(f"    [Scanner] Navegando: {full_url}")

            loaded = await self._browser.navigate(page, full_url)
            if not loaded:
                print(f"    [Scanner] Página bloqueada para {game.label}")
                return None

            # 2. Esperar abas da SPA renderizarem
            tabs_ok = await self._wait_for_tabs(page)
            if not tabs_ok:
                print(f"    [Scanner] Abas não carregaram para {game.label}")
                return None

            # Snapshot pré-clique (mercados que vieram no carregamento inicial)
            pre_click_count = len(captured_markets)

            # 3. Clicar na aba Cartões → dispara lazy-loading
            clicked = await self._click_cards_tab(page)
            if not clicked:
                print(f"    [INFO] Aba 'Cartões' não encontrada — jogo sem mercado de cartão ({game.label})")
                return None

            # 4. Aguardar lazy-loading: 3s para o interceptor capturar os
            #    novos JSONs de mercados que chegam pela rede após o clique
            await asyncio.sleep(3)

            lazy_loaded = len(captured_markets) - pre_click_count
            print(
                f"    [Scanner] Mercados: {len(captured_markets)} total "
                f"(+{lazy_loaded} via lazy-load) | Seleções: {len(captured_selections)}"
            )

            if lazy_loaded == 0:
                print(f"    [Scanner] Nenhum mercado novo após clique na aba Cartões")

            # 5. Buscar oportunidade nos mercados capturados
            return self._find_opportunity(game, full_url, captured_markets, captured_selections)

        except Exception as e:
            print(f"    [Scanner] Erro em {game.label}: {e}")
            return None

        finally:
            if page:
                try:
                    await page.close()
                except Exception:
                    pass

    async def scan_all(self, games: list[GameContext]) -> list[Opportunity]:
        """Escaneia lista de jogos sequencialmente com delay entre cada."""
        await self._browser.ensure_alive()

        # Filtrar jogos com mercados suficientes
        candidates = [g for g in games if g.total_markets >= settings.min_markets_for_cards]
        batch = candidates[: settings.max_events_per_cycle]

        filtered = len(games) - len(candidates)
        if filtered > 0:
            print(f"  (filtrados {filtered} jogos com < {settings.min_markets_for_cards} mercados)")
        if len(candidates) > settings.max_events_per_cycle:
            print(f"  (limitado a {settings.max_events_per_cycle} de {len(candidates)} candidatos)")

        opportunities: list[Opportunity] = []
        errors = 0

        for i, game in enumerate(batch):
            if i > 0:
                print(f"  [Delay] {settings.delay_between_events}s...")
                await asyncio.sleep(settings.delay_between_events)

            print(
                f"\n  [{i + 1}/{len(batch)}] {game.label} "
                f"| Min: {game.minute}' | Mercados: {game.total_markets}"
            )

            try:
                result = await asyncio.wait_for(self.scan_event(game), timeout=45)
                if result:
                    print(f"  [OK] OPORTUNIDADE: {result.selection_name} @ {result.odd:.2f}")
                    opportunities.append(result)
                else:
                    print(f"  [OK] Sem oportunidade Under cartão vermelho")
            except asyncio.TimeoutError:
                print(f"  [TIMEOUT] {game.label} (>45s)")
                errors += 1
            except Exception as e:
                print(f"  [ERRO] {game.label}: {e}")
                errors += 1

        # Se todos falharam → browser provavelmente crashou
        if batch and errors == len(batch):
            print("[Scanner] Todos falharam, forçando recycle...")
            await self._browser.recycle()

        return opportunities

    # ── Internos ───────────────────────────────────────────────────

    @staticmethod
    async def _wait_for_tabs(page: Page) -> bool:
        """Espera as abas do evento renderizarem na SPA."""
        try:
            await page.wait_for_selector(
                "span.GTM-tab-name",
                timeout=settings.selector_timeout,
            )
            return True
        except Exception:
            # Retry com reload
            print("    [Scanner] Abas não apareceram, tentando reload...")
            try:
                await page.reload(
                    wait_until="domcontentloaded",
                    timeout=settings.page_load_timeout,
                )
                await asyncio.sleep(2)
                await page.wait_for_selector(
                    "span.GTM-tab-name",
                    timeout=settings.selector_timeout,
                )
                return True
            except Exception:
                return False

    @staticmethod
    async def _click_cards_tab(page: Page) -> bool:
        """Clica na aba 'Cartões' do evento.

        Tenta cada seletor em sequência (fallback chain).
        Não espera aqui — o caller é responsável pelo sleep pós-clique
        para dar tempo ao lazy-loading.
        """
        for selector in _TAB_SELECTORS:
            try:
                tab = page.locator(selector).first
                if await tab.count() > 0 and await tab.is_visible():
                    await tab.click(force=True, timeout=3000)
                    print(f"    [Scanner] Aba 'Cartões' clicada (seletor: {selector[:40]})")
                    return True
            except Exception:
                continue
        return False

    @staticmethod
    def _find_opportunity(
        game: GameContext,
        full_url: str,
        markets: dict,
        selections: dict,
    ) -> Optional[Opportunity]:
        """Busca mercado Under Cartão Vermelho nos dados interceptados."""
        for _mid, market in markets.items():
            market_name = market.get("name", "").lower().strip()

            # Ignorar mercados de jogador individual
            if "jogador" in market_name or "player" in market_name:
                continue

            # Verificar se é mercado de cartão vermelho
            if not any(v in market_name for v in VALID_MARKET_NAMES):
                continue

            # Resolver seleções (inline ou via IDs)
            market_sels = market.get("selections", [])
            if not market_sels:
                sel_ids = market.get("selectionIdList", [])
                market_sels = [
                    selections[str(sid)]
                    for sid in sel_ids
                    if str(sid) in selections
                ]

            for sel in market_sels:
                sel_name = sel.get("name", "").lower().strip()
                if sel_name not in UNDER_SELECTIONS:
                    continue

                price = sel.get("price", 0)
                if price and price >= settings.min_odd_threshold:
                    return Opportunity(
                        event_id=game.id,
                        home_team=game.home,
                        away_team=game.away,
                        odd=price,
                        market_name=market.get("name", ""),
                        selection_name=sel.get("name", ""),
                        url=full_url,
                        competition=game.competition,
                        minute=game.minute,
                        score=game.score,
                    )

        return None
