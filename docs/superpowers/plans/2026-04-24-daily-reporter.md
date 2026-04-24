# Daily Reporter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar uma task asyncio que às 23:45 valida via SofaScore se as apostas Under Cartão Vermelho alertadas no dia se concretizaram e envia um relatório no Telegram.

**Architecture:** Uma asyncio.Task (`daily_reporter`) roda em paralelo ao loop principal, dorme até 23:45, faz polling no SofaScore para cada oportunidade salva em JSON no dia e envia o relatório. O JSON é apagado após o envio.

**Tech Stack:** Python 3.11, httpx (async), pytest, pytest-asyncio, difflib (stdlib)

---

## File Map

| Arquivo | Ação | Responsabilidade |
|---|---|---|
| `src/models.py` | Modificar | Adicionar `MatchResult` dataclass |
| `src/opportunity_log.py` | Criar | Leitura/escrita do JSON diário |
| `src/sofascore.py` | Criar | Scraping SofaScore — busca de evento + cartões |
| `src/telegram_notifier.py` | Modificar | Adicionar `send_daily_report()` |
| `main.py` | Modificar | Adicionar task `daily_reporter` + `opportunity_log.append()` |
| `docker-compose.yml` | Modificar | Montar volume `./data:/app/data` |
| `requirements.txt` | Modificar | Adicionar `pytest`, `pytest-asyncio` |
| `tests/__init__.py` | Criar | Pacote de testes |
| `tests/test_opportunity_log.py` | Criar | Testes do log JSON |
| `tests/test_sofascore.py` | Criar | Testes do scraper SofaScore |
| `tests/test_daily_report.py` | Criar | Testes do relatório Telegram |
| `data/.gitkeep` | Criar | Garante que o diretório existe no repositório |

---

## Task 1: Infraestrutura de testes + MatchResult

**Files:**
- Modify: `src/models.py`
- Modify: `requirements.txt`
- Create: `tests/__init__.py`
- Create: `data/.gitkeep`

- [ ] **Step 1: Adicionar MatchResult em `src/models.py`**

Adicionar ao final do arquivo (após a classe `GameContext`):

```python
from dataclasses import dataclass


@dataclass
class MatchResult:
    """Resultado da validação de uma aposta após o jogo terminar."""

    home_team: str
    away_team: str
    competition: str
    selection_name: str
    odd: float
    red_cards: int       # -1 se não verificado
    won: bool | None     # None se não verificado
    status: str          # "won" | "lost" | "unverified"
```

- [ ] **Step 2: Adicionar pytest ao `requirements.txt`**

Adicionar ao final do arquivo:

```
# --- Testes ---
pytest>=8.0.0
pytest-asyncio>=0.24.0
```

- [ ] **Step 3: Criar `tests/__init__.py` e `data/.gitkeep`**

```bash
mkdir -p tests data
touch tests/__init__.py data/.gitkeep
```

- [ ] **Step 4: Instalar dependências**

```bash
pip install pytest pytest-asyncio
```

Expected: instalação sem erros.

- [ ] **Step 5: Commit**

```bash
git add src/models.py requirements.txt tests/__init__.py data/.gitkeep
git commit -m "feat: add MatchResult model and test infrastructure"
```

---

## Task 2: `src/opportunity_log.py` (TDD)

**Files:**
- Create: `tests/test_opportunity_log.py`
- Create: `src/opportunity_log.py`

- [ ] **Step 1: Escrever testes em `tests/test_opportunity_log.py`**

