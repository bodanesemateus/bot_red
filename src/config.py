"""Configurações centralizadas via Pydantic Settings."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Scanner ────────────────────────────────────────────────────
    cooldown_seconds: int = 300
    min_odd_threshold: float = 1.5
    min_match_minute: int = 5
    max_events_per_cycle: int = 10
    delay_between_events: int = 3
    recycle_every_n_cycles: int = 10
    min_markets_for_cards: int = 50

    # ── Betano ─────────────────────────────────────────────────────
    base_url: str = "https://www.betano.bet.br"
    overview_endpoint: str = "/danae-webapi/api/live/overview/latest"
    query_language_id: str = "5"
    query_operator_id: str = "8"

    # ── Browser ────────────────────────────────────────────────────
    page_load_timeout: int = 30_000
    selector_timeout: int = 15_000
    warmup_delay: float = 4.0
    navigation_delay: float = 2.0

    # ── Telegram ───────────────────────────────────────────────────
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    @property
    def overview_url(self) -> str:
        return (
            f"{self.base_url}{self.overview_endpoint}"
            f"?queryLanguageId={self.query_language_id}"
            f"&queryOperatorId={self.query_operator_id}"
            f"&includeVirtuals=true"
        )

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)


settings = Settings()
