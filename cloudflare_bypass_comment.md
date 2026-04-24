Tive o mesmo problema rodando em EC2 (IP de datacenter). O Cloudflare bloqueia na hora porque o score de bot é altíssimo pra esses ranges de IP.

A solução que funcionou foi um fallback em 3 estágios:

**Estágio 1 (~200ms):** curl_cffi com cookies transferidos do Playwright
O Playwright (com playwright-stealth) passa no challenge do Cloudflare e recebe os cookies de sessão, incluindo o `cf_clearance`. Exporto esses cookies + o User-Agent e injeto numa `curl_cffi.Session`. Se o IP não estiver na blocklist de datacenter, essa session autenticada passa livre.

**Estágio 2 (~1-2s):** fetch() numa aba persistente do browser
Se o Estágio 1 receber 403 (session pinning ou IP bloqueado), uso uma aba do Playwright que fica aberta na home do site. Faço o fetch via `page.evaluate()` — o browser já tem os cookies e o TLS fingerprint certo, então passa.

**Estágio 3 (~8-15s):** fallback completo
Abre nova aba, navega até a home, faz o fetch. Comportamento original, usado só se a aba persistente ficar stale.

**Stack:**
- `playwright` (async) + `playwright-stealth` — bypassa detecção de automação no nível do contexto
- `curl_cffi` com `impersonate="chrome131"` — replica o TLS fingerprint do Chrome real
- Transferência de cookies Playwright → curl_cffi para autenticar requests diretas

O ganho principal é que na maioria dos ciclos você cai no Estágio 1 ou 2 em vez de sempre renavegar o browser inteiro.