```python
"""Testes de opportunity_log — leitura e escrita do JSON diário."""

import json
from datetime import date
from pathlib import Path

import pytest

from src.models import Opportunity
from src import opportunity_log


@pytest.fixture(autouse=True)
def tmp_data_dir(tmp_path, monkeypatch):
    """Redireciona DATA_DIR para diretório temporário em cada teste."""
    monkeypatch.setattr(opportunity_log, "DATA_DIR", tmp_path)
    return tmp_path


def _make_opp(**kwargs) -> Opportunity:
    defaults = dict(
        event_id="1",
        home_team="Flamengo",
        away_team="Corinthians",
        odd=1.85,
        market_name="Total de cartões vermelhos",
        selection_name="Menos de 0.5",
        url="https://betano.bet.br/jogo/1/",
        competition="Brasileirão",
        minute=30,
        score="1 x 0",
    )
    defaults.update(kwargs)
    return Opportunity(**defaults)


def test_append_creates_file(tmp_path):
    opp = _make_opp()
    opportunity_log.append(opp)
    today = date.today().isoformat()
    path = tmp_path / f"opportunities_{today}.json"
    assert path.exists()


def test_append_stores_fields(tmp_path):
    opp = _make_opp(home_team="Santos", away_team="Palmeiras", odd=2.10)
    opportunity_log.append(opp)
    today = date.today().isoformat()
    path = tmp_path / f"opportunities_{today}.json"
    data = json.loads(path.read_text())
    assert len(data) == 1
    entry = data[0]
    assert entry["home_team"] == "Santos"
    assert entry["away_team"] == "Palmeiras"
    assert entry["odd"] == 2.10
    assert "alerted_at" in entry


def test_append_multiple_opps(tmp_path):
    opportunity_log.append(_make_opp(event_id="1"))
    opportunity_log.append(_make_opp(event_id="2"))
    today = date.today().isoformat()
    data = json.loads((tmp_path / f"opportunities_{today}.json").read_text())
    assert len(data) == 2


def test_load_today_empty_when_no_file():
    assert opportunity_log.load_today() == []


def test_load_today_returns_entries(tmp_path):
    opportunity_log.append(_make_opp())
    entries = opportunity_log.load_today()
    assert len(entries) == 1
    assert entries[0]["home_team"] == "Flamengo"


def test_delete_today_removes_file(tmp_path):
    opportunity_log.append(_make_opp())
    opportunity_log.delete_today()
    today = date.today().isoformat()
    assert not (tmp_path / f"opportunities_{today}.json").exists()


def test_delete_today_no_error_if_no_file():
    # Não deve lançar exceção se o arquivo não existir
    opportunity_log.delete_today()
```

- [ ] **Step 2: Rodar testes para confirmar falha**

```bash
pytest tests/test_opportunity_log.py -v
```

Expected: `ModuleNotFoundError` ou `ImportError` — `opportunity_log` não existe ainda.

- [ ] **Step 3: Implementar `src/opportunity_log.py`**

```python
"""Persiste oportunidades alertadas no dia em JSON local."""

import json
from datetime import date, datetime
from pathlib import Path

from src.models import Opportunity

DATA_DIR = Path("data")


def _today_path() -> Path:
    return DATA_DIR / f"opportunities_{date.today().isoformat()}.json"


def append(opp: Opportunity) -> None:
    """Adiciona oportunidade ao JSON do dia (cria arquivo se não existir)."""
    DATA_DIR.mkdir(exist_ok=True)
    path = _today_path()
    entries: list[dict] = []
    if path.exists():
        entries = json.loads(path.read_text(encoding="utf-8"))
    entries.append({
        "event_id": opp.event_id,
        "home_team": opp.home_team,
        "away_team": opp.away_team,
        "competition": opp.competition,
        "minute": opp.minute,
        "score": opp.score,
        "odd": opp.odd,
        "selection_name": opp.selection_name,
        "url": opp.url,
        "alerted_at": datetime.now().isoformat(timespec="seconds"),
    })
    path.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_today() -> list[dict]:
    """Retorna as entradas do JSON do dia. Lista vazia se arquivo não existir."""
    path = _today_path()
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def delete_today() -> None:
    """Apaga o JSON do dia. Silencioso se o arquivo não existir."""
    path = _today_path()
    if path.exists():
        path.unlink()
```

- [ ] **Step 4: Rodar testes para confirmar aprovação**

```bash
pytest tests/test_opportunity_log.py -v
```

Expected: todos os testes PASS.

- [ ] **Step 5: Commit**

```bash
git add src/opportunity_log.py tests/test_opportunity_log.py
git commit -m "feat: implement opportunity_log with daily JSON persistence"
```

---

## Task 3: `src/sofascore.py` — busca de evento (TDD)

**Files:**
- Create: `tests/test_sofascore.py`
- Create: `src/sofascore.py`

- [ ] **Step 1: Escrever testes de busca de evento em `tests/test_sofascore.py`**

