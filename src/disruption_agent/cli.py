"""Command-line interface.

    disruption-agent monitor AF 1234 --date 2026-07-10          # live or mock per .env
    disruption-agent demo                                        # guided mock demo
"""

from __future__ import annotations

from datetime import date, timedelta

import typer
from rich.console import Console
from rich.table import Table

from .agent import run_agent
from .config import get_settings
from .models import DisruptionType

app = typer.Typer(add_completion=False, help="Travel-disruption agent on Amadeus APIs.")
console = Console()


def _print_run(result: dict) -> None:
    status = result.get("status")
    event = result.get("event")

    table = Table(title="Agent trace", show_header=False, border_style="dim")
    for i, step in enumerate(result.get("trace", []), start=1):
        table.add_row(f"[bold]{i}[/bold]", step)
    console.print(table)

    if status is None:
        console.print("[red]Flight not found — nothing to do.[/red]")
        return
    if event and event.type == DisruptionType.NONE:
        console.print(
            f"[green]✅ {status.flight_designator} is on time "
            f"(predicted >2h-delay probability: "
            f"{(event.delay_probability or 0):.0%}). No action needed.[/green]"
        )


@app.command()
def monitor(
    carrier: str = typer.Argument(..., help="Carrier code, e.g. AF"),
    flight_number: str = typer.Argument(..., help="Flight number, e.g. 1234"),
    departure_date: str = typer.Option(
        None, "--date", "-d", help="YYYY-MM-DD (default: tomorrow)"
    ),
    scenario: str = typer.Option(
        "delay", "--scenario", "-s", help="Mock scenario: delay | cancellation | on_time"
    ),
):
    """Check one flight and handle any disruption end-to-end."""
    when = date.fromisoformat(departure_date) if departure_date else date.today() + timedelta(1)
    settings = get_settings()
    console.rule(
        f"[bold]Disruption agent[/bold] · {carrier}{flight_number} · {when} · "
        f"mode={settings.agent_mode}"
    )
    result = run_agent(carrier, flight_number, when, scenario=scenario)
    _print_run(result)


@app.command()
def demo():
    """Run the three mock scenarios back to back (no credentials required)."""
    when = date.today() + timedelta(1)
    for scenario in ("on_time", "delay", "cancellation"):
        console.rule(f"[bold cyan]Scenario: {scenario}[/bold cyan]")
        result = run_agent("AF", "1234", when, scenario=scenario)
        _print_run(result)
        console.print()


if __name__ == "__main__":
    app()
