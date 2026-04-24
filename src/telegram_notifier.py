"""Notificação via Telegram Bot API (httpx)."""

from __future__ import annotations

from datetime import date as _date

import httpx

from src.config import settings
from src.models import Opportunity, MatchResult

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
        f"🎯 Mercado: <b>{opp.selection_name}</b>\n"
        f"📈 Odd: <b>{opp.odd:.2f}</b>\n"
        f"🕐 Tempo: {opp.minute}'\n"
        f"👉 Resultado: {opp.score}\n\n"
        f'🔗 <a href="{opp.url}">Apostar na Betano</a>'
    )
    return _post(text)


def send_daily_report(results: list[MatchResult], report_date: str | None = None) -> bool:
    """Envia relatório diário consolidado no Telegram."""
    if report_date is None:
        report_date = _date.today().strftime("%d/%m/%Y")

    won = [r for r in results if r.status == "won"]
    lost = [r for r in results if r.status == "lost"]
    unverified = [r for r in results if r.status == "unverified"]
    verified = won + lost

    lines = [
        f"📋 <b>RELATÓRIO DIÁRIO — {report_date}</b>\n",
        f"Total de alertas: {len(results)}",
        f"✅ Vencedores: {len(won)}",
        f"❌ Perdedores: {len(lost)}",
        f"⏳ Não verificados: {len(unverified)}",
        "\n─────────────────────────",
    ]

    for r in results:
        if r.status == "won":
            icon = "✅"
            detail = f"{r.red_cards} cartão(ões) vermelho(s)"
        elif r.status == "lost":
            icon = "❌"
            detail = f"{r.red_cards} cartão(ões) vermelho(s)"
        else:
            icon = "⏳"
            detail = "Não verificado — timeout SofaScore"

        lines.append(
            f"{icon} <b>{r.home_team} x {r.away_team}</b>\n"
            f"   {r.selection_name} @ {r.odd:.2f} | {detail}"
        )

    lines.append("─────────────────────────")

    if verified:
        pct = int(len(won) / len(verified) * 100)
        lines.append(f"Taxa de acerto: {pct}% ({len(won)}/{len(verified)} verificados)")

    return _post("\n".join(lines))
