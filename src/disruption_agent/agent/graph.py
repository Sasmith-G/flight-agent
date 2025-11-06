"""LangGraph pipeline for disruption handling.

    check_status ──> assess_disruption ──┬─(actionable)──> search_alternatives
                                         │                        │
                                         └─(not actionable)──> END│
                                                                  v
                             notify <── draft_recommendation <── retrieve_policies

Each node is a thin, testable function over `AgentState`; external systems (Amadeus,
LLM, notifier) are injected so the same graph runs in mock and live mode.
"""

from __future__ import annotations

from datetime import date

from langgraph.graph import END, StateGraph

from ..amadeus import AmadeusClient, get_client
from ..llm import LLM, get_llm
from ..models import DisruptionEvent, DisruptionType, Recommendation
from ..notify import Notifier, get_notifier
from ..rag import PolicyRetriever
from .state import AgentState


def _trace(state: AgentState, message: str) -> list[str]:
    return [*state.get("trace", []), message]


class DisruptionAgent:
    """Wires external dependencies into the LangGraph nodes."""

    def __init__(
        self,
        amadeus: AmadeusClient,
        retriever: PolicyRetriever,
        llm: LLM,
        notifier: Notifier,
    ):
        self.amadeus = amadeus
        self.retriever = retriever
        self.llm = llm
        self.notifier = notifier

    # -- nodes -------------------------------------------------------------

    def check_status(self, state: AgentState) -> AgentState:
        status = self.amadeus.flight_status(
            state["carrier"], state["flight_number"], state["departure_date"]
        )
        note = (
            f"Flight status retrieved for {state['carrier']}{state['flight_number']}"
            if status
            else "Flight not found in schedules"
        )
        return {"status": status, "trace": _trace(state, note)}

    def assess_disruption(self, state: AgentState) -> AgentState:
        status = state.get("status")
        if status is None:
            event = DisruptionEvent(type=DisruptionType.NONE, reason="flight not found")
            return {"event": event, "trace": _trace(state, "No flight data; stopping")}

        probability = self.amadeus.delay_prediction(
            status.departure_iata,
            status.arrival_iata,
            status.scheduled_departure,
            status.carrier_code,
            status.flight_number,
        )
        if status.cancelled:
            event = DisruptionEvent(
                type=DisruptionType.CANCELLATION,
                delay_probability=probability,
                reason="carrier cancelled the flight",
            )
        elif status.delay_minutes > 0:
            event = DisruptionEvent(
                type=DisruptionType.DELAY,
                delay_minutes=status.delay_minutes,
                delay_probability=probability,
                reason="estimated departure later than schedule",
            )
        else:
            event = DisruptionEvent(type=DisruptionType.NONE, delay_probability=probability)
        return {
            "event": event,
            "trace": _trace(
                state,
                f"Assessment: {event.type.value}"
                + (f", {event.delay_minutes}min" if event.delay_minutes else ""),
            ),
        }

    def search_alternatives(self, state: AgentState) -> AgentState:
        status = state["status"]
        assert status is not None
        options = self.amadeus.search_alternatives(
            status.departure_iata, status.arrival_iata, status.scheduled_departure.date()
        )
        options.sort(key=lambda o: o.arrival)
        return {
            "options": options,
            "trace": _trace(state, f"Found {len(options)} rebooking options"),
        }

    def retrieve_policies(self, state: AgentState) -> AgentState:
        event = state["event"]
        query = (
            "cancellation re-routing refund compensation"
            if event.type == DisruptionType.CANCELLATION
            else f"delay {event.delay_minutes // 60} hours compensation rebooking care meals"
        )
        passages = self.retriever.retrieve(query, top_k=3)
        return {
            "passages": passages,
            "trace": _trace(state, f"Retrieved {len(passages)} policy passages"),
        }

    def draft_recommendation(self, state: AgentState) -> AgentState:
        status = state["status"]
        assert status is not None
        summary = self.llm.draft_recommendation(
            status, state["event"], state["options"], state["passages"]
        )
        recommendation = Recommendation(
            summary=summary, options=state["options"][:3], policy_basis=state["passages"]
        )
        return {
            "recommendation": recommendation,
            "trace": _trace(state, "Recommendation drafted"),
        }

    def notify(self, state: AgentState) -> AgentState:
        recommendation = state["recommendation"]
        assert recommendation is not None
        ref = self.notifier.send(recommendation.summary)
        return {"delivery_ref": ref, "trace": _trace(state, f"Notification sent ({ref})")}

    # -- routing -----------------------------------------------------------

    @staticmethod
    def route_after_assessment(state: AgentState) -> str:
        return "search_alternatives" if state["event"].actionable else END


def build_graph(agent: DisruptionAgent):
    graph = StateGraph(AgentState)
    graph.add_node("check_status", agent.check_status)
    graph.add_node("assess_disruption", agent.assess_disruption)
    graph.add_node("search_alternatives", agent.search_alternatives)
    graph.add_node("retrieve_policies", agent.retrieve_policies)
    graph.add_node("draft_recommendation", agent.draft_recommendation)
    graph.add_node("notify", agent.notify)

    graph.set_entry_point("check_status")
    graph.add_edge("check_status", "assess_disruption")
    graph.add_conditional_edges(
        "assess_disruption",
        agent.route_after_assessment,
        {"search_alternatives": "search_alternatives", END: END},
    )
    graph.add_edge("search_alternatives", "retrieve_policies")
    graph.add_edge("retrieve_policies", "draft_recommendation")
    graph.add_edge("draft_recommendation", "notify")
    graph.add_edge("notify", END)
    return graph.compile()


def run_agent(
    carrier: str,
    flight_number: str,
    departure_date: date,
    scenario: str = "delay",
    fare_rules_dir: str | None = None,
) -> AgentState:
    """Convenience entry point used by the CLI, the tests and the MCP server."""
    from ..config import get_settings

    agent = DisruptionAgent(
        amadeus=get_client(scenario=scenario),
        retriever=PolicyRetriever(fare_rules_dir or get_settings().resolved_fare_rules_dir),
        llm=get_llm(),
        notifier=get_notifier(),
    )
    app = build_graph(agent)
    return app.invoke(
        {
            "carrier": carrier,
            "flight_number": flight_number,
            "departure_date": departure_date,
            "trace": [],
        }
    )
