"""Render the demo output to SVG for screenshots/docs (offline, mock mode)."""

import sys

from rich.console import Console

import disruption_agent.cli as cli
import disruption_agent.notify as notify

recorder = Console(record=True, width=88, force_terminal=True)
cli.console = recorder
notify.ConsoleNotifier.__init__ = lambda self, console=None: setattr(self, "console", recorder)

cli.demo()
recorder.save_svg(sys.argv[1], title="disruption-agent demo")
print(f"saved {sys.argv[1]}")
