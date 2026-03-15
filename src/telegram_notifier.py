"""Notificação via Telegram Bot API (httpx)."""

import httpx

from src.config import settings
from src.models import Opportunity

_TIMEOUT = 10.0


def _post(text: str, parse_mode: str = "HTML") -> bool:
    """Envia mensagem via Telegram Bot API."""
    if not settings.telegram_enabled:
        return False

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": settings.telegram_chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }

    try:
        resp = httpx.post(url, json=payload, timeout=_TIMEOUT)
        return resp.status_code == 200
    except httpx.HTTPError as e:
        print(f"[Telegram] Erro: {e}")
        return False


def send_message(text: str) -> bool:
    return _post(text)


def send_opportunity_alert(opp: Opportunity) -> bool:
    text = (
        f"📊 <b>ALERTA - Cartão Vermelho Under</b>\n\n"
        f"⚽ Jogo: <b>{opp.home_team} x {opp.away_team}</b>\n"
        f"🏆 Competição: {opp.competition}\n"
        f"📈 Odd: <b>{opp.odd:.2f}</b>\n"
        f"🕐 Tempo: {opp.minute}'\n"
        f"👉 Resultado: {opp.score}\n\n"
        f'🔗 <a href="{opp.url}">Apostar na Betano</a>'
    )
    return _post(text)
