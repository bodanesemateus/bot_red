"""Testes de opportunity_log — leitura e escrita do JSON diário."""

import json
from datetime import date
from pathlib import Path

import pytest

from src.models import Opportunity
from src import opportunity_log


@pytest.fixture(autouse=True)
def tmp_data_dir(tmp_path, monkeypatch):
    """Redireciona DATA_DIR para diretório temporário em cada teste."""
    monkeypatch.setattr(opportunity_log, "DATA_DIR", tmp_path)
    return tmp_path


def _make_opp(**kwargs) -> Opportunity:
    defaults = dict(
        event_id="1",
        home_team="Flamengo",
        away_team="Corinthians",
        odd=1.85,
        market_name="Total de cartões vermelhos",
        selection_name="Menos de 0.5",
        url="https://betano.bet.br/jogo/1/",
        competition="Brasileirão",
        minute=30,
        score="1 x 0",
    )
    defaults.update(kwargs)
    return Opportunity(**defaults)


def test_append_creates_file(tmp_path):
    opp = _make_opp()
    opportunity_log.append(opp)
    today = date.today().isoformat()
    path = tmp_path / f"opportunities_{today}.json"
    assert path.exists()


def test_append_stores_fields(tmp_path):
    opp = _make_opp(home_team="Santos", away_team="Palmeiras", odd=2.10)
    opportunity_log.append(opp)
    today = date.today().isoformat()
    path = tmp_path / f"opportunities_{today}.json"
    data = json.loads(path.read_text())
    assert len(data) == 1
    entry = data[0]
    assert entry["home_team"] == "Santos"
    assert entry["away_team"] == "Palmeiras"
    assert entry["odd"] == 2.10
    assert "alerted_at" in entry


def test_append_multiple_opps(tmp_path):
    opportunity_log.append(_make_opp(event_id="1"))
    opportunity_log.append(_make_opp(event_id="2"))
    today = date.today().isoformat()
    data = json.loads((tmp_path / f"opportunities_{today}.json").read_text())
    assert len(data) == 2


def test_load_today_empty_when_no_file():
    assert opportunity_log.load_today() == []


def test_load_today_returns_entries(tmp_path):
    opportunity_log.append(_make_opp())
    entries = opportunity_log.load_today()
    assert len(entries) == 1
    assert entries[0]["home_team"] == "Flamengo"


def test_delete_today_removes_file(tmp_path):
    opportunity_log.append(_make_opp())
    opportunity_log.delete_today()
    today = date.today().isoformat()
    assert not (tmp_path / f"opportunities_{today}.json").exists()


def test_delete_today_no_error_if_no_file():
    opportunity_log.delete_today()
