# Bot Red Card v2 — Arquitetura Técnica

## Visão Geral

Bot de monitoramento em tempo real de odds **Under 0.5 Cartão Vermelho** na Betano.
Arquitetura **híbrida** que combina duas ferramentas distintas para contornar camadas
diferentes de proteção WAF/Cloudflare:

| Fase | Ferramenta | Alvo | Proteção contornada |
|------|-----------|------|---------------------|
| **Descoberta** | curl_cffi | API REST `/live/overview` | TLS Fingerprinting |
| **Scanning** | Playwright + Stealth + XVFB | Páginas de jogo (SPA) | Bot Detection + Canvas Fingerprint |

---

## Diagrama de Fluxo

```
                         ┌──────────────────────────┐
                         │       main.py            │
                         │     (Orquestrador)        │
                         └────────┬─────────────────┘
                                  │
                 ┌────────────────┴────────────────┐
                 │                                  │
      ┌──────────▼──────────┐           ┌──────────▼──────────┐
      │   FASE 1: curl_cffi │           │  FASE 2: Playwright │
      │   (Descoberta)      │           │  (Scanning)         │
      └──────────┬──────────┘           └──────────┬──────────┘
                 │                                  │
      GET /live/overview                  Para cada GameContext:
      impersonate=chrome120               │
                 │                        ├─ 1. Abrir página do jogo
      Retorna JSON com                    ├─ 2. Interceptar respostas JSON
      todos os eventos                    ├─ 3. Clicar aba "Cartões"
      ao vivo                             ├─ 4. Capturar mercados (lazy-load)
                 │                        └─ 5. Buscar Under 0.5
      Extrai lista de                              │
      GameContext[]                        Retorna Opportunity[]
                 │                                  │
                 └────────────────┬────────────────┘
                                  │
                       ┌──────────▼──────────┐
                       │  Telegram Notifier  │
                       │  (httpx → Bot API)  │
                       └─────────────────────┘
```

---

## Fase 1: Descoberta de Jogos (curl_cffi)

### O Problema

A Betano usa **Cloudflare** na frente da API REST. O Cloudflare analisa o **TLS handshake**
(cipher suites, extensões, order of extensions) para detectar se o client é um browser real
ou uma biblioteca HTTP como `requests`/`httpx`. Bibliotecas Python têm um fingerprint TLS
completamente diferente de um Chrome real, resultando em **403 Forbidden**.

### A Solução

O `curl_cffi` resolve isso falsificando o TLS handshake no nível da libcurl. Com
`impersonate="chrome120"`, ele reproduz exatamente o mesmo TLS fingerprint de um
Chrome 120 real:

```python
response = curl_requests.get(
    settings.overview_url,
    headers={"Accept": "application/json"},
    impersonate="chrome120",
    timeout=30,
)
```

O Cloudflare vê um handshake idêntico ao de um browser legítimo e permite o acesso.
Isso é rápido (~200ms), confiável, e não precisa de browser.

### Por que não usar o Playwright aqui?

Tentamos 3 abordagens antes de voltar ao curl_cffi:

1. **`page.goto(api_url)`** — O browser envia `Sec-Fetch-Dest: document` (navegação direta),
   que o WAF identifica como anômalo para um endpoint JSON. Resultado: **403**.

2. **`page.evaluate("fetch(url)")`** — O frontend da Betano injeta tokens de telemetria
   gerados em runtime nos headers das requisições XHR. Nosso `fetch()` manual não tem
   esses tokens. Resultado: **403**.

3. **Interceptação passiva (SSR)** — A página `/live/` usa Server-Side Rendering; os dados
   vêm embutidos no HTML, não como XHR separado. `page.expect_response()` dá timeout
   porque o request nunca acontece na rede.

O curl_cffi funciona porque ataca a camada de TLS, não a camada de aplicação. A API REST
da Betano é pública e não requer tokens de sessão — só precisa passar pelo Cloudflare.

### Dados Extraídos

Da resposta JSON, extraímos para cada evento:

| Campo | Fonte | Uso |
|-------|-------|-----|
| `id` | chave do objeto `events` | Identificador único |
| `home` / `away` | `participants[0].name` / `participants[1].name` | Nomes dos times |
| `minute` | `liveData.clock.secondsSinceStart / 60` | Filtro por minuto mínimo |
| `total_markets` | `totalMarketsAvailable` | Priorização (mais mercados = maior chance de ter cartões) |
| `competition` | `league.name` ou `tournament.name` | Exibição no alerta |
| `score` | `liveData.score.home` x `liveData.score.away` | Exibição no alerta |
| `url` | `event.url` | Navegação na Fase 2 |

