import pytest

from disruption_agent.config import default_fare_rules_dir


@pytest.fixture
def fare_rules_dir() -> str:
    return default_fare_rules_dir()
