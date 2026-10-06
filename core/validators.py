"""URL and target validation.

Validation is intentionally strict and fails closed: anything that is not an
unambiguous public HTTP/HTTPS target is rejected unless private targets have
been explicitly enabled for local development.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

ALLOWED_SCHEMES = {"http", "https"}

# Hostnames that always resolve to the local machine.
_LOCAL_HOSTNAMES = {"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"}


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of validating a target URL."""

    ok: bool
    message: str = ""
    normalized_url: str = ""


def is_private_address(host: str) -> bool:
    """Return True if ``host`` is a loopback/private/internal/reserved address.

    Handles both literal IP addresses (v4 and v6) and hostnames. Hostnames are
    resolved via DNS; if resolution fails the host is treated as private
    (fail closed) so an unresolvable internal name is never silently allowed.
    """
    host = host.strip().lower()
    if not host:
        return True
    if host in _LOCAL_HOSTNAMES:
        return True

    # Direct IP literal?
    try:
        ip = ipaddress.ip_address(host)
        return _ip_is_private(ip)
    except ValueError:
        pass

    # Resolve the hostname and reject if *any* resolved address is private.
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        # Cannot resolve -> treat as non-public / unsafe.
        return True

    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr.split("%")[0])  # strip zone id
        except ValueError:
            continue
        if _ip_is_private(ip):
            return True
    return False


def _ip_is_private(ip: ipaddress._BaseAddress) -> bool:
    """Classify an IP address as non-public."""
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def validate_url(url: str, allow_private: bool = False) -> ValidationResult:
    """Validate a target URL.

    Args:
        url: The raw URL entered by the operator.
        allow_private: When True, localhost/private/internal targets are
            permitted (intended for local development only).

    Returns:
        A :class:`ValidationResult`. ``ok`` is False with a human-readable
        ``message`` when the URL is rejected.
    """
    if url is None or not url.strip():
        return ValidationResult(False, "Please enter a target URL.")

    candidate = url.strip()
    parsed = urlparse(candidate)

    if not parsed.scheme:
        return ValidationResult(
            False, "Missing protocol. The URL must start with http:// or https://."
        )

    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        return ValidationResult(
            False, "Only HTTP and HTTPS URLs are supported."
        )

    if not parsed.hostname:
        return ValidationResult(False, "Malformed URL: no host found.")

    if parsed.port is not None and not (0 < parsed.port <= 65535):
        return ValidationResult(False, f"Invalid port: {parsed.port}.")

    if not allow_private and is_private_address(parsed.hostname):
        return ValidationResult(
            False,
            "Localhost, private, and internal addresses are blocked. Enable "
            "'Allow private targets' in Settings for local development testing.",
        )

    # Normalize: drop any fragment, keep scheme/host/port/path/query.
    normalized = parsed._replace(fragment="").geturl()
    return ValidationResult(True, "Valid target URL.", normalized)
