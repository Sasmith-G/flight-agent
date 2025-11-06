"""Clients for the Amadeus Self-Service APIs.

`LiveAmadeusClient` talks to the Amadeus test environment (OAuth2 client-credentials);
`MockAmadeusClient` replays realistic recorded fixtures so the full agent pipeline can
run — and be tested in CI — without network access or credentials.

Endpoints used:
  * On-Demand Flight Status   GET /v2/schedule/flights
  * Flight Delay Prediction   GET /v1/travel/predictions/flight-delay
  * Flight Offers Search      GET /v2/shopping/flight-offers
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta

import httpx

from ..config import Settings, get_settings
from ..models import FlightStatus, RebookingOption


class AmadeusClient(ABC):
    """Interface the agent depends on — swap live/mock without touching the graph."""

    @abstractmethod
    def flight_status(
        self, carrier: str, number: str, departure_date: date
    ) -> FlightStatus | None: ...

    @abstractmethod
    def delay_prediction(
        self, origin: str, destination: str, departure: datetime, carrier: str, number: str
    ) -> float | None:
        """Probability that the flight is delayed more than 2 hours."""

    @abstractmethod
    def search_alternatives(
        self, origin: str, destination: str, departure_date: date, max_results: int = 5
    ) -> list[RebookingOption]: ...


class LiveAmadeusClient(AmadeusClient):
    """Amadeus Self-Service client with OAuth2 token caching and retry-aware requests."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._token: str | None = None
        self._token_expiry: float = 0.0
        self._http = httpx.Client(base_url=self.settings.amadeus_base_url, timeout=20)

    # -- auth ------------------------------------------------------------

    def _access_token(self) -> str:
        if self._token and time.time() < self._token_expiry - 60:
            return self._token
        resp = self._http.post(
            "/v1/security/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.settings.amadeus_client_id,
                "client_secret": self.settings.amadeus_client_secret,
            },
        )
        resp.raise_for_status()
        payload = resp.json()
        self._token = payload["access_token"]
        self._token_expiry = time.time() + payload.get("expires_in", 1799)
        return self._token

    def _get(self, path: str, params: dict) -> dict:
        resp = self._http.get(
            path, params=params, headers={"Authorization": f"Bearer {self._access_token()}"}
        )
        resp.raise_for_status()
        return resp.json()

    # -- endpoints --------------------------------------------------------

    def flight_status(self, carrier: str, number: str, departure_date: date) -> FlightStatus | None:
        data = self._get(
            "/v2/schedule/flights",
            {
                "carrierCode": carrier,
                "flightNumber": number,
                "scheduledDepartureDate": departure_date.isoformat(),
            },
        ).get("data", [])
        if not data:
            return None
        flight = data[0]
        dep = flight["flightPoints"][0]["departure"]["timings"]
        arr = flight["flightPoints"][-1]["arrival"]["timings"]

        def timing(timings: list[dict], qualifier: str) -> datetime | None:
            for t in timings:
                if t["qualifier"] == qualifier:
                    return datetime.fromisoformat(t["value"])
            return None

        scheduled_dep = timing(dep, "STD")
        scheduled_arr = timing(arr, "STA")
        if scheduled_dep is None or scheduled_arr is None:
            return None
        return FlightStatus(
            carrier_code=carrier,
            flight_number=number,
            departure_iata=flight["flightPoints"][0]["iataCode"],
            arrival_iata=flight["flightPoints"][-1]["iataCode"],
            scheduled_departure=scheduled_dep,
            estimated_departure=timing(dep, "ETD"),
            scheduled_arrival=scheduled_arr,
            estimated_arrival=timing(arr, "ETA"),
        )

    def delay_prediction(
        self, origin: str, destination: str, departure: datetime, carrier: str, number: str
    ) -> float | None:
        try:
            data = self._get(
                "/v1/travel/predictions/flight-delay",
                {
                    "originLocationCode": origin,
                    "destinationLocationCode": destination,
                    "departureDate": departure.date().isoformat(),
                    "departureTime": departure.strftime("%H:%M:%S"),
                    "arrivalDate": departure.date().isoformat(),
                    "arrivalTime": (departure + timedelta(hours=2)).strftime("%H:%M:%S"),
                    "aircraftCode": "320",
                    "carrierCode": carrier,
                    "flightNumber": number,
                    "duration": "PT2H",
                },
            ).get("data", [])
        except httpx.HTTPStatusError:
            return None  # prediction is best-effort; the agent degrades gracefully
        for bucket in data:
            if bucket.get("result") == "OVER_120_MINUTES":
                return float(bucket.get("probability", 0.0))
        return 0.0

    def search_alternatives(
        self, origin: str, destination: str, departure_date: date, max_results: int = 5
    ) -> list[RebookingOption]:
        data = self._get(
            "/v2/shopping/flight-offers",
            {
                "originLocationCode": origin,
                "destinationLocationCode": destination,
                "departureDate": departure_date.isoformat(),
                "adults": 1,
                "nonStop": "true",
                "max": max_results,
            },
        ).get("data", [])
        options: list[RebookingOption] = []
        for offer in data:
            segment = offer["itineraries"][0]["segments"][0]
            options.append(
                RebookingOption(
                    carrier_code=segment["carrierCode"],
                    flight_number=segment["number"],
                    departure_iata=segment["departure"]["iataCode"],
                    arrival_iata=segment["arrival"]["iataCode"],
                    departure=datetime.fromisoformat(segment["departure"]["at"]),
                    arrival=datetime.fromisoformat(segment["arrival"]["at"]),
                    price_total=float(offer["price"]["grandTotal"]),
                    currency=offer["price"]["currency"],
                    seats_available=offer.get("numberOfBookableSeats"),
                )
            )
        return options


