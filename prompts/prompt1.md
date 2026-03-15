Contexto e Reset de Arquitetura
"Estou iniciando a refatoração total deste bot de rastreamento de odds da Betano. O projeto atual está na pasta bot_red/, mas ele parou de funcionar porque a Betano reforçou as proteções, resultando em 'Splash Screens' e páginas vazias durante o scraping.

Minhas diretrizes para você:

O que herdar: Analise bot_red/src/scanner.py apenas para entender os nomes dos mercados (Cartão Vermelho, Expulsão, etc.) e as seleções de Under 0.5.

O que descartar: Ignore a lógica atual de inicialização do Playwright e do curl_cffi, pois estão sendo detectados.

Nova Abordagem de Evasão: Vamos usar playwright-stealth, rotação de headers reais e uma estratégia de 'Sessão Quente' (abrir a home, aceitar cookies e navegar internamente) para evitar o bloqueio.

Estrutura: Quero um código modular, tipado (Pydantic) e preparado para rodar em Docker de forma resiliente.

Tarefa Inicial:
Leia os arquivos na pasta bot_red/ para entender o funcionamento atual e, em seguida, crie o novo Dockerfile e o requirements.txt otimizados para Python 3.11-slim, incluindo todas as dependências necessárias para o Playwright com Stealth e tratamento de imagens/fonts se necessário. Não escreva o código do bot ainda, apenas prepare o ambiente de infraestrutura."