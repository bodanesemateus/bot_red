Refactor: Session Transfer & Persistent Tab
Tipo: Melhoria de performance / Engenharia
Prioridade: Alta
Estimativa total: ~1.5h
Pré-requisito: Nenhum. O sistema atual continua funcionando como fallback.
---
Contexto
Hoje o bot roda em EC2 (AWS, ASN AS16509). O curl_cffi sempre recebe HTTP 403 da Cloudflare porque IPs de datacenter têm score de bot elevado. O fallback atual usa BrowserEngine.fetch_json(), que abre uma nova aba, navega para a home, faz fetch() via JS e fecha a aba — levando ~8-15s por ciclo.
Este refactor implementa duas otimizações complementares que reduzem o tempo de discovery de ~10s para 200ms (melhor caso) ou 1-2s (pior caso).
---
Arquitetura Alvo: Fallback em 3 Estágios
Estágio 1: curl_cffi + cookies do Playwright     (~200ms)
    ├── HTTP 200 → usa resultado
    └── HTTP 403 → cookies expiraram, cai para estágio 2
Estágio 2: fetch() na aba persistente              (~1-2s)
    ├── OK → usa resultado + refresh cookies no curl_cffi
    └── Falhou → cai para estágio 3
Estágio 3: fetch_json (comportamento atual)         (~8-15s)
    └── Abre nova aba, navega home, fetch, fecha
---
História 1: Cookie/Session Transfer (Playwright → curl_cffi)
Problema
O Playwright já passa no challenge do Cloudflare durante a warm session e recebe ~27 cookies (incluindo cf_clearance). Esses cookies autenticam a sessão. O curl_cffi não os utiliza — faz requests "frias" que são rejeitadas pelo IP.
Solução
Exportar os cookies e o User-Agent do contexto Playwright e injetá-los numa curl_cffi.requests.Session persistente. Isso permite que o curl_cffi faça requests autenticadas com a sessão do browser.
Requisitos técnicos
1. O User-Agent no curl_cffi DEVE ser idêntico ao do Playwright (Cloudflare valida contra a sessão)
2. O impersonate deve ser Chrome (já é chrome131)
3. Os cookies precisam ser refreshed periodicamente (cf_clearance expira ~30min)
Implementação
Passo 1: Expor User-Agent no BrowserEngine
Arquivo: src/browser.py
O UA escolhido em start() (linha 86) é usado no contexto mas não é acessível externamente. Guardar como atributo da instância.
# browser.py — dentro de start(), APÓS linha 86
# ANTES:
ua = random.choice(_USER_AGENTS)
# DEPOIS:
ua = random.choice(_USER_AGENTS)
self._user_agent = ua  # Expor para session transfer
Adicionar property pública:
# browser.py — junto das outras properties (após linha 273)
@property
def user_agent(self) -> str:
    return getattr(self, "_user_agent", "")
Passo 2: Método para exportar cookies
Arquivo: src/browser.py
Adicionar método público que retorna cookies no formato compatível com curl_cffi:
# browser.py — após o método warm_session() (após linha 140)
async def export_cookies(self) -> list[dict]:
    """Exporta cookies do contexto para uso em clientes HTTP externos."""
    if not self._context:
        return []
    return await self._context.cookies()
Passo 3: Construir curl_cffi Session com cookies
Arquivo: main.py
Adicionar função que cria uma Session do curl_cffi alimentada com cookies do Playwright:
# main.py — após os imports, antes de _resolve_competition()
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
async def _refresh_curl_session(browser: BrowserEngine) -> curl_requests.Session | None:
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
Passo 4: Alterar _fetch_live_events para usar Session
Arquivo: main.py
Alterar a assinatura e o estágio 1 de _fetch_live_events() (atualmente linha 145):
# ANTES (linha 145):
async def _fetch_live_events(browser: "BrowserEngine") -> list[GameContext]:
# DEPOIS:
async def _fetch_live_events(
    browser: "BrowserEngine",
    curl_session: curl_requests.Session | None = None,
) -> list[GameContext]:
Substituir o estágio 1 (linhas 152-183). Em vez de curl_requests.get() sem cookies, usar curl_session.get():
    # ── Estágio 1: curl_cffi com cookies do Playwright ─────────────
    if curl_session:
        try:
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
                return games
            print(f"  [API] curl_cffi+cookies falhou ({response.status_code}) → fallback browser")
        except Exception as e:
            print(f"  [API] curl_cffi+cookies erro ({e}) → fallback browser")
    # ── Estágio 2 e 3: browser (ver História 2) ────────────────────
    # ... (manter fallback browser existente)