```python
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


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_response(json_data: dict, status_code: int = 200):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data
    mock.raise_for_status = MagicMock()
    return mock


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
        # "Fla" deve encontrar "Flamengo" e "Corint" deve encontrar "Corinthians"
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
```

- [ ] **Step 2: Rodar testes para confirmar falha**

```bash
pytest tests/test_sofascore.py -v
```

Expected: `ModuleNotFoundError` — `sofascore` não existe ainda.

- [ ] **Step 3: Implementar `src/sofascore.py` com `find_event` e `get_red_cards`**

```python
"""Scraping da API não oficial do SofaScore para validação de resultados."""

from __future__ import annotations

import difflib
from datetime import date as _date

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
_MATCH_THRESHOLD = 0.5   # ratio mínimo de similaridade de nome


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
    """Busca o evento no SofaScore pelo nome dos times (matching fuzzy).

    Retorna o evento completo ou None se não encontrado.
    """
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
```

- [ ] **Step 4: Rodar testes para confirmar aprovação**

```bash
pytest tests/test_sofascore.py::test_find_event_exact_match tests/test_sofascore.py::test_find_event_fuzzy_match tests/test_sofascore.py::test_find_event_not_found tests/test_sofascore.py::test_get_red_cards_counts_correctly tests/test_sofascore.py::test_get_red_cards_zero_when_none -v
```

Expected: todos PASS.

- [ ] **Step 5: Commit**

```bash
git add src/sofascore.py tests/test_sofascore.py
git commit -m "feat: sofascore scraper — event discovery and red card count"
```

---

## Task 4: `src/sofascore.py` — validação com polling (TDD)

**Files:**
- Modify: `tests/test_sofascore.py`
- Modify: `src/sofascore.py`

- [ ] **Step 1: Adicionar testes de `validate_opportunity` em `tests/test_sofascore.py`**

Acrescentar ao final do arquivo:

```python
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

    # Primeira chamada: em andamento; Segunda: finalizado
    find_side_effects = [in_progress, finished]
    with patch("src.sofascore.find_event", new_callable=AsyncMock, side_effect=find_side_effects), \
         patch("src.sofascore.get_red_cards", new_callable=AsyncMock, return_value=0), \
         patch("asyncio.sleep", new_callable=AsyncMock):
        result = await sofascore.validate_opportunity(ENTRY_UNDER_05, "2026-04-24", poll_interval=0, max_polls=3)
    assert result.status == "won"
```

- [ ] **Step 2: Rodar testes para confirmar falha**

```bash
pytest tests/test_sofascore.py -k "validate_opportunity" -v
```

Expected: `AttributeError` — `validate_opportunity` não existe.

- [ ] **Step 3: Adicionar `validate_opportunity` e `validate_all` em `src/sofascore.py`**

Acrescentar ao final do arquivo (após `get_red_cards`):

```python
import asyncio
from datetime import date as _date

from src.models import MatchResult

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
```

**Atenção:** o import de `asyncio` e `MatchResult` deve ir no topo do arquivo, antes de `_BASE`. Reorganize os imports em `src/sofascore.py`:

```python
from __future__ import annotations

import asyncio
import difflib
from datetime import date as _date

import httpx

from src.models import MatchResult
```

- [ ] **Step 4: Rodar todos os testes do sofascore**

```bash
pytest tests/test_sofascore.py -v
```

Expected: todos PASS.

- [ ] **Step 5: Commit**

```bash
git add src/sofascore.py tests/test_sofascore.py
git commit -m "feat: sofascore validate_opportunity with polling and validate_all"
```

---

## Task 5: `send_daily_report()` em `telegram_notifier.py` (TDD)

**Files:**
- Create: `tests/test_daily_report.py`
- Modify: `src/telegram_notifier.py`

- [ ] **Step 1: Escrever testes em `tests/test_daily_report.py`**

