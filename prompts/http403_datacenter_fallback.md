# HTTP 403 em Datacenter AWS — Diagnóstico e Solução de Fallback

**Data:** Abril 2026
**Contexto:** Deploy do bot em EC2 t3.small (sa-east-1, ASN AS16509 AMAZON-02)
**Sintoma:** `curl_cffi` retorna HTTP 403 (1277 bytes) na chamada à API REST da Betano
**Solução adotada:** Fallback para `BrowserEngine.fetch_json()` via JS `fetch()` no contexto Playwright

---

## 1. Diagnóstico do Problema

### 1.1 O que mudou ao sair do ambiente local

No ambiente local (macOS, IP residencial), o `curl_cffi` com `impersonate="chrome120"`
funcionava corretamente: retornava HTTP 200 com o JSON de eventos ao vivo.

Após o deploy na AWS (EC2 sa-east-1), o mesmo código passou a retornar HTTP 403
com corpo de 1277 bytes — tamanho típico de uma página de challenge do Cloudflare,
não de um payload de aplicação.

### 1.2 Por que o curl_cffi não é suficiente em datacenter

O `curl_cffi` resolve especificamente o problema de **TLS fingerprinting**: ele
falsifica o TLS Client Hello (cipher suites, extensões, ordem das extensões) para
imitar um Chrome real, o que faz o Cloudflare aceitar conexões de bibliotecas Python
que normalmente seriam rejeitadas.

Porém, o Cloudflare e outros sistemas WAF aplicam **múltiplas camadas de avaliação
de confiança**, e TLS fingerprint é apenas uma delas. A segunda camada é a
**reputação de IP por ASN (Autonomous System Number)**.

O IP de uma instância EC2 vem do ASN **AS16509 (AMAZON-02)**. O Cloudflare mantém
um score de reputação por ASN baseado em histórico de abuso (scraping, DDoS,
credential stuffing). ASNs de grandes cloud providers — AWS, DigitalOcean, GCP,
Azure — têm scores de bot elevados por padrão, porque são onde a esmagadora maioria
de tráfego automatizado malicioso se origina.

O resultado prático: independente de quão perfeito seja o TLS handshake, o IP de
datacenter já começa com uma pontuação de risco alta. Para alguns endpoints/domínios
mais sensíveis, o Cloudflare bloqueia na camada de IP antes mesmo de avaliar o TLS.

```
Fluxo de avaliação Cloudflare (simplificado):

┌─────────────────────────────────────────────────────────────────┐
│  1. IP Reputation (ASN score)          → bloqueio aqui ✗        │
│  2. TLS Fingerprint (JA3/JA4)          → curl_cffi resolve      │
│  3. HTTP/2 Fingerprint (AKAMAI)        → curl_cffi resolve      │
│  4. Browser Challenge (JS execution)   → Playwright resolve     │
│  5. Behavioral Analysis (mouse, timing)│ → Playwright + Stealth  │
└─────────────────────────────────────────────────────────────────┘
```

### 1.3 Evidência nos logs

```
[API] HTTP 403 | 1277 bytes
```

O corpo de 1277 bytes é a página de challenge do Cloudflare (`cf-mitigated: challenge`
no header), não um erro 403 da aplicação Betano. Isso confirma que o bloqueio é na
borda (Cloudflare), não no backend.

### 1.4 Por que o Playwright passa onde o curl_cffi falha

Simultaneamente ao 403 no curl_cffi, o Playwright carregou a home da Betano com sucesso
e instalou 13–28 cookies de sessão. Isso demonstra que o problema não é o IP estar
totalmente banido — é que a Betano/Cloudflare exige um **browser challenge completo**
(execução de JavaScript de verificação) para IPs de datacenter, e o curl_cffi não pode
executar JS.

O Playwright passa pelo challenge porque:

1. Executa o JS de verificação do Cloudflare (Turnstile/Bot Management)
2. Tem um TLS fingerprint de Chromium real (headless=False)
3. O `playwright-stealth` oculta sinais de automação no runtime JS
4. XVFB + headless=False produz um ambiente de rendering indistinguível de um desktop

