"""LLM layer that drafts the passenger message.

The LLM is intentionally used for exactly one thing: turning structured, verified facts
(disruption data, rebooking options, retrieved policy passages) into a clear passenger
message. It never invents flights, prices or entitlements — everything it says is
grounded in data the pipeline already validated. `MockLLM` renders the same message
deterministically from a template, which keeps the demo and the test suite offline.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .config import Settings, get_settings
from .models import DisruptionEvent, DisruptionType, FlightStatus, PolicyPassage, RebookingOption

SYSTEM_PROMPT = """You are a travel-disruption assistant writing a short message to a passenger.

Rules:
- Use ONLY the facts provided: flight data, rebooking options, and policy passages.
- Quote entitlements only when supported by a provided policy passage, and name the source.
- Never promise compensation unconditionally; say "likely eligible" and cite the rule.
- Present at most 3 rebooking options, ordered by earliest arrival.
- Be concise, calm and actionable. End by asking which option the passenger prefers.
"""


def build_user_prompt(
    status: FlightStatus,
    event: DisruptionEvent,
    options: list[RebookingOption],
    passages: list[PolicyPassage],
) -> str:
    lines = [
        f"Flight: {status.flight_designator} {status.departure_iata}->{status.arrival_iata}",
        f"Scheduled departure: {status.scheduled_departure:%Y-%m-%d %H:%M}",
        f"Disruption: {event.type.value}, delay={event.delay_minutes}min",
    ]
    if event.delay_probability is not None:
        lines.append(f"Predicted probability of >2h delay: {event.delay_probability:.0%}")
    lines.append("\nRebooking options:")
    lines += [f"- {o.label} ({o.seats_available or '?'} seats left)" for o in options]
    lines.append("\nApplicable policy passages:")
    lines += [f"[{p.source}]\n{p.text}" for p in passages]
    return "\n".join(lines)


class LLM(ABC):
    @abstractmethod
    def draft_recommendation(
        self,
        status: FlightStatus,
        event: DisruptionEvent,
        options: list[RebookingOption],
        passages: list[PolicyPassage],
    ) -> str: ...


class AnthropicLLM(LLM):
    def __init__(self, settings: Settings | None = None):
        import anthropic

        self.settings = settings or get_settings()
        self.client = anthropic.Anthropic(api_key=self.settings.anthropic_api_key)

    def draft_recommendation(self, status, event, options, passages) -> str:
        response = self.client.messages.create(
            model=self.settings.anthropic_model,
            max_tokens=700,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": build_user_prompt(status, event, options, passages)}
            ],
        )
        return response.content[0].text


class MockLLM(LLM):
    """Deterministic template renderer producing the same message shape as the live LLM."""

    def draft_recommendation(self, status, event, options, passages) -> str:
        if event.type == DisruptionType.CANCELLATION:
            headline = (
                f"Your flight {status.flight_designator} "
                f"{status.departure_iata}->{status.arrival_iata} has been CANCELLED."
            )
        else:
            hours, minutes = divmod(event.delay_minutes, 60)
            headline = (
                f"Your flight {status.flight_designator} "
                f"{status.departure_iata}->{status.arrival_iata} "
                f"is delayed by {hours}h{minutes:02d}."
            )
        option_lines = [
            f"  {i}. {o.label} — {o.seats_available or '?'} seats left"
            for i, o in enumerate(sorted(options, key=lambda o: o.arrival)[:3], start=1)
        ]
        sources = ", ".join(dict.fromkeys(p.source.split(" — ")[0] for p in passages))
        entitlement = (
            "Based on the applicable rules, rebooking is free of charge and you are "
            f"likely eligible for care and compensation (sources: {sources})."
        )
        return "\n".join(
            [
                headline,
                "",
                "Here are your best rebooking options (earliest arrival first):",
                *option_lines,
                "",
                entitlement,
                "",
                "Reply with the option number you prefer and I will proceed.",
            ]
        )


def get_llm(settings: Settings | None = None) -> LLM:
    settings = settings or get_settings()
    if settings.live and settings.anthropic_api_key:
        return AnthropicLLM(settings)
    return MockLLM()