```python
"""Testes do relatório diário no Telegram."""

from unittest.mock import patch

import pytest

from src.models import MatchResult
from src import telegram_notifier as telegram


def _result(status: str, red_cards: int = 0, won: bool | None = None) -> MatchResult:
    return MatchResult(
        home_team="Time A",
        away_team="Time B",
        competition="Liga X",
        selection_name="Menos de 0.5",
        odd=1.85,
        red_cards=red_cards,
        won=won,
        status=status,
    )


def test_send_daily_report_calls_post():
    results = [
        _result("won", red_cards=0, won=True),
        _result("lost", red_cards=1, won=False),
        _result("unverified", red_cards=-1, won=None),
    ]
    with patch("src.telegram_notifier._post", return_value=True) as mock_post:
        telegram.send_daily_report(results, report_date="24/04/2026")
    mock_post.assert_called_once()
    text = mock_post.call_args[0][0]
    assert "RELATÓRIO DIÁRIO" in text
    assert "24/04/2026" in text
    assert "✅" in text
    assert "❌" in text
    assert "⏳" in text
    assert "Taxa de acerto" in text


def test_send_daily_report_accuracy_excludes_unverified():
    results = [
        _result("won", red_cards=0, won=True),
        _result("won", red_cards=0, won=True),
        _result("lost", red_cards=1, won=False),
        _result("unverified", red_cards=-1, won=None),
    ]
    with patch("src.telegram_notifier._post", return_value=True) as mock_post:
        telegram.send_daily_report(results, report_date="24/04/2026")
    text = mock_post.call_args[0][0]
    # 2 de 3 verificados
    assert "67%" in text or "2/3" in text


def test_send_daily_report_all_unverified_no_accuracy_line():
    results = [_result("unverified", red_cards=-1, won=None)]
    with patch("src.telegram_notifier._post", return_value=True) as mock_post:
        telegram.send_daily_report(results, report_date="24/04/2026")
    text = mock_post.call_args[0][0]
    assert "Taxa de acerto" not in text
```

- [ ] **Step 2: Rodar testes para confirmar falha**

```bash
pytest tests/test_daily_report.py -v
```

Expected: `AttributeError` — `send_daily_report` não existe.

- [ ] **Step 3: Adicionar `send_daily_report()` em `src/telegram_notifier.py`**

Adicionar ao final do arquivo (após `send_opportunity_alert`):

```python
from datetime import date as _date
from src.models import MatchResult


def send_daily_report(results: list[MatchResult], report_date: str | None = None) -> bool:
    if report_date is None:
        report_date = _date.today().strftime("%d/%m/%Y")

    won = [r for r in results if r.status == "won"]
    lost = [r for r in results if r.status == "lost"]
    unverified = [r for r in results if r.status == "unverified"]
    verified = won + lost

    lines = [
        f"📋 <b>RELATÓRIO DIÁRIO — {report_date}</b>\n",
        f"Total de alertas: {len(results)}",
        f"✅ Vencedores: {len(won)}",
        f"❌ Perdedores: {len(lost)}",
        f"⏳ Não verificados: {len(unverified)}",
        "\n─────────────────────────",
    ]

    for r in results:
        if r.status == "won":
            icon = "✅"
            detail = f"{r.red_cards} cartão(ões) vermelho(s)"
        elif r.status == "lost":
            icon = "❌"
            detail = f"{r.red_cards} cartão(ões) vermelho(s)"
        else:
            icon = "⏳"
            detail = "Não verificado — timeout SofaScore"

        lines.append(
            f"{icon} <b>{r.home_team} x {r.away_team}</b>\n"
            f"   {r.selection_name} @ {r.odd:.2f} | {detail}"
        )

    lines.append("─────────────────────────")

    if verified:
        pct = int(len(won) / len(verified) * 100)
        lines.append(f"Taxa de acerto: {pct}% ({len(won)}/{len(verified)} verificados)")

    return _post("\n".join(lines))
```

- [ ] **Step 4: Rodar testes**

```bash
pytest tests/test_daily_report.py -v
```

Expected: todos PASS.

- [ ] **Step 5: Rodar suite completa para checar regressões**

```bash
pytest -v
```

Expected: todos PASS.

- [ ] **Step 6: Commit**

```bash
git add src/telegram_notifier.py tests/test_daily_report.py
git commit -m "feat: add send_daily_report to telegram_notifier"
```

---

## Task 6: Integrar `daily_reporter` em `main.py`

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Adicionar imports no topo de `main.py`**

Após os imports existentes, adicionar:

```python
from datetime import datetime as _dt
from src import opportunity_log
from src.sofascore import validate_all
```

