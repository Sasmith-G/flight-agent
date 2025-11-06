"""Notification channels. Console by default; Twilio (SMS/WhatsApp) when configured."""

from __future__ import annotations

from abc import ABC, abstractmethod

import httpx
from rich.console import Console
from rich.panel import Panel

from .config import Settings, get_settings


class Notifier(ABC):
    @abstractmethod
    def send(self, message: str) -> str:
        """Send the message; returns a delivery reference."""


class ConsoleNotifier(Notifier):
    def __init__(self, console: Console | None = None):
        self.console = console or Console()

    def send(self, message: str) -> str:
        self.console.print(
            Panel(message, title="📱 Passenger notification", border_style="green", expand=False)
        )
        return "console"


class TwilioNotifier(Notifier):
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def send(self, message: str) -> str:
        sid = self.settings.twilio_account_sid
        resp = httpx.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
            auth=(sid, self.settings.twilio_auth_token),
            data={
                "From": self.settings.twilio_from,
                "To": self.settings.twilio_to,
                "Body": message,
            },
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json().get("sid", "unknown")


def get_notifier(settings: Settings | None = None) -> Notifier:
    settings = settings or get_settings()
    if settings.twilio_account_sid and settings.twilio_auth_token:
        return TwilioNotifier(settings)
    return ConsoleNotifier()
