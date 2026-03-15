"O WAF da Betano é mais complexo que o esperado. O fetch() manual falhou com 403 porque o frontend deles gera tokens de telemetria/segurança em tempo real e anexa aos headers de requisições da API. Nosso fetch manual não aciona esses scripts.

A Solução Definitiva: Interceptação Passiva.
Em vez de ativamente solicitarmos a API, vamos deixar o site fazer isso e apenas 'escutar' a resposta orgânica da rede. O WAF não tem como bloquear isso, pois quem fará o request é o próprio código React da Betano.

Tarefa de Refatoração:

Desfaça o uso do fetch_api no src/main.py e remova-o do browser.py.

No src/main.py (ou onde estiver a busca inicial), refaça a função _fetch_live_events.

A lógica agora deve ser:

Criar uma nova aba no contexto quente: page = await browser.new_page().

Criar uma promessa de captura: response_promise = page.expect_response(lambda r: 'live/overview' in r.url, timeout=20000).

Navegar para a página pública de apostas ao vivo: await page.goto(f"{settings.base_url}/live/").

Aguardar a interceptação: api_response = await response_promise.

Extrair o JSON: data = await api_response.json().

Após capturar o JSON, extraia os eventos exatamente como era feito antes e feche essa página (await page.close()), retornando a lista de games.

Faça tratamento de erro adequado: se der timeout na captura da API, faça um retry (ex: recarregue a página 1 vez antes de desistir).

Execute as alterações necessárias para que a fase de descoberta de jogos use interceptação passiva."