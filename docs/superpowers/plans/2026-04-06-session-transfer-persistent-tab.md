# Session Transfer & Persistent Tab — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduzir o tempo de discovery de ~10s para 200ms (melhor caso) via fallback em 3 estágios: curl_cffi+cookies → aba persistente → nova aba.

**Architecture:** História 2 primeiro (`BrowserEngine` mantém aba persistente em `_fetch_page`, reutilizada em `fetch_json`). História 1 depois (`BrowserEngine` expõe cookies e UA; `main.py` cria `curl_cffi.Session` autenticada e a passa para `_fetch_live_events`, que retorna `(list[GameContext], bool)`).

**Tech Stack:** Python 3.11+, Playwright async, curl_cffi, pytest, pytest-asyncio, unittest.mock

---

## File Map

| Arquivo | Mudança |
|---------|---------|
| `src/browser.py` | + `_fetch_page`, `_user_agent`; rewrite `warm_session`, `fetch_json`, `stop`; + `export_cookies`, `user_agent` property |
| `main.py` | + `_build_curl_session`, `_refresh_curl_session`; rewrite `_fetch_live_events` (nova assinatura + retorno tuple); rewrite `run` (init/refresh session) |
| `tests/test_browser.py` | Testes unitários para as mudanças em browser.py |
| `tests/test_main.py` | Testes unitários para as mudanças em main.py |

---

## Tarefa 1: Aba Persistente — atributos e `__init__`

**Files:**
- Modify: `src/browser.py:59-64`
- Test: `tests/test_browser.py`

- [ ] **Step 1: Criar arquivo de testes (se não existir)**

```bash
ls tests/ 2>/dev/null || mkdir tests && touch tests/__init__.py
```

- [ ] **Step 2: Escrever teste para `_fetch_page` inicial**

`tests/test_browser.py`:
```python
"""Testes unitários para BrowserEngine."""
import pytest
from src.browser import BrowserEngine


def test_fetch_page_starts_none():
    engine = BrowserEngine()
    assert engine._fetch_page is None


def test_user_agent_starts_empty():
    engine = BrowserEngine()
    assert engine.user_agent == ""
```

- [ ] **Step 3: Rodar testes para confirmar falha**

```bash
pytest tests/test_browser.py::test_fetch_page_starts_none tests/test_browser.py::test_user_agent_starts_empty -v
```

Esperado: `FAILED — AttributeError: '_fetch_page'` e `AttributeError: 'user_agent'`

- [ ] **Step 4: Adicionar `_fetch_page` e `_user_agent` no `__init__`**

Em `src/browser.py`, substituir o bloco `__init__` (linhas 59-64):

```python
    def __init__(self) -> None:
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._stealth = Stealth()
        self._warm: bool = False
        self._fetch_page: Optional[Page] = None
        self._user_agent: str = ""
```

- [ ] **Step 5: Rodar testes para confirmar verde**

```bash
pytest tests/test_browser.py::test_fetch_page_starts_none tests/test_browser.py::test_user_agent_starts_empty -v
```

Esperado: `2 passed`

- [ ] **Step 6: Commit**

```bash
git add src/browser.py tests/test_browser.py
git commit -m "feat: add _fetch_page and _user_agent attributes to BrowserEngine"
```

---

## Tarefa 2: Expor `user_agent` e salvar UA no `start()`

**Files:**
- Modify: `src/browser.py:86` (dentro de `start()`)
- Modify: `src/browser.py:267-273` (bloco de properties)
- Test: `tests/test_browser.py`

- [ ] **Step 1: Escrever teste para a property `user_agent`**

Adicionar em `tests/test_browser.py`:
```python
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_start_saves_user_agent():
    """Após start(), user_agent deve ser um dos UAs da pool."""
    from src.browser import _USER_AGENTS

    engine = BrowserEngine()

    mock_context = MagicMock()
    mock_browser = MagicMock()
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_playwright = MagicMock()
    mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)

    with patch("src.browser.async_playwright") as mock_ap:
        mock_ap.return_value.__aenter__ = AsyncMock(return_value=mock_playwright)
        mock_ap.return_value.start = AsyncMock(return_value=mock_playwright)
        await engine.start()

    assert engine.user_agent in _USER_AGENTS
    assert engine._user_agent != ""
```

- [ ] **Step 2: Rodar para confirmar falha**

```bash
pytest tests/test_browser.py::test_start_saves_user_agent -v
```

Esperado: `FAILED — AssertionError: '' not in _USER_AGENTS`

