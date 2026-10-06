"""Reusable load-test scenario definitions.

Scenarios are plain data so they can be shared between the in-process asyncio
engine (default, local mode) and the Locust engine (optional, distributed
mode). Keeping them here avoids duplicating target/path configuration.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class Scenario:
    """A named collection of authorized GET/HEAD paths against one base URL."""

    name: str
    base_url: str
    paths: list[str] = field(default_factory=lambda: ["/"])
    method: str = "GET"

    def __post_init__(self) -> None:
        if self.method.upper() not in {"GET", "HEAD"}:
            raise ValueError("Only GET and HEAD are supported.")
        self.method = self.method.upper()
        self.paths = [p if p.startswith("/") else "/" + p for p in self.paths] or ["/"]


def scenario_from_env() -> Scenario:
    """Build a scenario from environment variables (used by Locust workers).

    Environment variables:
        LT_TARGET_URL   Base URL of the authorized target (required).
        LT_PATHS        Comma-separated list of paths (default "/").
        LT_METHOD       GET or HEAD (default GET).
    """
    base_url = os.getenv("LT_TARGET_URL")
    if not base_url:
        raise RuntimeError(
            "LT_TARGET_URL is required. Set it to the authorized target base URL."
        )
    raw_paths = os.getenv("LT_PATHS", "/")
    paths = [p.strip() for p in raw_paths.split(",") if p.strip()]
    return Scenario(
        name="env",
        base_url=base_url,
        paths=paths or ["/"],
        method=os.getenv("LT_METHOD", "GET"),
    )


# A conservative default used for documentation/examples.
DEFAULT_SCENARIO = Scenario(
    name="homepage",
    base_url="https://example.com",
    paths=["/", "/about", "/contact", "/products"],
)
