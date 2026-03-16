Adicionando a linha Under 1.5
"O bot está funcionando perfeitamente! Agora queremos expandir a cobertura de apostas.

Atualmente, o bot procura apenas pela linha 'Under 0.5' (Menos de 0.5) nos mercados de cartão vermelho. O objetivo agora é monitorar as linhas 'Under 0.5' E 'Under 1.5' simultaneamente.

Tarefa:
No arquivo src/scanner.py, localize a função onde ocorre a filtragem da seleção (provavelmente em _find_opportunity ou similar).
Ajuste a condição que verifica o nome da seleção (selection_name). Em vez de exigir apenas a string '0.5', modifique a lógica para aceitar que o nome contenha '0.5' OU '1.5'.
Continue garantindo que a opção seja de 'Under' (Menos).

Como o nosso modelo Opportunity já salva o selection_name, a notificação do Telegram continuará funcionando perfeitamente, exibindo de forma dinâmica se o alerta é para 'Menos de 0.5' ou 'Menos de 1.5'."