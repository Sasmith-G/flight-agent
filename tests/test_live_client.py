"""LiveAmadeusClient contract tests against mocked HTTP (respx) — no network."""

from datetime import date

import respx
from httpx import Response

from disruption_agent.amadeus import LiveAmadeusClient
from disruption_agent.config import Settings

BASE = "https://test.api.amadeus.com"


def make_client() -> LiveAmadeusClient:
    return LiveAmadeusClient(
        Settings(
            agent_mode="live",
            amadeus_client_id="id",
            amadeus_client_secret="secret",
            amadeus_base_url=BASE,
        )
    )


def mock_token(router):
    router.post(f"{BASE}/v1/security/oauth2/token").mock(
        return_value=Response(200, json={"access_token": "tok", "expires_in": 1799})
    )


@respx.mock
def test_flight_status_parses_timings():
    mock_token(respx)
    respx.get(f"{BASE}/v2/schedule/flights").mock(
        return_value=Response(
            200,
            json={
                "data": [
                    {
                        "flightPoints": [
                            {
                                "iataCode": "NCE",
                                "departure": {
                                    "timings": [
                                        {"qualifier": "STD", "value": "2026-07-10T14:00:00"},
                                        {"qualifier": "ETD", "value": "2026-07-10T17:10:00"},
                                    ]
                                },
                            },
                            {
                                "iataCode": "CDG",
                                "arrival": {
                                    "timings": [
                                        {"qualifier": "STA", "value": "2026-07-10T15:35:00"}
                                    ]
                                },
                            },
                        ]
                    }
                ]
            },
        )
    )
    status = make_client().flight_status("AF", "1234", date(2026, 7, 10))
    assert status is not None
    assert status.delay_minutes == 190
    assert status.departure_iata == "NCE" and status.arrival_iata == "CDG"


@respx.mock
def test_token_is_cached_between_calls():
    mock_token(respx)
    route = respx.get(f"{BASE}/v2/schedule/flights").mock(
        return_value=Response(200, json={"data": []})
    )
    client = make_client()
    client.flight_status("AF", "1234", date(2026, 7, 10))
    client.flight_status("AF", "1234", date(2026, 7, 10))
    token_calls = [c for c in respx.calls if c.request.url.path.endswith("token")]
    assert len(token_calls) == 1
    assert route.call_count == 2


@respx.mock
def test_delay_prediction_degrades_gracefully_on_error():
    mock_token(respx)
    respx.get(f"{BASE}/v1/travel/predictions/flight-delay").mock(return_value=Response(400))
    from datetime import datetime

    result = make_client().delay_prediction("NCE", "CDG", datetime(2026, 7, 10, 14), "AF", "1234")
    assert result is None


@respx.mock
def test_flight_offers_parsing():
    mock_token(respx)
    respx.get(f"{BASE}/v2/shopping/flight-offers").mock(
        return_value=Response(
            200,
            json={
                "data": [
                    {
                        "numberOfBookableSeats": 5,
                        "itineraries": [
                            {
                                "segments": [
                                    {
                                        "carrierCode": "AF",
                                        "number": "6205",
                                        "departure": {
                                            "iataCode": "NCE",
                                            "at": "2026-07-10T16:00:00",
                                        },
                                        "arrival": {"iataCode": "CDG", "at": "2026-07-10T17:35:00"},
                                    }
                                ]
                            }
                        ],
                        "price": {"grandTotal": "96.00", "currency": "EUR"},
                    }
                ]
            },
        )
    )
    options = make_client().search_alternatives("NCE", "CDG", date(2026, 7, 10))
    assert len(options) == 1
    assert options[0].price_total == 96.0
    assert options[0].seats_available == 5
