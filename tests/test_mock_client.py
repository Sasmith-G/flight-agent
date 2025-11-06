from datetime import date

from disruption_agent.amadeus import MockAmadeusClient


def test_delay_scenario_reports_190_minutes():
    client = MockAmadeusClient(scenario="delay")
    status = client.flight_status("AF", "1234", date(2026, 7, 10))
    assert status is not None
    assert status.delay_minutes == 190
    assert not status.cancelled


def test_cancellation_scenario():
    client = MockAmadeusClient(scenario="cancellation")
    status = client.flight_status("AF", "1234", date(2026, 7, 10))
    assert status is not None and status.cancelled


def test_alternatives_have_prices_and_route():
    options = MockAmadeusClient().search_alternatives("NCE", "CDG", date(2026, 7, 10))
    assert len(options) == 3
    assert all(o.departure_iata == "NCE" and o.price_total > 0 for o in options)