Uma vez que o Playwright passa no challenge inicial (warm session), os **cookies de
sessão resultantes** são suficientes para autenticar requisições subsequentes no mesmo
domínio — inclusive chamadas `fetch()` feitas via `page.evaluate()`.

---

## 2. A Solução Implementada

### 2.1 Descrição

Foi adicionado o método `BrowserEngine.fetch_json(url)` em `src/browser.py`, e a
função `_fetch_live_events()` em `main.py` foi convertida para `async` com lógica
de fallback em dois estágios:

```
Estágio 1: curl_cffi (rápido, ~200-500ms)
  ├── HTTP 200 → usa o resultado, retorna
  └── HTTP 403/4xx → loga e cai para estágio 2

Estágio 2: BrowserEngine.fetch_json() (lento, ~8-15s)
  ├── Abre nova aba no contexto quente existente
  ├── Navega para a home (estabelece Referer correto)
  ├── Executa fetch() via page.evaluate() com credentials: 'include'
  └── Retorna o JSON parseado ou None se falhar
```

### 2.2 Implementação do `fetch_json`

```python
async def fetch_json(self, url: str) -> Optional[dict]:
    page = await self._context.new_page()
    await self._stealth.apply_stealth_async(page)
    try:
        await page.goto(settings.base_url, wait_until="domcontentloaded", ...)
        result = await page.evaluate(
            """async (url) => {
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
            }""",
            url,
        )
        return result if "__error" not in result else None
    finally:
        await page.close()
```

O ponto crítico é `credentials: 'include'` — isso inclui os cookies de sessão já
instalados pelo warm session na requisição, o que faz o Cloudflare reconhecer a sessão
como legítima.

A navegação prévia para `settings.base_url` garante que:
- O `Referer` header será `https://www.betano.bet.br/` (same-origin, esperado pelo WAF)
- O contexto de segurança do browser está no domínio correto para a CORS policy

### 2.3 Por que isso funciona mas a abordagem anterior (page.evaluate no fetch_api) não funcionava

O histórico do projeto registra uma tentativa anterior de `page.evaluate("fetch(url)")`
que retornava 403. Havia duas diferenças fundamentais:

1. **Contexto da página**: na tentativa anterior, o fetch era executado a partir de
   uma página de jogo específica, sem ter estabelecido previamente o contexto da home.
   Agora, navegamos explicitamente para a home antes do fetch, garantindo o Referer
   e o contexto de cookies correto.

2. **Maturidade da sessão**: a tentativa anterior era feita antes do warm session ter
   completado totalmente. Agora, `fetch_json` só é chamado após `warm_session()` ter
   instalado os cookies de sessão.

---

## 3. Trade-offs e Limitações da Solução

### 3.1 Custo de latência

O fallback para browser é significativamente mais lento que curl_cffi:

| Método | Latência típica | Uso de recursos |
|--------|-----------------|-----------------|
| curl_cffi direto | ~200–500ms | CPU/RAM mínimos |
| BrowserEngine.fetch_json | ~8–15s | Abre aba, carrega página, executa JS |

No ambiente AWS (IP de datacenter), o curl_cffi sempre falhará com 403, então o
custo do fallback é pago em todos os ciclos. Com cooldown de 300s por ciclo, 15s
de latência na busca da API representa ~5% do ciclo — aceitável.

### 3.2 Escalabilidade

A solução atual usa uma única instância do BrowserEngine de forma sequencial. O
`fetch_json` abre e fecha uma aba por chamada. Se o `max_events_per_cycle` crescer
muito, o gargalo já existente no scanning de eventos se tornará mais pronunciado.

### 3.3 Fragilidade ao recycle do browser

O `fetch_json` depende do contexto quente (`self._context`) estar válido. O
`recycle()` destrói e recria o contexto. Se `fetch_json` for chamado imediatamente
após um `recycle()`, haverá uma nova warm session em andamento — o que é correto
pois o `recycle()` chama `warm_session()` antes de retornar.

### 3.4 Sem retry no fallback