Passo 5: Integrar no loop principal
Arquivo: main.py, dentro de run() (atualmente linha 206)
Após warm_session(), criar a session inicial. Refreshar a cada N ciclos:
    # Após warm_session() (linha 220):
    curl_session = await _refresh_curl_session(browser)
    
    # Dentro do while True, ANTES de _fetch_live_events:
    # Refresh cookies a cada 5 ciclos (~25 min com cooldown=300s)
    if cycle > 1 and cycle % 5 == 0:
        curl_session = await _refresh_curl_session(browser) or curl_session
    
    # Passar session para _fetch_live_events:
    games = await _fetch_live_events(browser, curl_session)
    
    # Se o curl_cffi falhou com 403, forçar refresh no próximo ciclo
    # (implementar via flag ou verificar nos logs)
Passo 6: Refresh automático on-failure
Adicionar lógica para que, se o estágio 1 retornar 403, force refresh dos cookies no próximo ciclo. A forma mais simples:
# Em _fetch_live_events, retornar tuple (games, needs_refresh):
async def _fetch_live_events(
    browser: "BrowserEngine",
    curl_session: curl_requests.Session | None = None,
) -> tuple[list[GameContext], bool]:
    """Retorna (jogos, needs_cookie_refresh)."""
    needs_refresh = False
    
    # Estágio 1: curl_cffi + cookies
    if curl_session:
        try:
            response = curl_session.get(settings.overview_url, timeout=15)
            if response.status_code == 200:
                # ... parse e retorna
                return games, False
            else:
                needs_refresh = True  # cookies podem ter expirado
        except Exception:
            needs_refresh = True
    
    # Estágio 2/3: browser fallback
    # ... (código existente)
    return games, needs_refresh
# No loop principal:
games, needs_refresh = await _fetch_live_events(browser, curl_session)
if needs_refresh:
    curl_session = await _refresh_curl_session(browser) or curl_session
Risco: Session Pinning
O Cloudflare pode vincular o cf_clearance ao TLS fingerprint exato do Chromium. Se o JA3 do Playwright for diferente do JA3 do curl_cffi impersonate=chrome131, os cookies serão rejeitados.
Como verificar: Nos logs, se o estágio 1 sempre retornar 403 mesmo com cookies válidos, é session pinning. Nesse caso, o estágio 2 (aba persistente) assume como método primário.
Não é blocker: O fallback para browser funciona independente.
Critérios de aceite
- [ ] Após warm_session, curl_cffi recebe cookies do Playwright
- [ ] curl_cffi usa o mesmo User-Agent do Playwright
- [ ] Logs mostram curl_cffi+cookies HTTP 200 (se não houver session pinning)
- [ ] Se 403, cai automaticamente para fallback browser
- [ ] Cookies são refreshed a cada ~25 min
- [ ] Nenhuma regressão: se cookie transfer não funcionar, comportamento é idêntico ao atual
---
História 2: Aba Persistente para fetch_json
Problema
BrowserEngine.fetch_json() (browser.py:170-222) abre uma nova aba, aplica stealth, navega para a home inteira, faz page.evaluate(fetch()), e fecha. São ~8-15s desperdiçados. Os cookies já existem no contexto — a navegação para home é overhead.
Solução
Manter uma aba aberta na home como membro da classe. Reutilizá-la para todas as chamadas fetch_json(). A aba só é recriada se ficar stale ou no recycle.
Implementação
Passo 1: Aba persistente como atributo
Arquivo: src/browser.py
Adicionar atributo no __init__ (linha 59):
# browser.py:59 — __init__
self._fetch_page: Optional[Page] = None
Passo 2: Inicializar aba na warm_session
Arquivo: src/browser.py
No final de warm_session(), em vez de fechar a page, guardá-la como _fetch_page:
# browser.py — substituir warm_session() (linhas 105-140)
async def warm_session(self) -> bool:
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
        await self._dismiss_modals(page)
        await asyncio.sleep(1)
        cookies = await self._context.cookies()
        print(f"[Browser] Sessão quente — {len(cookies)} cookies instalados")
        self._warm = True
        # Guardar aba para fetch_json reutilizar
        # (já está na home, com cookies e contexto correto)
        if self._fetch_page:
            try:
                await self._fetch_page.close()
            except Exception:
                pass
        self._fetch_page = page
        return True
    except Exception as e:
        print(f"[Browser] AVISO: aquecimento falhou: {e}")
        self._warm = False
        await page.close()
        return False
    # NÃO fechar page aqui — ela agora é self._fetch_page