**Filtros aplicados:**
- Apenas futebol (`sportId == "FOOT"`)
- Exclui eSports
- Minuto >= configurável (default: 5')
- Ordenado por `total_markets` decrescente

---

## Fase 2: Scanning de Mercados (Playwright)

### O Problema

Os mercados de cartão vermelho não estão na API REST pública. Eles são carregados
dinamicamente pela SPA (Single Page Application) da Betano quando o usuário clica na
aba **"Cartões"** dentro da página de um jogo. É um **lazy-loading** — os dados só
trafegam na rede após a interação do usuário.

Além disso, a Betano implementa detecção de bots nas páginas de jogo:
- Verificação de `navigator.webdriver`
- Canvas fingerprinting
- Análise de plugins do navegador
- Splash screens de verificação

### A Solução: BrowserEngine (3 camadas de evasão)

#### Camada 1: Playwright Stealth

A biblioteca `playwright-stealth` aplica patches JavaScript que:

- Remove a flag `navigator.webdriver` (principal sinal de automação)
- Falsifica o objeto `chrome` e suas propriedades
- Simula plugins reais (`Chrome PDF Viewer`, etc.)
- Patcha `navigator.permissions` para retornar valores consistentes

```python
stealth = Stealth()
await stealth.apply_stealth_async(page)
```

#### Camada 2: Rotação de Identidade

A cada inicialização do browser, são sorteados aleatoriamente:

**User-Agent** (6 variantes):
- Chrome 122–131 em Windows 10/11 e macOS Sonoma/Ventura
- Versões recentes e populares para não levantar suspeita

**Viewport** (4 resoluções):
- 1920x1080, 1536x864, 1440x900, 1366x768
- Resoluções reais de monitores comuns

**Headers extras** consistentes com o UA:
- `Accept-Language: pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7`
- `Sec-CH-UA-Platform` dinâmico (`"Windows"` ou `"macOS"` conforme o UA)

#### Camada 3: XVFB (Display Virtual)

O Chromium roda com `headless=False` — como um browser real com janela visível.
Isso é crítico porque:

- `headless=True` tem diferenças detectáveis no objeto `navigator`, no rendering pipeline,
  e em propriedades CSS como `@media (hover)`
- Sites como a Betano conseguem distinguir headless de headed mesmo com stealth patches

No Docker, não existe tela física. O **XVFB** (X Virtual Framebuffer) cria um display
X11 virtual em memória:

```bash
xvfb-run --auto-servernum --server-args='-screen 0 1920x1080x24' python main.py
```

O Chromium renderiza numa "tela" de 1920x1080 com 24-bit de cor que existe apenas
em memória. Para o site, é indistinguível de um browser real rodando num desktop.

### Sessão Quente (Warm Session)

A estratégia mais importante de evasão. Em vez de navegar diretamente para o jogo
(comportamento de bot), simulamos o padrão de um usuário real:

```
1. Abrir betano.bet.br (home page)
2. Aceitar modal de idade/cookies
3. Aguardar 4s (SPA carrega, scripts de telemetria rodam)
4. Cookies de sessão são instalados (~51 cookies)
5. Agora navegar para os jogos usando o MESMO contexto
```

Todas as navegações subsequentes herdam os cookies e o estado da sessão.
O WAF vê um usuário que chegou pela home e está navegando internamente —
não um bot que apareceu direto na URL de um jogo.

### Interceptação de Mercados (Lazy-Loading)

O scanning de cada jogo segue este fluxo:

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Abrir nova aba no contexto quente                        │
│    └─ Cookies/sessão herdados da warm session              │
│                                                             │
│ 2. Instalar interceptor: page.on("response", callback)     │
│    └─ Captura toda resposta JSON com "markets"/"selections"│
│                                                             │
│ 3. Navegar para a página do jogo                           │
│    └─ Verificar splash screen (body < 50 chars?)           │
│    └─ Se bloqueado → reload + retry                        │
│                                                             │
│ 4. Esperar abas da SPA renderizarem (wait_for_selector)    │
│    └─ Seletor: span.GTM-tab-name (até 15s)               │
│    └─ Se timeout → reload + retry                          │
│                                                             │
│ 5. Clicar na aba "Cartões"                                 │
│    └─ Fallback: 3 seletores CSS diferentes                 │
│    └─ Se não encontrar → jogo sem mercado de cartão → skip│
│                                                             │
│ 6. Aguardar 3s (lazy-loading)                              │
│    └─ O clique na aba dispara XHR para a API de mercados  │
│    └─ O interceptor captura o JSON automaticamente         │
│                                                             │
│ 7. Varrer mercados capturados                              │
│    └─ Filtrar por nome: "cartão vermelho", "expulsão"...  │
│    └─ Buscar seleção Under: "não", "under 0.5"...         │
│    └─ Verificar odd >= threshold                           │
│    └─ Retornar Opportunity se encontrar                    │
│                                                             │
│ 8. Fechar aba                                              │
└─────────────────────────────────────────────────────────────┘
```

**Por que interceptar JSON em vez de parsear o DOM?**

- O DOM da Betano é gerado por React com classes CSS ofuscadas (hashes aleatórios)
- Os seletores CSS mudam a cada deploy
- O JSON da API tem estrutura estável: `{ markets: {...}, selections: {...} }`
- Interceptar é mais rápido, mais confiável e mais resistente a mudanças de layout

### Termos de Mercado

Herdados da análise do scanner original e mantidos para compatibilidade:

**Mercados válidos** (match por substring, case-insensitive):
```
"total de cartões vermelhos", "total de cartoes vermelhos"
"cartão vermelho", "cartao vermelho"
"cartões vermelhos", "cartoes vermelhos"
"expulsão", "expulsao"
```

**Seleções Under** (match exato):
```
"não", "nao", "menos de 0.5", "under 0.5"
```

Variantes sem acento são necessárias porque a API da Betano às vezes retorna
nomes sem acentuação.

---

## Resiliência e Ciclo de Vida

### Loop Principal

```
while True:
    1. curl_cffi → busca jogos ao vivo (síncrono, ~200ms)
    2. Scanner → escaneia jogos sequencialmente (3s delay entre cada)
    3. Filtra oportunidades já alertadas (evita duplicatas)
    4. Envia alertas novos via Telegram
    5. Cooldown (default: 120s)
```

### Reciclagem do Browser

A cada N ciclos (default: 10), o browser é completamente destruído e recriado:

- Novo User-Agent sorteado
- Novo viewport sorteado
- Nova sessão quente (novos cookies)
- Previne: memory leaks, sessão expirada, profiling por tempo de sessão

### Tratamento de Falhas

| Cenário | Ação |
|---------|------|
| Splash screen detectada | Reload automático + retry |
| Abas da SPA não carregaram | Reload + retry com timeout |
| Aba "Cartões" não existe | Skip (log INFO, não é erro) |
| Timeout no scan de um jogo (>45s) | Skip, continua para o próximo |
| Todos os jogos falharam no ciclo | Browser recycle forçado |
| Browser crashou | `ensure_alive()` detecta e recicla |

### Docker

O container é construído com tudo necessário para simular um desktop real:

```
python:3.11-slim-bookworm
├── Chromium (via playwright install)
├── XVFB + xauth (display virtual)
├── Fontes reais (Liberation, Noto, Emoji)
│   └── Evita canvas fingerprint vazio
├── Libs gráficas (cairo, pango, jpeg, png, webp)
│   └── Renderização completa de assets
├── Locale pt-BR.UTF-8
│   └── Consistência com o site alvo
├── curl + libcurl + openssl + build-essential
│   └── Build deps para curl_cffi
└── Roda como usuário não-root (botuser)
```

**Recursos alocados:**
- `shm_size: 512m` — memória compartilhada para o Chromium (sem isso, crash em páginas pesadas)
- `memory: 2g` — limite de RAM do container
- Logs com rotação (10MB x 3 arquivos)
- `restart: unless-stopped` — auto-restart em caso de crash

---

## Stack de Dependências

| Pacote | Versão | Justificativa |
|--------|--------|---------------|
| `playwright` | >=1.49 | Automação de browser. Escolhido sobre Selenium por ser mais moderno, mais rápido, e ter API async nativa |
| `playwright-stealth` | >=1.0.6 | Patches anti-detecção. Equivalente ao `puppeteer-extra-plugin-stealth` do ecossistema Node |
| `curl_cffi` | >=0.6 | TLS fingerprint bypass. Única lib Python capaz de falsificar o handshake TLS de forma convincente |
| `pydantic` | >=2.10 | Modelos tipados com validação. Previne dados inválidos fluindo pelo pipeline |
| `pydantic-settings` | >=2.7 | Config via `.env` com tipagem e validação automática |
| `httpx` | >=0.28 | HTTP client moderno para Telegram. Mais leve que `requests`, suporta async |
| `python-dotenv` | >=1.0 | Carregamento de `.env` (dependência do pydantic-settings) |

### Por que não Selenium?

- Playwright tem API async nativa (essencial para o loop de eventos)
- Melhor performance (protocolo CDP direto, sem WebDriver intermediário)
- `playwright-stealth` é mais maduro que equivalentes Selenium
- Instalação de browsers integrada (`playwright install chromium`)

### Por que não requests/httpx para a API?

- Ambos têm TLS fingerprint de Python puro
- Cloudflare detecta e bloqueia com 403
- `curl_cffi` é a única opção que falsifica TLS no nível C

---

## Configuração (.env)

```env
# Scanner
COOLDOWN_SECONDS=120       # Intervalo entre ciclos
MIN_ODD_THRESHOLD=1.5      # Odd mínima para alertar
MIN_MATCH_MINUTE=10        # Ignorar jogos nos primeiros X minutos
MAX_EVENTS_PER_CYCLE=30    # Máximo de jogos escaneados por ciclo
DELAY_BETWEEN_EVENTS=3     # Delay entre scans (anti-rate-limit)
RECYCLE_EVERY_N_CYCLES=10  # Frequência de reciclagem do browser
MIN_MARKETS_FOR_CARDS=50   # Mínimo de mercados para tentar scan

# Telegram
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```
