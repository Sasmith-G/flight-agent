from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class DisruptionType(StrEnum):
    NONE = "none"
    DELAY = "delay"
    CANCELLATION = "cancellation"


class FlightStatus(BaseModel):
    """Normalised view of an Amadeus On-Demand Flight Status response."""

    carrier_code: str
    flight_number: str
    departure_iata: str
    arrival_iata: str
    scheduled_departure: datetime
    estimated_departure: datetime | None = None
    scheduled_arrival: datetime
    estimated_arrival: datetime | None = None
    cancelled: bool = False

    @property
    def flight_designator(self) -> str:
        return f"{self.carrier_code}{self.flight_number}"

    @property
    def delay_minutes(self) -> int:
        if self.estimated_departure is None:
            return 0
        return max(
            0, int((self.estimated_departure - self.scheduled_departure).total_seconds() // 60)
        )


class DisruptionEvent(BaseModel):
    """The agent's assessment of whether — and how badly — a flight is disrupted."""

    type: DisruptionType
    delay_minutes: int = 0
    delay_probability: float | None = Field(
        default=None, description="P(delay > 2h) from Amadeus Flight Delay Prediction"
    )
    reason: str = ""

    @property
    def actionable(self) -> bool:
        """Disruptions worth rebooking: cancellations or delays of 2h+ (EU261 threshold)."""
        return self.type == DisruptionType.CANCELLATION or (
            self.type == DisruptionType.DELAY and self.delay_minutes >= 120
        )


class RebookingOption(BaseModel):
    """Normalised view of an Amadeus Flight Offers Search result."""

    carrier_code: str
    flight_number: str
    departure_iata: str
    arrival_iata: str
    departure: datetime
    arrival: datetime
    price_total: float
    currency: str = "EUR"
    seats_available: int | None = None

    @property
    def label(self) -> str:
        return (
            f"{self.carrier_code}{self.flight_number} "
            f"{self.departure_iata}->{self.arrival_iata} "
            f"dep {self.departure:%H:%M} arr {self.arrival:%H:%M} "
            f"({self.price_total:.2f} {self.currency})"
        )


class PolicyPassage(BaseModel):
    """A fare-rule / passenger-rights passage retrieved by the RAG layer."""

    source: str
    text: str
    score: float


class Recommendation(BaseModel):
    """Final output: the message sent to the traveller, with its grounding."""

    summary: str
    options: list[RebookingOption]
    policy_basis: list[PolicyPassage]
    generated_at: datetime = Field(default_factory=datetime.now)