Passo 3: fetch_json usando aba persistente
Arquivo: src/browser.py
Reescrever fetch_json() (linhas 170-222):
async def fetch_json(self, url: str) -> Optional[dict]:
    """Busca JSON usando aba persistente (fast path) ou nova aba (fallback)."""
    
    # Fast path: usar aba persistente já na home
    if self._fetch_page:
        try:
            result = await self._fetch_page.evaluate(
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
            if isinstance(result, dict) and "__error" not in result:
                return result
            print(f"  [Browser.fetch_json] Aba persistente falhou: {result.get('__error')}")
            # Aba pode ter ficado stale — fechar e cair pro fallback
            await self._fetch_page.close()
            self._fetch_page = None
        except Exception as e:
            print(f"  [Browser.fetch_json] Aba persistente erro: {e}")
            try:
                await self._fetch_page.close()
            except Exception:
                pass
            self._fetch_page = None
    # Fallback: abrir nova aba (comportamento original)
    if not self._context:
        return None
    page = await self._context.new_page()
    await self._stealth.apply_stealth_async(page)
    try:
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
            print(f"  [Browser.fetch_json] Fallback erro: {result['__error']}")
            return None
        # Promover aba para persistente se deu certo
        self._fetch_page = page
        page = None  # Não fechar no finally
        return result
    except Exception as e:
        print(f"  [Browser.fetch_json] Fallback exceção: {e}")
        return None
    finally:
        if page:  # Só fecha se não foi promovida
            await page.close()
Passo 4: Limpar aba no stop() e recycle()
Arquivo: src/browser.py
No stop() (linha 142), fechar _fetch_page:
async def stop(self) -> None:
    self._warm = False
    # Fechar aba persistente
    if self._fetch_page:
        try:
            await self._fetch_page.close()
        except Exception:
            pass
        self._fetch_page = None
    # ... resto do stop existente
Critérios de aceite
- [ ] Após warm_session, _fetch_page está aberta na home
- [ ] fetch_json() reutiliza a aba sem renavegar (~1-2s)
- [ ] Se a aba ficar stale (erro/timeout), cai para fallback (nova aba)
- [ ] Fallback promove a nova aba para persistente se der certo
- [ ] recycle() e stop() limpam a aba
- [ ] Nenhum memory leak (aba não fica duplicada)
---
Ordem de implementação
1. História 2 primeiro (aba persistente) — é o fallback seguro e melhoria garantida
2. História 1 depois (cookie transfer) — depende da História 2 como fallback
3. Testar em produção: observar logs por ~1h para confirmar qual estágio está sendo usado
4. Se cookie transfer funcionar: a maioria dos ciclos leva ~200ms
5. Se não funcionar (session pinning): aba persistente já garante ~1-2s
---
Como testar
# Deploy
rsync ... && ssh ... "cd bot_red && docker compose down && docker compose up -d --build"
# Observar logs
ssh ... "cd bot_red && docker compose logs -f"
Sucesso da História 1: Logs mostram curl_cffi+cookies HTTP 200
Sucesso da História 2: Logs NÃO mostram Navegando: https://www.betano.bet.br no fetch_json (aba reutilizada)
Fallback funcionando: Se aparecer Aba persistente falhou seguido de resultado OK no fallback