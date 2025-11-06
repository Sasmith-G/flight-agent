from datetime import datetime, timedelta

from disruption_agent.models import DisruptionEvent, DisruptionType, FlightStatus


def make_status(delay_minutes: int = 0, cancelled: bool = False) -> FlightStatus:
    dep = datetime(2026, 7, 10, 14, 0)
    return FlightStatus(
        carrier_code="AF",
        flight_number="1234",
        departure_iata="NCE",
        arrival_iata="CDG",
        scheduled_departure=dep,
        estimated_departure=dep + timedelta(minutes=delay_minutes),
        scheduled_arrival=dep + timedelta(minutes=95),
        cancelled=cancelled,
    )


def test_delay_minutes_computed_from_estimate():
    assert make_status(delay_minutes=190).delay_minutes == 190


def test_no_delay_when_on_time():
    assert make_status(delay_minutes=0).delay_minutes == 0


def test_delay_never_negative_when_flight_leaves_early():
    assert make_status(delay_minutes=-10).delay_minutes == 0


def test_actionable_thresholds():
    assert not DisruptionEvent(type=DisruptionType.DELAY, delay_minutes=90).actionable
    assert DisruptionEvent(type=DisruptionType.DELAY, delay_minutes=120).actionable
    assert DisruptionEvent(type=DisruptionType.CANCELLATION).actionable
    assert not DisruptionEvent(type=DisruptionType.NONE).actionable
