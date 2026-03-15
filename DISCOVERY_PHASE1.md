# FASE 1: Descoberta do Sistema de Mercados Betano

## Resumo

A investigação do WebSocket e APIs do Betano revelou a arquitetura de carregamento de mercados:

## Descobertas Principais

### 1. WebSocket (SignalR)
- **URL**: `wss://www.betano.bet.br/signalr/connect?transport=webSockets&clientProtocol=1.5`
- **Hub**: `sportsbookhub`
- **Métodos descobertos**:
  - `subscribeliveVisualizationsInfo` - Para animações ao vivo (scoreboard)
  - `pushLiveVisualizationsInfo` - Push de dados de visualização
- **Conclusão**: WebSocket é usado APENAS para visualizações ao vivo, NÃO para mercados

### 2. APIs REST

#### Overview API
```
GET /danae-webapi/api/live/overview/latest?queryLanguageId=5&queryOperatorId=8&includeVirtuals=true
```
- Retorna lista de eventos ao vivo
- Cada evento tem `marketIdList` com IDs de mercados disponíveis
- Mercados e seleções em listas separadas no top-level
- Mercados limitados (4-8 por evento na visão geral)

#### Event-Specific API (PRINCIPAL)
```
GET /danae-webapi/api/live/events/{eventId}/latest
```
- Retorna TODOS os mercados de um evento específico
- 20-108+ mercados por evento
- **IMPORTANTE**: Retorna vazio quando chamado diretamente - requer contexto de browser

### 3. Mercados de Cartão
- **Mercados de cartão vermelho NÃO foram encontrados** em eventos ao vivo testados
- Possíveis explicações:
  - Disponíveis apenas em pré-jogo
  - Disponíveis apenas para certas ligas/eventos
  - Removidos durante jogo ao vivo

### 4. Estrutura de Dados

```json
{
  "version": 835,
  "sport": { "id": "FOOT", "name": "Futebol" },
  "zone": { "id": 11429, "name": "Israel" },
  "league": { "id": 17802, "name": "Liga Leumit" },
  "event": {
    "id": 81325220,
    "marketIdList": [2626104986, ...],
    "participants": [
      { "name": "Time A" },
      { "name": "Time B" }
    ]
  },
  "markets": {
    "2626104986": {
      "name": "Resultado Final",
      "selections": [...]
    }
  }
}
```

## Implicações para o Scraper

1. **Para mercados de eventos ao vivo**: Usar Playwright para buscar `/danae-webapi/api/live/events/{eventId}/latest`
2. **WebSocket não é necessário**: Mercados vêm de REST API
3. **Mercados de cartão**: Verificar disponibilidade em eventos pré-jogo
4. **Autenticação**: Endpoint requer contexto de browser (cookies/headers)

## Implementação Realizada

### FASE 2: market_client.py
- Cliente leve que usa Playwright para buscar mercados completos
- Método `get_event_markets(event_id, event_url)` retorna todos os mercados
- Método `find_red_card_market(event_id, event_url)` procura especificamente cartão vermelho

### FASE 3: Integração com scraper.py
- Adicionado `fetch_full_markets_for_match()` - busca mercados via Playwright
- Adicionado `find_red_card_in_full_markets()` - busca cartão vermelho via Playwright
- Método `process_matches()` agora aceita `use_full_markets=True` para busca completa

## Descoberta FASE 6: Lazy-Loading da Aba "Cartões"

### Problema Identificado
O mercado de Cartão Vermelho NÃO estava sendo detectado porque a Betano usa **lazy-loading**.
Os mercados de cartões só são carregados quando o usuário clica na aba "Cartões".

### Solução Implementada
1. **Fechar modal de idade**: Usar JavaScript para remover o modal que bloqueia cliques
2. **Clicar na aba "Cartões"**: Seletor `span.GTM-tab-name:has-text('Cartões')`
3. **Interceptar resposta**: Capturar os novos mercados carregados após o clique

### Eventos com Aba "Cartões"
- Nem todos os jogos têm a aba "Cartões"
- Geralmente disponível em ligas maiores (Premier League, La Liga, Série A, etc.)
- Jogos menores/regionais não têm esta aba

### Resultado Final
✅ **Mercado de Cartão Vermelho detectado com sucesso!**
- Exemplo: AFC Hermannstadt vs FC Botosani
- Mercado: "Total de Cartões Vermelhos"
- Seleção: "Mais de 0.5"
- Odd: 5.00

## Arquivos Criados/Modificados

- `market_client.py` - Cliente Playwright para mercados
- `src/scraper.py` - Atualizado com métodos de busca completa
- `DISCOVERY_PHASE1.md` - Este relatório
