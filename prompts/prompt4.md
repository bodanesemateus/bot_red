O Bypass XHR (Fetch via Console)
"O teste inicial foi ótimo! A sessão quente funcionou perfeitamente (capturou 51 cookies). Porém, o bot tomou HTTP 403 ao tentar buscar a lista de jogos na API.

O Problema: > Isso acontece porque fazer um page.goto() ou um Request direto para uma URL de API (JSON) faz o navegador enviar XHR headers errados (como sec-fetch-dest: document), o que aciona o WAF da Betano instantaneamente. Ninguém digita a URL da API na barra de endereço.

A Solução (Bypass):
A melhor tática de evasão é executar o fetch() do JavaScript de dentro da aba da Home Page que já está aberta, autorizada e com o 'stealth' aplicado.

Tarefa:

No src/browser.py (ou na classe equivalente que gerencia o Playwright), crie um método async def fetch_api(self, api_url: str) -> dict:

Este método deve usar o contexto da página que já está na Home e executar:
return await self.page.evaluate(f"() => fetch('{api_url}').then(res => res.json())")

Altere a lógica de busca de eventos ao vivo (provavelmente no main.py ou scanner.py) para usar este método fetch_api com a URL completa do overview, em vez de navegar até a API ou usar httpx/curl_cffi.

Se a resposta retornar nula ou der erro, faça o fetch_api tentar novamente 1 vez após 2 segundos.

Faça apenas os ajustes pontuais para corrigir essa chamada da API."