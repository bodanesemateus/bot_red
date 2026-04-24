"""Persiste oportunidades alertadas no dia em JSON local."""

import json
from datetime import date, datetime
from pathlib import Path

from src.models import Opportunity

DATA_DIR = Path("data")


def _today_path() -> Path:
    return DATA_DIR / f"opportunities_{date.today().isoformat()}.json"


def append(opp: Opportunity) -> None:
    """Adiciona oportunidade ao JSON do dia (cria arquivo se não existir)."""
    DATA_DIR.mkdir(exist_ok=True)
    path = _today_path()
    entries: list[dict] = []
    if path.exists():
        entries = json.loads(path.read_text(encoding="utf-8"))
    entries.append({
        "event_id": opp.event_id,
        "home_team": opp.home_team,
        "away_team": opp.away_team,
        "competition": opp.competition,
        "minute": opp.minute,
        "score": opp.score,
        "odd": opp.odd,
        "selection_name": opp.selection_name,
        "url": opp.url,
        "alerted_at": datetime.now().isoformat(timespec="seconds"),
    })
    path.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_today() -> list[dict]:
    """Retorna as entradas do JSON do dia. Lista vazia se arquivo não existir."""
    path = _today_path()
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def delete_today() -> None:
    """Apaga o JSON do dia. Silencioso se o arquivo não existir."""
    path = _today_path()
    if path.exists():
        path.unlink()
