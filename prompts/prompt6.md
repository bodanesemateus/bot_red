"Os logs mostram um Timeout na interceptação. Isso acontece porque a Betano usa Server-Side Rendering (SSR) no carregamento inicial da página /live/. Os dados vêm embutidos no HTML, então o frontend não faz um request de rede para a API de overview na abertura, causando o timeout.

Nós desviamos do plano original da arquitetura híbrida. A busca da API de overview funcionava perfeitamente na versão 1 do projeto usando a biblioteca curl_cffi, pois ela falsifica o TLS Fingerprinting e passa pelo Cloudflare sem problemas. O WAF só nos bloqueava nas páginas de detalhes do jogo (que agora já resolvemos com a Sessão Quente do Playwright).

Tarefa de Correção:

Remova a lógica de interceptação passiva (_intercept_overview) e pare de usar o Playwright para buscar a API de overview.

No src/main.py (ou num novo src/api_client.py), importe o curl_cffi: from curl_cffi import requests (ou requests.AsyncSession).

Refaça a função _fetch_live_events para fazer um GET direto na settings.overview_url usando o curl_cffi com o parâmetro impersonate="chrome120" e timeout=30.

Converta a resposta para JSON, extraia os jogos elegíveis (como já estava sendo feito) e retorne a lista.

Apenas a segunda fase (o Scanner de cartões) deve continuar usando o browser.new_page() do Playwright com a Sessão Quente.

Reescreva a fase 1 para usar puramente curl_cffi."