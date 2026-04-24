"""Modelos tipados do Bot Red Card."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field


class Opportunity(BaseModel):
    """Oportunidade de aposta Under em Cartão Vermelho encontrada."""

    event_id: str
    home_team: str
    away_team: str
    odd: float = Field(gt=0)
    market_name: str
    selection_name: str
    url: str
    competition: str = "Desconhecida"
    minute: int = 0
    score: str = "0 x 0"

    @property
    def label(self) -> str:
        return f"{self.home_team} vs {self.away_team}"


class GameContext(BaseModel):
    """Contexto de um jogo ao vivo extraído da API."""

    id: str
    home: str
    away: str
    url: str
    minute: int = 0
    total_markets: int = 0
    competition: str = "Desconhecida"
    score: str = "0 x 0"

    @property
    def label(self) -> str:
        return f"{self.home} vs {self.away}"


@dataclass
class MatchResult:
    """Resultado da validação de uma aposta após o jogo terminar."""

    home_team: str
    away_team: str
    competition: str
    selection_name: str
    odd: float
    red_cards: int       # -1 se não verificado
    won: bool | None     # None se não verificado
    status: str          # "won" | "lost" | "unverified"
