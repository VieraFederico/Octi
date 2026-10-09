"""Check that every service Octi depends on is set up correctly.

Run from the repository root:  python -m scripts.check_services

Prints one line per check (`OK`, `FAIL: <reason>` or `skipped (<reason>)`) and exits non-zero if any
check failed (FR-015 … FR-018). It makes one real chat call and one real embedding call.
"""

import sys
from collections.abc import Callable

from services.health import Clients, run_checks
from services.logging_setup import configure_logging
from services.settings import Settings, get_settings


def main(load_settings: Callable[[], Settings] = get_settings, clients: Clients = Clients()) -> int:
    """Run the checks, print one line each, return the exit code. Tests pass fake settings and clients."""

    def load_settings_and_configure_logging() -> Settings:
        settings = load_settings()
        configure_logging(settings)
        return settings

    results = run_checks(load_settings_and_configure_logging, clients)
    for result in results:
        print(result.line())
    return 1 if any(result.status == "FAIL" for result in results) else 0


if __name__ == "__main__":
    sys.exit(main())