- [ ] **Step 3: Salvar UA no `start()` e adicionar property**

Em `src/browser.py`, linha 86, substituir:
```python
        ua = random.choice(_USER_AGENTS)
```
por:
```python
        ua = random.choice(_USER_AGENTS)
        self._user_agent = ua
```

Adicionar a property após a linha `is_alive` (após linha 273):
```python
    @property
    def user_agent(self) -> str:
        return self._user_agent
```

- [ ] **Step 4: Rodar testes**

```bash
pytest tests/test_browser.py -v
```

Esperado: todos passando (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/browser.py tests/test_browser.py
git commit -m "feat: expose user_agent property on BrowserEngine"
```

---

## Tarefa 3: `export_cookies()` no `BrowserEngine`

**Files:**
- Modify: `src/browser.py` (após `warm_session()`, ~linha 140)
- Test: `tests/test_browser.py`

- [ ] **Step 1: Escrever testes**

Adicionar em `tests/test_browser.py`:
```python
@pytest.mark.asyncio
async def test_export_cookies_no_context():
    """Sem contexto, retorna lista vazia."""
    engine = BrowserEngine()
    result = await engine.export_cookies()
    assert result == []


@pytest.mark.asyncio
async def test_export_cookies_with_context():
    """Com contexto, chama context.cookies() e retorna resultado."""
    engine = BrowserEngine()
    fake_cookies = [{"name": "cf_clearance", "value": "abc123", "domain": ".betano.bet.br"}]
    mock_context = MagicMock()
    mock_context.cookies = AsyncMock(return_value=fake_cookies)
    engine._context = mock_context

    result = await engine.export_cookies()

    assert result == fake_cookies
    mock_context.cookies.assert_called_once()
```

- [ ] **Step 2: Rodar para confirmar falha**

```bash
pytest tests/test_browser.py::test_export_cookies_no_context tests/test_browser.py::test_export_cookies_with_context -v
```

Esperado: `FAILED — AttributeError: 'BrowserEngine' object has no attribute 'export_cookies'`

- [ ] **Step 3: Implementar `export_cookies()`**

Em `src/browser.py`, adicionar após o método `warm_session()` (após a linha `finally: await page.close()`):

```python
    async def export_cookies(self) -> list[dict]:
        """Exporta cookies do contexto para uso em clientes HTTP externos."""
        if not self._context:
            return []
        return await self._context.cookies()
```

- [ ] **Step 4: Rodar testes**

```bash
pytest tests/test_browser.py -v
```

Esperado: todos passando (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/browser.py tests/test_browser.py
git commit -m "feat: add export_cookies() to BrowserEngine"
```

---

## Tarefa 4: Reescrever `warm_session()` para manter aba persistente

**Files:**
- Modify: `src/browser.py:105-140` (método `warm_session`)
- Test: `tests/test_browser.py`

- [ ] **Step 1: Escrever teste**

Adicionar em `tests/test_browser.py`:
```python
@pytest.mark.asyncio
async def test_warm_session_saves_fetch_page():
    """warm_session() deve salvar a aba em _fetch_page em vez de fechá-la."""
    engine = BrowserEngine()

    mock_page = MagicMock()
    mock_page.goto = AsyncMock()
    mock_page.evaluate = AsyncMock()
    mock_page.close = AsyncMock()

    mock_context = MagicMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_context.cookies = AsyncMock(return_value=[{"name": "cf_clearance", "value": "x"}])
    engine._context = mock_context

    with patch.object(engine._stealth, "apply_stealth_async", AsyncMock()):
        with patch.object(engine, "_dismiss_modals", AsyncMock()):
            result = await engine.warm_session()

    assert result is True
    assert engine._fetch_page is mock_page
    mock_page.close.assert_not_called()  # NÃO deve fechar


@pytest.mark.asyncio
async def test_warm_session_failure_closes_page():
    """Em caso de erro, a aba deve ser fechada."""
    engine = BrowserEngine()

    mock_page = MagicMock()
    mock_page.goto = AsyncMock(side_effect=Exception("timeout"))
    mock_page.close = AsyncMock()

    mock_context = MagicMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)
    engine._context = mock_context

    with patch.object(engine._stealth, "apply_stealth_async", AsyncMock()):
        result = await engine.warm_session()

    assert result is False
    mock_page.close.assert_called_once()
    assert engine._fetch_page is None
```

- [ ] **Step 2: Rodar para confirmar falha**

```bash
pytest tests/test_browser.py::test_warm_session_saves_fetch_page tests/test_browser.py::test_warm_session_failure_closes_page -v
```

Esperado: `FAILED` — `mock_page.close.assert_not_called()` vai falhar porque `finally` fecha a aba.

- [ ] **Step 3: Reescrever `warm_session()`**

Substituir o método `warm_session()` completo em `src/browser.py`:

```python
    async def warm_session(self) -> bool:
        """Sessão Quente: navega na home, aceita cookies, instala sessão.

        Retorna True se a sessão foi aquecida com sucesso.
        Guarda a aba aberta em _fetch_page para reutilização em fetch_json().
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

            # Fechar aba persistente anterior se existir
            if self._fetch_page:
                try:
                    await self._fetch_page.close()
                except Exception:
                    pass
            # Guardar aba para fetch_json reutilizar (já está na home)
            self._fetch_page = page
            return True

        except Exception as e:
            print(f"[Browser] AVISO: aquecimento falhou: {e}")
            self._warm = False
            await page.close()
            return False
```

- [ ] **Step 4: Rodar testes**

```bash
pytest tests/test_browser.py -v
```

Esperado: todos passando (7 passed)

- [ ] **Step 5: Commit**

```bash
git add src/browser.py tests/test_browser.py
git commit -m "feat: warm_session() keeps persistent tab instead of closing it"
```

---

## Tarefa 5: Reescrever `fetch_json()` com aba persistente

**Files:**
- Modify: `src/browser.py:170-222` (método `fetch_json`)
- Test: `tests/test_browser.py`

- [ ] **Step 1: Escrever testes**

Adicionar em `tests/test_browser.py`:
```python
@pytest.mark.asyncio
async def test_fetch_json_uses_persistent_page():
    """fetch_json() usa _fetch_page sem abrir nova aba."""
    engine = BrowserEngine()
    fake_data = {"events": {}, "leagues": {}}

    mock_page = MagicMock()
    mock_page.evaluate = AsyncMock(return_value=fake_data)
    engine._fetch_page = mock_page

    mock_context = MagicMock()
    mock_context.new_page = AsyncMock()
    engine._context = mock_context

    result = await engine.fetch_json("https://example.com/api")

    assert result == fake_data
    mock_context.new_page.assert_not_called()  # Não abriu nova aba


@pytest.mark.asyncio
async def test_fetch_json_fallback_when_persistent_fails():
    """fetch_json() cai para nova aba se a aba persistente falhar."""
    engine = BrowserEngine()
    fake_data = {"events": {}}

    mock_persistent = MagicMock()
    mock_persistent.evaluate = AsyncMock(return_value={"__error": 403})
    mock_persistent.close = AsyncMock()
    engine._fetch_page = mock_persistent

    mock_fallback = MagicMock()
    mock_fallback.goto = AsyncMock()
    mock_fallback.evaluate = AsyncMock(return_value=fake_data)
    mock_fallback.close = AsyncMock()

    mock_context = MagicMock()
    mock_context.new_page = AsyncMock(return_value=mock_fallback)
    engine._context = mock_context

    with patch.object(engine._stealth, "apply_stealth_async", AsyncMock()):
        result = await engine.fetch_json("https://example.com/api")

    assert result == fake_data
    mock_persistent.close.assert_called_once()
    # Fallback promovida para persistente
    assert engine._fetch_page is mock_fallback


@pytest.mark.asyncio
async def test_fetch_json_no_context_returns_none():
    """Sem contexto e sem aba persistente, retorna None."""
    engine = BrowserEngine()
    result = await engine.fetch_json("https://example.com/api")
    assert result is None
```

- [ ] **Step 2: Rodar para confirmar falha**

```bash
pytest tests/test_browser.py::test_fetch_json_uses_persistent_page tests/test_browser.py::test_fetch_json_fallback_when_persistent_fails tests/test_browser.py::test_fetch_json_no_context_returns_none -v
```

Esperado: `FAILED` — comportamento atual sempre abre nova aba.

- [ ] **Step 3: Reescrever `fetch_json()`**

Substituir o método completo em `src/browser.py`:

```python
    async def fetch_json(self, url: str) -> Optional[dict]:
        """Busca JSON usando aba persistente (fast path) ou nova aba (fallback).

        Fast path: reutiliza _fetch_page já na home (~1-2s).
        Fallback: abre nova aba, navega home, faz fetch (~8-15s).
        """
        # ── Fast path: aba persistente ────────────────────────────────
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
                await self._fetch_page.close()
                self._fetch_page = None
            except Exception as e:
                print(f"  [Browser.fetch_json] Aba persistente erro: {e}")
                try:
                    await self._fetch_page.close()
                except Exception:
                    pass
                self._fetch_page = None

        # ── Fallback: nova aba ────────────────────────────────────────
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
            if page:
                await page.close()
```

- [ ] **Step 4: Rodar todos os testes**

```bash
pytest tests/test_browser.py -v
```

Esperado: todos passando (10 passed)

- [ ] **Step 5: Commit**

```bash
git add src/browser.py tests/test_browser.py
git commit -m "feat: fetch_json() uses persistent tab as fast path with fallback"
```

---

## Tarefa 6: `stop()` fecha `_fetch_page`

**Files:**
- Modify: `src/browser.py:142-159` (método `stop`)
- Test: `tests/test_browser.py`

- [ ] **Step 1: Escrever teste**

Adicionar em `tests/test_browser.py`:
```python
@pytest.mark.asyncio
async def test_stop_closes_fetch_page():
    """stop() deve fechar _fetch_page se existir."""
    engine = BrowserEngine()

    mock_page = MagicMock()
    mock_page.close = AsyncMock()
    engine._fetch_page = mock_page

    mock_context = MagicMock()
    mock_context.close = AsyncMock()
    mock_browser = MagicMock()
    mock_browser.close = AsyncMock()
    mock_playwright = MagicMock()
    mock_playwright.stop = AsyncMock()

    engine._context = mock_context
    engine._browser = mock_browser
    engine._playwright = mock_playwright

    await engine.stop()

    mock_page.close.assert_called_once()
    assert engine._fetch_page is None
```

- [ ] **Step 2: Rodar para confirmar falha**

```bash
pytest tests/test_browser.py::test_stop_closes_fetch_page -v
```

Esperado: `FAILED — mock_page.close.assert_called_once()` falha (stop atual não fecha _fetch_page)

- [ ] **Step 3: Atualizar `stop()`**

Substituir o método `stop()` em `src/browser.py`:

```python
    async def stop(self) -> None:
        """Encerra contexto, browser e Playwright."""
        self._warm = False
        # Fechar aba persistente
        if self._fetch_page:
            try:
                await self._fetch_page.close()
            except Exception:
                pass
            self._fetch_page = None
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
```

- [ ] **Step 4: Rodar todos os testes**

```bash
pytest tests/test_browser.py -v
```

Esperado: todos passando (11 passed)

- [ ] **Step 5: Commit**

```bash
git add src/browser.py tests/test_browser.py
git commit -m "feat: stop() cleans up persistent fetch tab"
```

---

## Tarefa 7: `_build_curl_session()` e `_refresh_curl_session()` em `main.py`

**Files:**
- Modify: `main.py` (após imports, antes de `_resolve_competition`)
- Test: `tests/test_main.py`

- [ ] **Step 1: Criar arquivo de testes**

```bash
touch tests/test_main.py
```

- [ ] **Step 2: Escrever testes**

`tests/test_main.py`:
```python
"""Testes unitários para main.py."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def test_build_curl_session_sets_cookies():
    """_build_curl_session injeta todos os cookies na session."""
    from main import _build_curl_session

    cookies = [
        {"name": "cf_clearance", "value": "abc", "domain": ".betano.bet.br", "path": "/"},
        {"name": "session_id", "value": "xyz", "domain": ".betano.bet.br", "path": "/"},
    ]
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0"

    session = _build_curl_session(cookies, ua)

    assert session.headers.get("User-Agent") == ua
    assert session.cookies.get("cf_clearance") == "abc"
    assert session.cookies.get("session_id") == "xyz"


def test_build_curl_session_sets_required_headers():
    """_build_curl_session define os headers de segurança obrigatórios."""
    from main import _build_curl_session

    session = _build_curl_session([], "test-ua")

    assert session.headers.get("Accept") == "application/json, text/plain, */*"
    assert "Sec-Fetch-Dest" in session.headers
    assert "Sec-Fetch-Mode" in session.headers


@pytest.mark.asyncio
async def test_refresh_curl_session_returns_none_without_ua():
    """Se o browser não tiver UA, retorna None."""
    from main import _refresh_curl_session

    mock_browser = MagicMock()
    mock_browser.export_cookies = AsyncMock(return_value=[{"name": "x", "value": "y"}])
    mock_browser.user_agent = ""  # UA vazio

    result = await _refresh_curl_session(mock_browser)

    assert result is None


@pytest.mark.asyncio
async def test_refresh_curl_session_returns_session_with_cookies():
    """Com cookies e UA válidos, retorna uma Session configurada."""
    from main import _refresh_curl_session
    from curl_cffi import requests as curl_requests

    mock_browser = MagicMock()
    mock_browser.export_cookies = AsyncMock(return_value=[
        {"name": "cf_clearance", "value": "tok123", "domain": ".betano.bet.br", "path": "/"}
    ])
    mock_browser.user_agent = "Mozilla/5.0 Chrome/131"

    result = await _refresh_curl_session(mock_browser)

    assert isinstance(result, curl_requests.Session)
    assert result.cookies.get("cf_clearance") == "tok123"
```

- [ ] **Step 3: Rodar para confirmar falha**

```bash
pytest tests/test_main.py -v
```

Esperado: `FAILED — ImportError: cannot import name '_build_curl_session'`

- [ ] **Step 4: Implementar as funções em `main.py`**

Em `main.py`, adicionar após os imports (linha 20), antes de `_resolve_competition`:

```python
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
```

- [ ] **Step 5: Rodar testes**

```bash
pytest tests/test_main.py -v
```

Esperado: todos passando (4 passed)

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat: add _build_curl_session and _refresh_curl_session to main.py"
```

---

## Tarefa 8: Reescrever `_fetch_live_events()` com 3 estágios

**Files:**
- Modify: `main.py:145-203` (função `_fetch_live_events`)
- Test: `tests/test_main.py`

- [ ] **Step 1: Escrever testes**

Adicionar em `tests/test_main.py`:
```python
@pytest.mark.asyncio
async def test_fetch_live_events_uses_curl_session_on_200():
    """Estágio 1: curl_session.get() com 200 retorna jogos e needs_refresh=False."""
    from main import _fetch_live_events

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"data"
    mock_response.json = MagicMock(return_value={"events": {}, "leagues": {}, "regions": {}})

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_response)

    mock_browser = MagicMock()

    games, needs_refresh = await _fetch_live_events(mock_browser, mock_session)

    assert games == []
    assert needs_refresh is False
    mock_session.get.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_live_events_needs_refresh_on_403():
    """Estágio 1: 403 marca needs_refresh=True e cai para browser."""
    from main import _fetch_live_events

    mock_response = MagicMock()
    mock_response.status_code = 403
    mock_response.content = b""

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_response)

    mock_browser = MagicMock()
    mock_browser.fetch_json = AsyncMock(return_value={"events": {}, "leagues": {}, "regions": {}})

    games, needs_refresh = await _fetch_live_events(mock_browser, mock_session)

    assert needs_refresh is True


