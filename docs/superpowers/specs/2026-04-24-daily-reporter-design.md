# Design: Relatório Diário de Validação de Apostas

**Data:** 2026-04-24  
**Status:** Aprovado

## Objetivo

Ao final de cada dia (23:45), o bot valida automaticamente se as apostas Under Cartão Vermelho alertadas no grupo se concretizaram ou não, enviando um relatório consolidado no Telegram e apagando o registro do dia.

---

## Arquitetura

Três novos componentes se integram ao bot existente sem alterar o loop principal:

```
main.py
  ├── loop principal (sem mudanças, exceto opportunity_log.append())
  └── daily_reporter task (nova asyncio.Task)
        ├── dorme até 23:45
        ├── para cada oportunidade do JSON:
        │     └── polling SofaScore até jogo terminar → verifica cartões
        ├── envia relatório no Telegram (apenas se houver alertas)
        └── apaga o JSON e reprograma para 23:45 do dia seguinte

src/opportunity_log.py   ← novo
src/sofascore.py         ← novo
src/telegram_notifier.py ← existente, adicionar send_daily_report()
```

---

## Componentes

### 1. `src/opportunity_log.py`

Gerencia o arquivo JSON de oportunidades do dia.

**Arquivo:** `data/opportunities_YYYY-MM-DD.json`  
**Formato:**
```json
[
  {
    "event_id": "12345",
    "home_team": "Flamengo",
    "away_team": "Corinthians",
    "competition": "Brasileirão",
    "minute": 23,
    "score": "1 x 0",
    "odd": 1.85,
    "selection_name": "Menos de 0.5",
    "url": "https://www.betano.bet.br/...",
    "alerted_at": "2026-04-24T14:32:10"
  }
]
```

**Funções:**
- `append(opp: Opportunity) -> None` — adiciona entrada ao JSON do dia (cria se não existir)
- `load_today() -> list[dict]` — lê o JSON do dia atual
- `delete_today() -> None` — apaga o arquivo após envio do relatório

O diretório `data/` deve ser mapeado como volume no Docker para sobreviver a restarts.

---

### 2. `src/sofascore.py`

Scraping da API JSON não oficial do SofaScore via `httpx`. Não requer Playwright.

**Endpoints usados:**
- Busca de eventos do dia: `https://api.sofascore.com/api/v1/sport/football/scheduled-events/YYYY-MM-DD`
- Estatísticas do evento: `https://api.sofascore.com/api/v1/event/{event_id}/statistics`

**Fluxo de validação por jogo:**

1. Buscar eventos do dia no SofaScore
2. Fazer match do jogo por `home_team` + `away_team` usando `difflib.SequenceMatcher` (tolerância a abreviações)
3. Verificar `status.type`:
   - `"finished"` → buscar estatísticas e contar cartões vermelhos
   - `"inprogress"` → aguardar 5 minutos e tentar novamente
4. Determinar resultado:
   - Under 0.5 → ganhou se total de cartões vermelhos == 0
   - Under 1.5 → ganhou se total de cartões vermelhos <= 1

**Polling para jogos em andamento:**
- Intervalo: 5 minutos entre tentativas
- Timeout máximo: 90 minutos
- Se expirar: marca como `"não verificado — timeout"`

**Resultado retornado por jogo:**
```python
@dataclass
class MatchResult:
    home_team: str
    away_team: str
    selection_name: str
    odd: float
    red_cards: int          # -1 se não verificado
    won: bool | None        # None se não verificado
    status: str             # "won" | "lost" | "unverified"
```

---

### 3. `daily_reporter` task em `main.py`

Task asyncio criada uma única vez no início do `run()`, que roda em loop eterno paralelo ao loop principal.

```python
async def daily_reporter():
    while True:
        await _sleep_until(23, 45)
        entries = opportunity_log.load_today()
        if entries:
            results = await _validate_all(entries)   # polling SofaScore
            telegram.send_daily_report(results)
        opportunity_log.delete_today()
        await asyncio.sleep(60)  # evita disparar duas vezes no mesmo minuto
```

**`_sleep_until(hour, minute)`:** calcula os segundos até o próximo 23:45 com base no horário atual. Funciona corretamente para qualquer horário de início do container.

**Integração no loop principal** — única mudança no `while True` existente:
```python
for opp in new_opps:
    telegram.send_opportunity_alert(opp)
    opportunity_log.append(opp)   # ← linha adicionada
    alerted_events.add(...)
```

---

### 4. `send_daily_report()` em `telegram_notifier.py`

Formato da mensagem:
```
📋 RELATÓRIO DIÁRIO — 24/04/2026

Total de alertas: 5
✅ Vencedores: 3
❌ Perdedores: 1
⏳ Não verificados: 1

─────────────────────────
✅ Flamengo x Corinthians
   Under 0.5 @ 1.85 | 0 cartões vermelhos

❌ Manchester City x Arsenal
   Under 0.5 @ 1.72 | 2 cartões vermelhos

⏳ Santos x Palmeiras
   Não verificado — timeout SofaScore
─────────────────────────
Taxa de acerto: 75% (3/4 verificados)
```

Se não houver alertas no dia: **não envia nada** e não apaga o arquivo (que não existe).

---

## Docker

Adicionar volume ao `docker-compose.yml` para persistir o JSON entre restarts:

```yaml
volumes:
  - ./data:/app/data
```

---

## Limitações Conhecidas

- **Primeiro dia após deploy:** oportunidades enviadas antes do restart do container não estarão no JSON. A partir do segundo dia, captura é completa.
- **Match de nomes:** times com nomes muito abreviados ou em idiomas diferentes podem não ser encontrados no SofaScore. Nesses casos, o jogo é marcado como `"não verificado"`.
- **SofaScore:** API não oficial, sem garantia de estabilidade. Se a API mudar, o scraper precisa de atualização.
