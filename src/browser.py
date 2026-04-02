"""Motor de evasão: Playwright Stealth + Sessão Quente.

Estratégia:
1. Lança Chromium com stealth patches no nível do contexto
2. Aquece sessão navegando na home → aceita cookies → instala sessão
3. Reutiliza o mesmo contexto para navegar internamente (como usuário real)
4. Rotação de User-Agent entre Chrome reais (Win/Mac)
"""

import asyncio
import random
from typing import Optional

from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    Playwright,
)
from playwright_stealth import Stealth

from src.config import settings

# ── Pool de User-Agents reais (Chrome 122-131, Win/Mac) ───────────
_USER_AGENTS = [
    # Chrome 131 — Windows 10
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    # Chrome 130 — Windows 11
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    # Chrome 131 — macOS Sonoma
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    # Chrome 129 — Windows 10
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    # Chrome 128 — macOS Ventura
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    # Chrome 122 — Windows 10
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]

# ── Viewports comuns (evita fingerprint fixo) ──────────────────────
_VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1366, "height": 768},
]


class BrowserEngine:
    """Gerencia o browser com evasão e sessão quente."""

    def __init__(self) -> None:
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._stealth = Stealth()
        self._warm: bool = False

    # ── Lifecycle ──────────────────────────────────────────────────

    async def start(self) -> None:
        """Inicia Playwright, browser e contexto com stealth."""
        self._playwright = await async_playwright().start()

        self._browser = await self._playwright.chromium.launch(
            headless=False,
            args=[
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-site-isolation-trials",
                "--window-size=1920,1080",
                "--start-maximized",
            ],
        )

        ua = random.choice(_USER_AGENTS)
        vp = random.choice(_VIEWPORTS)

        self._context = await self._browser.new_context(
            user_agent=ua,
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            viewport=vp,
            color_scheme="light",
            java_script_enabled=True,
            # Headers extras que um Chrome real envia
            extra_http_headers={
                "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
                "Sec-CH-UA-Platform": '"Windows"' if "Windows" in ua else '"macOS"',
            },
        )

        print(f"[Browser] Iniciado | UA: ...{ua[-40:]} | VP: {vp['width']}x{vp['height']}")

    async def warm_session(self) -> bool:
        """Sessão Quente: navega na home, aceita cookies, instala sessão.

        Retorna True se a sessão foi aquecida com sucesso.
        """
        if not self._context:
            return False

        page = await self._context.new_page()
        await self._stealth.apply_stealth_async(page)

        try:
            print("[Browser] Aquecendo sessão na home...")
            await page.goto(
                settings.base_url,
                wait_until="domcontentloaded",
                timeout=settings.page_load_timeout,
            )
            await asyncio.sleep(settings.warmup_delay)

            # Tratar modal de idade / cookies
            await self._dismiss_modals(page)
            await asyncio.sleep(1)

            cookies = await self._context.cookies()
            print(f"[Browser] Sessão quente — {len(cookies)} cookies instalados")
            self._warm = True
            return True

        except Exception as e:
            print(f"[Browser] AVISO: aquecimento falhou: {e}")
            self._warm = False
            return False

        finally:
            await page.close()

    async def stop(self) -> None:
        """Encerra contexto, browser e Playwright."""
        self._warm = False
        for resource in (self._context, self._browser):
            if resource:
                try:
                    await resource.close()
                except Exception:
                    pass
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
        self._context = None
        self._browser = None
        self._playwright = None
        print("[Browser] Encerrado")

    async def recycle(self) -> None:
        """Recicla browser completo (novo UA, novo viewport, nova sessão)."""
        print("[Browser] Reciclando...")
        await self.stop()
        await self.start()
        await self.warm_session()

    # ── Fetch via Browser ──────────────────────────────────────────

    async def fetch_json(self, url: str) -> Optional[dict]:
        """Busca JSON usando o contexto do browser (bypassa bloqueio de IP).

        Usa a sessão quente (cookies + fingerprint) para fazer a requisição
        via JS fetch(), contornando bloqueios de datacenter que afetam o
        curl_cffi direto.
        """
        if not self._context:
            return None

        page = await self._context.new_page()
        await self._stealth.apply_stealth_async(page)

        try:
            # Navega para a home como referer antes de fazer o fetch
            await page.goto(
                settings.base_url,
                wait_until="domcontentloaded",
                timeout=settings.page_load_timeout,
            )

            result = await page.evaluate(
                """async (url) => {
                    try {
                        const resp = await fetch(url, {
                            method: 'GET',
                            headers: {
                                'Accept': 'application/json, text/plain, */*',
                                'Accept-Language': 'pt-BR,pt;q=0.9',
                            },
                            credentials: 'include',
                        });
                        if (!resp.ok) return { __error: resp.status };
                        return await resp.json();
                    } catch(e) {
                        return { __error: String(e) };
                    }
                }""",
                url,
            )

            if isinstance(result, dict) and "__error" in result:
                print(f"  [Browser.fetch_json] Erro: {result['__error']}")
                return None

            return result

        except Exception as e:
            print(f"  [Browser.fetch_json] Exceção: {e}")
            return None

        finally:
            await page.close()

    # ── Navegação ──────────────────────────────────────────────────

    async def new_page(self) -> Page:
        """Cria nova aba no contexto quente, com stealth aplicado."""
        if not self._context:
            raise RuntimeError("Browser não iniciado. Chame start() primeiro.")

        page = await self._context.new_page()
        await self._stealth.apply_stealth_async(page)
        return page

    async def navigate(self, page: Page, url: str) -> bool:
        """Navega para URL usando o contexto quente.

        Simula navegação interna (não abre URL diretamente do zero).
        Retorna True se a página carregou com conteúdo válido.
        """
        try:
            await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=settings.page_load_timeout,
            )
            await asyncio.sleep(settings.navigation_delay)
            await self._dismiss_modals(page)

            # Verificar splash screen / body vazio
            if await self._is_blocked(page):
                print("    [Browser] Splash screen detectada, tentando reload...")
                await page.reload(wait_until="domcontentloaded", timeout=settings.page_load_timeout)
                await asyncio.sleep(settings.navigation_delay)
                await self._dismiss_modals(page)

                if await self._is_blocked(page):
                    print("    [Browser] Ainda bloqueado após reload")
                    return False

            return True

        except Exception as e:
            print(f"    [Browser] Erro na navegação: {e}")
            return False

    @property
    def is_warm(self) -> bool:
        return self._warm

    @property
    def is_alive(self) -> bool:
        return self._browser is not None and self._context is not None

    async def ensure_alive(self) -> None:
        """Garante que o browser está funcional; recicla se necessário."""
        if not self.is_alive:
            await self.recycle()
            return
        # Teste rápido: abrir e fechar uma aba
        try:
            page = await self._context.new_page()
            await page.close()
        except Exception:
            await self.recycle()

    # ── Internos ───────────────────────────────────────────────────

    @staticmethod
    async def _dismiss_modals(page: Page) -> None:
        """Fecha modais de idade, cookies e overlays genéricos."""
        try:
            # Botão "Sim, aceito" (modal de idade)
            await page.evaluate("""
                () => {
                    const btns = document.querySelectorAll('button, div[role="button"]');
                    for (const btn of btns) {
                        const t = btn.textContent?.toLowerCase() || '';
                        if (t.includes('sim') && t.includes('aceito')) {
                            btn.click();
                            return;
                        }
                    }
                }
            """)
            await asyncio.sleep(0.5)

            # Remover overlays residuais
            await page.evaluate("""
                () => {
                    const sels = [
                        '#age-verification-modal',
                        '.modal-backdrop',
                        '.sb-modal',
                        '[class*="overlay"]',
                        '[class*="splash"]',
                    ];
                    for (const s of sels) {
                        document.querySelectorAll(s).forEach(el => el.remove());
                    }
                    document.body.style.overflow = '';
                    document.body.style.position = '';
                }
            """)
        except Exception:
            pass

    @staticmethod
    async def _is_blocked(page: Page) -> bool:
        """Detecta se a página está bloqueada (splash screen ou body vazio)."""
        try:
            body_text = await page.evaluate(
                "() => (document.body?.innerText || '').trim()"
            )
            # Body vazio ou muito curto → provavelmente bloqueado
            if len(body_text) < 50:
                return True
            # Splash screen keywords
            lower = body_text.lower()
            if any(kw in lower for kw in ("splash", "checking your browser", "please wait")):
                return True
            return False
        except Exception:
            return True