@pytest.mark.asyncio
async def test_fetch_live_events_without_session_uses_browser():
    """Sem curl_session, vai direto para browser (comportamento anterior)."""
    from main import _fetch_live_events

    mock_browser = MagicMock()
    mock_browser.fetch_json = AsyncMock(return_value={"events": {}, "leagues": {}, "regions": {}})

    with patch("main.curl_requests") as mock_curl:
        games, needs_refresh = await _fetch_live_events(mock_browser, curl_session=None)

    # curl_requests.get não foi chamado
    mock_curl.get.assert_not_called()
    mock_browser.fetch_json.assert_called_once()
```

- [ ] **Step 2: Rodar para confirmar falha**

```bash
pytest tests/test_main.py::test_fetch_live_events_uses_curl_session_on_200 tests/test_main.py::test_fetch_live_events_needs_refresh_on_403 tests/test_main.py::test_fetch_live_events_without_session_uses_browser -v
```

Esperado: `FAILED` — assinatura atual não aceita `curl_session` e não retorna tuple.

- [ ] **Step 3: Reescrever `_fetch_live_events()`**

Substituir a função completa em `main.py`:

```python
async def _fetch_live_events(
    browser: "BrowserEngine",
    curl_session: curl_requests.Session | None = None,
) -> tuple[list[GameContext], bool]:
    """Busca eventos ao vivo com fallback em 3 estágios.

    Retorna (jogos, needs_cookie_refresh).
    needs_cookie_refresh=True indica que os cookies expiraram e devem
    ser renovados antes do próximo ciclo.
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
```

- [ ] **Step 4: Rodar todos os testes de main**

```bash
pytest tests/test_main.py -v
```

Esperado: todos passando (7 passed)

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat: _fetch_live_events() implements 3-stage fallback with curl_session"
```

---

## Tarefa 9: Integrar session no loop `run()`

**Files:**
- Modify: `main.py:206-291` (função `run`)

> Nota: Esta tarefa não tem testes unitários pois `run()` é o loop principal de integração. A verificação é manual via logs em produção.

- [ ] **Step 1: Atualizar `run()` para inicializar e usar a session**

Substituir a função `run()` em `main.py`:

```python
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

    # Criar session curl_cffi com cookies do Playwright
    curl_session = await _refresh_curl_session(browser)

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

            # Reciclagem periódica (recycle já faz warm_session internamente)
            if cycle > 1 and cycle % settings.recycle_every_n_cycles == 0:
                await browser.recycle()
                curl_session = await _refresh_curl_session(browser)

            # Refresh cookies a cada 5 ciclos (~25 min com cooldown=300s)
            elif cycle > 1 and cycle % 5 == 0:
                curl_session = await _refresh_curl_session(browser) or curl_session

            # Fase 1: buscar eventos ao vivo (3 estágios)
            games, needs_refresh = await _fetch_live_events(browser, curl_session)

            # Se cookies expiraram, renovar antes do próximo ciclo
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
                alerted_events.add(f"{opp.event_id}:{opp.selection_name}")

            total_opportunities += len(new_opps)

            print(f"Aguardando {settings.cooldown_seconds}s...")
            await asyncio.sleep(settings.cooldown_seconds)

    except KeyboardInterrupt:
        print("\nEncerrando...")
    finally:
        await browser.stop()
        print(f"\nTotal de oportunidades: {total_opportunities}")
```

- [ ] **Step 2: Rodar toda a suite de testes**

```bash
pytest tests/ -v
```

Esperado: todos passando (11 passed)

- [ ] **Step 3: Verificar que não há erros de import**

```bash
python -c "import main; print('OK')"
```

Esperado: `OK`

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "feat: integrate curl_session into run() loop with periodic refresh"
```

---

## Tarefa 10: Verificação Final

- [ ] **Step 1: Rodar suite completa**

```bash
pytest tests/ -v --tb=short
```

Esperado: todos passando, 0 erros.

- [ ] **Step 2: Verificar tipagem (opcional, se mypy instalado)**

```bash
python -m mypy main.py src/browser.py --ignore-missing-imports 2>/dev/null || echo "mypy not installed, skip"
```

- [ ] **Step 3: Checar logs esperados pós-deploy**

Após `docker compose up -d --build`, observar os logs com:
```bash
docker compose logs -f
```

Logs esperados (História 2 OK):
```
[Browser] Sessão quente — 27 cookies instalados
  [Session] curl_cffi atualizada com 27 cookies
```

Logs esperados (História 1 OK — sem session pinning):
```
  [API] curl_cffi+cookies HTTP 200 | 45231 bytes
  [API] curl_cffi+cookies OK | 12 jogos
```

Logs que indicam session pinning (fallback funcionando):
```
  [API] curl_cffi+cookies falhou (403) → fallback browser
  [API] Browser fetch ...
  [API] Browser OK | 12 jogos
```

Logs que indicam aba persistente em uso (História 2 OK):
```
  [API] Browser fetch ...
  [API] Browser OK | 12 jogos
```
**E ausência de:** `Navegando: https://www.betano.bet.br` no `fetch_json`.

---

## Resumo das Mudanças

### `src/browser.py`
| Mudança | Linha original | Descrição |
|---------|---------------|-----------|
| `__init__` | 59-64 | + `_fetch_page`, `_user_agent` |
| `start()` | 86 | Salva UA em `self._user_agent` |
| `warm_session()` | 105-140 | Mantém aba em `_fetch_page` em vez de fechar |
| `export_cookies()` | novo, após 140 | Exporta cookies do contexto |
| `fetch_json()` | 170-222 | Aba persistente first, nova aba como fallback |
| `stop()` | 142-159 | Fecha `_fetch_page` antes do resto |
| `user_agent` property | novo, após 273 | Acesso público ao UA |

### `main.py`
| Mudança | Linha original | Descrição |
|---------|---------------|-----------|
| `_build_curl_session()` | novo, após imports | Cria Session curl_cffi com cookies |
| `_refresh_curl_session()` | novo, após `_build_curl_session` | Exporta cookies e cria/atualiza Session |
| `_fetch_live_events()` | 145-203 | Nova assinatura + 3 estágios + retorna tuple |
| `run()` | 206-291 | Init session + refresh periódico + usa tuple |
