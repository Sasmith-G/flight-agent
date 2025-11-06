from datetime import date
from typing import TypedDict

from ..models import (
    DisruptionEvent,
    FlightStatus,
    PolicyPassage,
    RebookingOption,
    Recommendation,
)


class AgentState(TypedDict, total=False):
    """State threaded through the LangGraph pipeline."""

    # inputs
    carrier: str
    flight_number: str
    departure_date: date

    # produced by nodes
    status: FlightStatus | None
    event: DisruptionEvent
    options: list[RebookingOption]
    passages: list[PolicyPassage]
    recommendation: Recommendation | None
    delivery_ref: str | None
    trace: list[str]
