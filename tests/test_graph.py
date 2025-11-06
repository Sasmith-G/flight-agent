"""End-to-end tests of the LangGraph pipeline in mock mode (offline, deterministic)."""

from datetime import date

import pytest

from disruption_agent.agent.graph import DisruptionAgent, build_graph
from disruption_agent.amadeus import MockAmadeusClient
from disruption_agent.llm import MockLLM
from disruption_agent.models import DisruptionType
from disruption_agent.notify import Notifier
from disruption_agent.rag import PolicyRetriever


class SpyNotifier(Notifier):
    def __init__(self):
        self.messages: list[str] = []

    def send(self, message: str) -> str:
        self.messages.append(message)
        return f"spy-{len(self.messages)}"


def run(scenario: str, fare_rules_dir: str):
    notifier = SpyNotifier()
    agent = DisruptionAgent(
        amadeus=MockAmadeusClient(scenario=scenario),
        retriever=PolicyRetriever(fare_rules_dir),
        llm=MockLLM(),
        notifier=notifier,
    )
    app = build_graph(agent)
    result = app.invoke(
        {"carrier": "AF", "flight_number": "1234", "departure_date": date(2026, 7, 10), "trace": []}
    )
    return result, notifier


def test_delay_scenario_notifies_with_grounded_options(fare_rules_dir):
    result, notifier = run("delay", fare_rules_dir)
    assert result["event"].type == DisruptionType.DELAY
    assert result["recommendation"] is not None
    assert len(notifier.messages) == 1
    message = notifier.messages[0]
    assert "delayed by 3h10" in message
    assert "AF6205" in message  # earliest-arrival option present
    assert "eu261" in message  # policy source cited


def test_cancellation_scenario_notifies(fare_rules_dir):
    result, notifier = run("cancellation", fare_rules_dir)
    assert result["event"].type == DisruptionType.CANCELLATION
    assert "CANCELLED" in notifier.messages[0]


def test_on_time_flight_sends_no_notification(fare_rules_dir):
    result, notifier = run("on_time", fare_rules_dir)
    assert result["event"].type == DisruptionType.NONE
    assert notifier.messages == []
    assert result.get("recommendation") is None


def test_options_ordered_by_earliest_arrival(fare_rules_dir):
    result, _ = run("delay", fare_rules_dir)
    arrivals = [o.arrival for o in result["options"]]
    assert arrivals == sorted(arrivals)


def test_trace_records_every_step(fare_rules_dir):
    result, _ = run("delay", fare_rules_dir)
    assert len(result["trace"]) == 6


@pytest.mark.parametrize("scenario", ["delay", "cancellation"])
def test_recommendation_grounded_in_retrieved_passages(fare_rules_dir, scenario):
    result, _ = run(scenario, fare_rules_dir)
    assert result["passages"], "policy passages must ground the recommendation"
    assert result["recommendation"].policy_basis == result["passages"]
