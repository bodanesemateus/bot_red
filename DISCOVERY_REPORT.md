# Relatório de Descoberta - API Betano

## Resumo Executivo

Após extensiva engenharia reversa da plataforma Betano, foram mapeados os endpoints e a arquitetura da API. O mercado de **Cartão Vermelho NÃO está disponível via REST API** - ele é carregado sob demanda via WebSocket quando o usuário expande a tab "Cartões" na página do evento.

## Endpoints Descobertos

### 1. API de Overview (REST)
```
GET https://www.betano.bet.br/danae-webapi/api/live/overview/latest
    ?queryLanguageId=5
    &queryOperatorId=8
    &includeVirtuals=false
```

**Retorna:**
- Lista de eventos ao vivo de todos os esportes
- Apenas 6-8 mercados principais por evento (de 100-200+ disponíveis)
- Estrutura normalizada: `events`, `markets`, `selections`

**Mercados disponíveis:**
- Resultado Final (1X2)
- Próximo Gol
- Total de Gols Mais/Menos
- Escanteios Mais/Menos
- Chance Dupla
- Ambas equipes Marcam
- Empate Anula

### 2. API de Configuração (REST)
```
GET https://br.betano.com/api/live/{slug}/{eventId}/
```

**Retorna:**
- Configuração de tabs de mercados por esporte
- IDs de tipos de mercados (marketTypeIds)
- Configurações de incidentes (RED_CARD, YELLOW_CARD, etc.)

### 3. API de Sincronização (REST - Incremental)
```
POST https://www.betano.bet.br/danae-webapi/api/live/overview/sync
```

**Uso:** Sincronização incremental de dados após carregamento inicial. Não retorna mercados adicionais.

## Mercados de Cartão Vermelho

Os seguintes marketTypeIds foram identificados para mercados de cartões:

| TypeId | Descrição Provável |
|--------|-------------------|
| REDC   | Red Card          |
| ARED   | Away Red Card     |
| HRED   | Home Red Card     |
| 1RED   | 1 Red Card        |
| BTRC   | Both Teams Red Card |
| RCOU   | Red Card Over/Under |

**Localização na UI:**
- Tab "Cartões" (38 mercados)
- Tab "Pro.- Cartões" (7 mercados)

## Arquitetura de Carregamento

```
┌─────────────────────────────────────────────────────────────────┐
│                     Frontend (React)                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. Carrega /live/overview/latest (REST)                        │
│     → Recebe mercados principais (6-8 por evento)               │
│                                                                 │
│  2. Usuário clica em tab "Cartões"                              │
│     → Frontend envia mensagem via WebSocket                     │
│     → Backend retorna mercados da tab                           │
│                                                                 │
│  3. WebSocket mantém atualizações em tempo real                 │
│     → Odds, disponibilidade, status                             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Limitações da API REST

1. **Mercados limitados:** Apenas mercados principais são retornados
2. **Sem filtro funcional:** Parâmetros como `marketTypeId`, `marketGroupId` são ignorados
3. **Sem endpoint de detalhes:** Não existe `/event/{id}/details` ou similar
4. **Mercados especiais via WebSocket:** Cartões, estatísticas, especiais

## Endpoints Testados (404/Não Funcionais)

- `/live/event/{id}`
- `/live/events/{id}/markets`
- `/live/marketGroups/{id}`
- `/live/eventDetails/{id}`
- `/prematch/event/{id}`
- `/sportsbook/event/{id}`
- `/offering/v2018/events/{id}.json`

## Alternativas Possíveis

### 1. Implementar Cliente WebSocket
```python
# Exemplo conceitual
ws = WebSocketClient("wss://betano.bet.br/ws")
ws.subscribe({"eventId": "123", "marketGroups": ["cards"]})
```
**Prós:** Acesso a todos os mercados
**Contras:** Complexidade, autenticação, manutenção

### 2. Usar Mercados Disponíveis
O scraper atual funciona com:
- Escanteios Mais/Menos
- Próximo Gol
- Total de Gols

### 3. Monitorar Pré-jogo
Verificar se há endpoint de pré-jogo com mercado de cartão.

## Configuração Atual do Scraper

```python
# config.py
danae_api_base = "https://www.betano.bet.br/danae-webapi/api"
live_overview_endpoint = "/live/overview/latest"
query_language_id = "5"  # Português BR
query_operator_id = "8"  # Betano BR
football_sport_id = "FOOT"
```

## Conclusão

A arquitetura da Betano prioriza carregamento sob demanda para otimizar performance. O mercado de Cartão Vermelho requer implementação de cliente WebSocket para acesso completo. O scraper atual está funcional para mercados disponíveis via REST.