class MockAmadeusClient(AmadeusClient):
    """Replays a realistic disruption scenario: AF1234 NCE->CDG delayed 3h10.

    Fixture values mirror the shape and magnitude of real Amadeus test-environment
    responses, so switching AGENT_MODE=live changes the data source, not the behaviour.
    """

    def __init__(self, scenario: str = "delay"):
        self.scenario = scenario

    def flight_status(self, carrier: str, number: str, departure_date: date) -> FlightStatus | None:
        scheduled_dep = datetime.combine(departure_date, datetime.min.time()).replace(hour=14)
        scheduled_arr = scheduled_dep + timedelta(hours=1, minutes=35)
        if self.scenario == "cancellation":
            return FlightStatus(
                carrier_code=carrier,
                flight_number=number,
                departure_iata="NCE",
                arrival_iata="CDG",
                scheduled_departure=scheduled_dep,
                scheduled_arrival=scheduled_arr,
                cancelled=True,
            )
        if self.scenario == "on_time":
            return FlightStatus(
                carrier_code=carrier,
                flight_number=number,
                departure_iata="NCE",
                arrival_iata="CDG",
                scheduled_departure=scheduled_dep,
                estimated_departure=scheduled_dep,
                scheduled_arrival=scheduled_arr,
                estimated_arrival=scheduled_arr,
            )
        delay = timedelta(hours=3, minutes=10)
        return FlightStatus(
            carrier_code=carrier,
            flight_number=number,
            departure_iata="NCE",
            arrival_iata="CDG",
            scheduled_departure=scheduled_dep,
            estimated_departure=scheduled_dep + delay,
            scheduled_arrival=scheduled_arr,
            estimated_arrival=scheduled_arr + delay,
        )

    def delay_prediction(
        self, origin: str, destination: str, departure: datetime, carrier: str, number: str
    ) -> float | None:
        return {"delay": 0.82, "cancellation": None, "on_time": 0.04}.get(self.scenario, 0.82)

    def search_alternatives(
        self, origin: str, destination: str, departure_date: date, max_results: int = 5
    ) -> list[RebookingOption]:
        base = datetime.combine(departure_date, datetime.min.time())
        fixtures = [
            ("AF", "6205", 16, 0, 96.0, 5),
            ("AF", "6240", 18, 30, 112.0, 9),
            ("A5", "3766", 19, 15, 88.0, 3),
        ]
        return [
            RebookingOption(
                carrier_code=c,
                flight_number=n,
                departure_iata=origin,
                arrival_iata=destination,
                departure=base.replace(hour=h, minute=m),
                arrival=base.replace(hour=h, minute=m) + timedelta(hours=1, minutes=35),
                price_total=price,
                seats_available=seats,
            )
            for c, n, h, m, price, seats in fixtures[:max_results]
        ]


def get_client(settings: Settings | None = None, scenario: str = "delay") -> AmadeusClient:
    settings = settings or get_settings()
    if settings.live:
        return LiveAmadeusClient(settings)
    return MockAmadeusClient(scenario=scenario)
