"""Application settings and hard safety caps.

Settings are layered: environment variables (loaded from a local ``.env`` via
python-dotenv) override the built-in defaults. Hard caps are deliberately *not*
user-editable from the UI — they are the outer safety envelope that keeps a
single laptop from being pointed at a target with unbounded load.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Load .env from the project root if present. Never fails if absent.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class Settings(BaseModel):
    """Runtime configuration with conservative, overridable defaults."""

    # ----- Hard safety caps (outer envelope; not editable from the UI) -----
    max_users_hard_cap: int = Field(
        default_factory=lambda: _env_int("LT_MAX_USERS_HARD_CAP", 50000),
        description="Absolute ceiling on virtual users for a single local run.",
    )
    max_duration_hard_cap_s: int = Field(
        default_factory=lambda: _env_int("LT_MAX_DURATION_HARD_CAP_S", 1800),
        description="Absolute ceiling on test duration (seconds).",
    )
    # Soft advisory: above this, a single machine is usually the bottleneck and
    # the distributed Locust cluster is the right tool. Not a hard limit — it
    # only drives a prominent warning in the UI.
    single_machine_recommended_max: int = Field(
        default_factory=lambda: _env_int("LT_SINGLE_MACHINE_RECOMMENDED_MAX", 2000),
        description="Advisory ceiling for realistic single-machine load generation.",
    )
    # Hard ceiling on the HTTP connection pool so very large VU counts cannot
    # exhaust file descriptors / sockets and crash the engine.
    max_connection_pool: int = Field(
        default_factory=lambda: _env_int("LT_MAX_CONNECTION_POOL", 10000),
        description="Upper bound on concurrent HTTP connections regardless of VUs.",
    )

    # ----- User-facing defaults (editable in the Settings page) -----
    default_max_users: int = Field(
        default_factory=lambda: _env_int("LT_DEFAULT_MAX_USERS", 500)
    )
    default_duration_s: int = Field(
        default_factory=lambda: _env_int("LT_DEFAULT_DURATION_S", 60)
    )
    default_spawn_rate: float = Field(
        default_factory=lambda: _env_float("LT_DEFAULT_SPAWN_RATE", 10.0)
    )
    default_timeout_s: float = Field(
        default_factory=lambda: _env_float("LT_DEFAULT_TIMEOUT_S", 10.0)
    )
    default_error_threshold_pct: float = Field(
        default_factory=lambda: _env_float("LT_DEFAULT_ERROR_THRESHOLD_PCT", 5.0)
    )
    default_p95_threshold_ms: float = Field(
        default_factory=lambda: _env_float("LT_DEFAULT_P95_THRESHOLD_MS", 3000.0)
    )

    # ----- Behaviour flags -----
    allow_private_targets: bool = Field(
        default_factory=lambda: _env_bool("LT_ALLOW_PRIVATE_TARGETS", False),
        description="Allow localhost/private targets by default (dev only).",
    )

    # ----- Storage -----
    database_path: str = Field(
        default_factory=lambda: os.getenv(
            "LT_DATABASE_PATH", str(_PROJECT_ROOT / "data" / "history.db")
        )
    )

    # ----- Identity -----
    user_agent: str = Field(
        default_factory=lambda: os.getenv(
            "LT_USER_AGENT", "authorized-load-tester/1.0 (+local)"
        )
    )

    def clamp_users(self, requested: int) -> int:
        """Clamp a requested user count to the hard cap."""
        return max(1, min(requested, self.max_users_hard_cap))

    def clamp_duration(self, requested: int) -> int:
        """Clamp a requested duration to the hard cap."""
        return max(1, min(requested, self.max_duration_hard_cap_s))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