Se o `fetch_json` falhar (exceção de rede, timeout, JS error), a função retorna
`[]` e o ciclo é pulado. Não há retry no fallback. Na prática, o browser já tem
resiliência embutida (reload em splash screen, ensure_alive), mas uma falha rara
de rede durante o `page.evaluate` resultará em ciclo perdido.

---

## 4. Alternativas Consideradas

### 4.1 Proxy Residencial

Rotear o tráfego do `curl_cffi` por um proxy residencial (Brightdata, Oxylabs)
resolveria o problema de reputação de IP de forma limpa, sem depender do browser
para a fase de descoberta.

**Prós:** resolve o problema na raiz; curl_cffi volta a funcionar; sem custo de latência
**Contras:** custo adicional (~$10–15/mês para o volume estimado); dependência de
serviço externo; implementação mais complexa (autenticação proxy no curl_cffi)

**Por que não foi adotado agora:** a solução de fallback resolve o problema imediato
sem custo adicional. O proxy residencial seria a solução ideal se o volume de
requisições ou a latência do fallback se tornarem problemáticos.

### 4.2 Mudar para IP residencial (VPS caseiro / Oracle Cloud)

Hospedar em hardware físico com IP residencial, ou no Oracle Cloud Free Tier
(ARM, IPs da Oracle têm reputação ligeiramente melhor que AWS).

**Prós:** curl_cffi funcionaria diretamente; sem custo do fallback
**Contras:** o usuário já tem créditos AWS ($100); migração tem custo de tempo;
Oracle Free Tier tem limite de CPU em instâncias ARM

### 4.3 ElasticIP + rotação de IPs

Associar e desassociar Elastic IPs programaticamente para mudar o IP quando
bloqueado.

**Prós:** resolve bloqueios temporários
**Contras:** IPs Elastic da AWS ainda são do ASN AS16509; não resolve o problema
de reputação de ASN, apenas adia re-bloqueio

### 4.4 AWS NAT Gateway com múltiplos IPs / AWS Global Accelerator

Rotear por múltiplos IPs de saída.

**Contras:** custo significativo (~$30–50/mês); todos os IPs ainda são AS16509

---

## 5. Avaliação da Solução Adotada

### O que foi ganho

- **Funcionalidade restaurada** sem custo adicional
- **Sem mudança na lógica de negócio** — o fallback é transparente para o resto do código
- **Resiliência melhorada**: se no futuro o IP for whitelisted (IPs AWS às vezes
  passam após aquecimento de sessão), o curl_cffi volta a ser usado automaticamente
  sem nenhuma mudança

### O que pode ser melhorado

1. **Eliminar a navegação para home no fetch_json**: após a warm session estar ativa,
   os cookies já estão no contexto. A navegação para home é um overhead. Poderia-se
   reutilizar uma aba persistente já aberta na home para fazer os fetches, reduzindo
   latência de ~8s para ~1-2s.

2. **Proxy residencial como upgrade**: quando o volume ou a SLA exigirem, adicionar
   um proxy residencial como primeira tentativa antes do curl_cffi.

3. **Cache do JSON da API**: o JSON de overview é estável por ~30s. Se houver múltiplos
   scans rápidos, um cache com TTL evitaria chamadas redundantes.

4. **Retry com backoff no fallback**: adicionar 1 retry com 2s de espera no
   `fetch_json` antes de retornar None, para absorver falhas transientes de rede.

---

## 6. Conclusão

A causa raiz é a **reputação negativa do ASN AWS** no sistema de scoring do Cloudflare,
que bloqueia requisições diretas de datacenter independente da qualidade do TLS
fingerprint. O curl_cffi resolve TLS fingerprinting mas não ASN reputation.

A solução de fallback para `BrowserEngine.fetch_json()` é **pragmaticamente correta**:
usa o único caminho que já estava provado funcionar (o browser com warm session) para
a operação que estava falhando. O custo é latência adicional por ciclo, que é aceitável
dado o cooldown de 300s.

A solução ideal de longo prazo é um proxy residencial brasileiro, que resolveria o
problema na raiz mantendo curl_cffi como método primário e eliminando o overhead do
browser fallback.
