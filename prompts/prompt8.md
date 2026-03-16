"O bot está quase perfeito, mas precisamos de dois ajustes finais para deixá-lo à prova de falhas e com a comunicação correta.

Tarefa 1: Busca Flexível (Substring) no Scanner
Casas de apostas mudam a formatação com frequência (ex: usando vírgula no lugar de ponto, ou espaços diferentes).
No arquivo src/scanner.py, atualize a lógica de validação do nome da seleção dentro de _find_opportunities.
Em vez de usar um match exato contra a lista UNDER_SELECTIONS, mude para uma lógica de validação por substring (contém). Uma seleção deve ser considerada válida se atender a ambas as condições abaixo (após converter para minúsculo):

Contém o número da linha: "0.5" OU "0,5" OU "1.5" OU "1,5".

Contém a intenção de under: "menos" OU "under" OU "nao" OU "não".
Exceção: Se a seleção for exatamente "não" ou "nao" (usado no mercado 'Haverá cartão vermelho?'), ela deve ser aceite diretamente como under 0.5.
Pode remover a dependência estrita da lista de strings exatas UNDER_SELECTIONS.

Tarefa 2: Atualizar a Mensagem de Inicialização
Como o bot agora suporta múltiplas linhas de cartões, precisamos atualizar a mensagem de inicialização no Telegram para refletir isso.
No arquivo main.py, localize a função run() e procure pelo bloco onde o bot envia a mensagem de inicialização via telegram.send_message(...).
Adicione uma nova linha a essa mensagem informando as linhas monitoradas. O texto deve ficar semelhante a isto:

f"<b>BOT RED CARD v2 iniciado</b>\n\n"
f"Linhas: Under 0.5 e 1.5\n"
f"Cooldown: {settings.cooldown_seconds}s\n"
f"Max eventos: {settings.max_events_per_cycle}\n"
f"Odd mínima: {settings.min_odd_threshold}\n"
f"Horário: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"

Execute estas duas alterações em conjunto."