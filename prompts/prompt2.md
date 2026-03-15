O Motor de Evasão e o "Hot Session"
"Ótimo resumo. Agora vamos avançar para a implementação do núcleo do bot.

Tarefa 1: Modelos e Configuração
Crie o arquivo src/models.py com os modelos Pydantic para Opportunity e GameContext, e o src/config.py usando PydanticSettings para gerenciar o .env de forma tipada (inclua as variáveis de ODD_MIN, TELEGRAM_TOKEN, etc.).

Tarefa 2: Browser Engine (O segredo da evasão)
Crie src/browser.py. Este módulo deve:

Iniciar o Playwright com stealth e um User-Agent de um Chrome real (ex: v122+ no Windows ou Mac).

Implementar a 'Sessão Quente': Antes de ir para qualquer jogo, o navegador deve carregar betano.bet.br, aguardar o carregamento da home e, se houver um modal de cookies ou 'Splash Screen', tratá-lo ou esperar que desapareça.

Criar um método get_page_content(url) que use a mesma aba/contexto para navegar internamente para o link do jogo, simulando um usuário clicando.

Tarefa 3: O Novo Scanner
Crie src/scanner.py herdando os termos de mercado que você mapeou (cartões vermelhos, expulsão).

Use page.wait_for_selector com timeout de 15s para garantir que os mercados carregaram.

Se após o carregamento o texto 'Splash Screen' ainda for predominante ou o body estiver vazio, implemente uma lógica de 'Recarregar' ou 'Limpar Cookies'.

Retorne a Opportunity validada com a Odd encontrada."