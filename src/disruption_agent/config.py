from functools import lru_cache
from importlib import resources
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


def default_fare_rules_dir() -> str:
    """Policy corpus bundled with the package (EU261, carrier policies)."""
    return str(resources.files("disruption_agent") / "data")


class Settings(BaseSettings):
    """Runtime configuration, loaded from environment variables / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    agent_mode: Literal["mock", "live"] = "mock"

    amadeus_client_id: str = ""
    amadeus_client_secret: str = ""
    amadeus_base_url: str = "https://test.api.amadeus.com"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"

    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from: str = ""
    twilio_to: str = ""

    fare_rules_dir: str = ""

    @property
    def resolved_fare_rules_dir(self) -> str:
        return self.fare_rules_dir or default_fare_rules_dir()

    @property
    def live(self) -> bool:
        return self.agent_mode == "live"


@lru_cache
def get_settings() -> Settings:
    return Settings()