- [ ] **Step 2: Adicionar `_sleep_until` e `daily_reporter` antes da função `run()`**

Inserir antes de `async def run():`:

```python
async def _sleep_until(hour: int, minute: int) -> None:
    """Dorme até o próximo HH:MM do dia (ou do dia seguinte se já passou)."""
    now = _dt.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        # Já passou das 23:45 hoje — aguardar até amanhã
        from datetime import timedelta
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
        # Aguarda 60s para não disparar duas vezes no mesmo minuto
        await asyncio.sleep(60)
```

- [ ] **Step 3: Criar a task no início de `run()` e adicionar `opportunity_log.append()` no loop**

Dentro de `async def run()`, logo após `scanner = Scanner(browser)`:

```python
    # Task paralela de relatório diário
    asyncio.create_task(daily_reporter())
```

No bloco `for opp in new_opps:`, após `telegram.send_opportunity_alert(opp)`:

```python
                opportunity_log.append(opp)
```

O bloco final deve ficar:

```python
            for opp in new_opps:
                print(f"  >> {opp.label} | {opp.selection_name} | Odd: {opp.odd:.2f}")
                sent = telegram.send_opportunity_alert(opp)
                print(f"  [Telegram] {'OK' if sent else 'FALHOU'}")
                opportunity_log.append(opp)
                alerted_events.add(f"{opp.event_id}:{opp.selection_name}")
```

- [ ] **Step 4: Verificar que o arquivo importa sem erros**

```bash
python -c "import main; print('OK')"
```

Expected: `OK` sem erros.

- [ ] **Step 5: Commit**

```bash
git add main.py
git commit -m "feat: integrate daily_reporter async task into main loop"
```

---

## Task 7: Volume Docker + configuração final

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Adicionar volume `data/` ao `docker-compose.yml`**

Adicionar `volumes` ao serviço `bot`:

```yaml
services:
  bot:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: bot_red_card
    restart: unless-stopped
    command: /bin/bash -c "xvfb-run --auto-servernum --server-args='-screen 0 1280x720x16' python main.py 2>&1"
    env_file:
      - .env
    environment:
      - TZ=America/Sao_Paulo
      - PYTHONUNBUFFERED=1
    volumes:
      - ./data:/app/data
    shm_size: "256m"
    deploy:
      resources:
        limits:
          memory: 1536m
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

- [ ] **Step 2: Rodar suite de testes completa**

```bash
pytest -v
```

Expected: todos PASS.

- [ ] **Step 3: Commit final**

```bash
git add docker-compose.yml
git commit -m "feat: mount data volume in docker-compose for JSON persistence"
```

---

## Self-Review

**Cobertura da spec:**

| Requisito | Task |
|---|---|
| Salvar oportunidade em JSON ao alertar | Task 2 + Task 6 |
| JSON por data, deletar após relatório | Task 2 |
| Scraping SofaScore para resultados | Task 3 + Task 4 |
| Polling para jogos em andamento (5min, 90min max) | Task 4 |
| Timeout → "não verificado" | Task 4 |
| Under 0.5: ganhou se 0 cartões vermelhos | Task 4 |
| Under 1.5: ganhou se ≤ 1 cartão vermelho | Task 4 |
| Relatório Telegram com resumo + lista + taxa | Task 5 |
| Sem alertas no dia → não envia nada | Task 5 (not tested explicitly — add note) |
| Task asyncio paralela, não bloqueia loop | Task 6 |
| `_sleep_until` funciona para qualquer horário de start | Task 6 |
| Volume Docker para persistir entre restarts | Task 7 |

**Sem alertas no dia — confirmação:** a função `daily_reporter` chama `send_daily_report` apenas dentro do `if entries:`, então se não houver entradas, nenhuma mensagem é enviada. Correto.

**Tipos consistentes:** `MatchResult` definido em Task 1 (`models.py`), usado em Task 4 (`sofascore.py`) e Task 5 (`telegram_notifier.py`) — todos importam de `src.models`. Consistente.

**Polling paralelo:** `validate_all` usa `asyncio.gather`, então jogos em andamento são monitorados em paralelo, não sequencialmente. O relatório sai quando **todos** terminam ou atingem timeout.
