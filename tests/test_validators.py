"""Tests for URL validation and private-address detection."""

from __future__ import annotations

import pytest

from core.validators import is_private_address, split_target, validate_url


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://example.com",
        "https://example.com/path?q=1",
        "https://example.com:8443/a/b",
    ],
)
def test_valid_public_urls(url: str) -> None:
    result = validate_url(url, allow_private=False)
    assert result.ok, result.message
    assert result.normalized_url


@pytest.mark.parametrize(
    "url, fragment",
    [
        ("", "enter a target URL"),
        ("   ", "enter a target URL"),
        ("ftp://example.com", "Only HTTP and HTTPS"),
        ("file:///etc/passwd", "Only HTTP and HTTPS"),
        ("ws://example.com", "Only HTTP and HTTPS"),
        ("http://", "no host"),
    ],
)
def test_invalid_urls(url: str, fragment: str) -> None:
    result = validate_url(url, allow_private=False)
    assert not result.ok
    assert fragment.lower() in result.message.lower()


def test_missing_scheme_defaults_to_https() -> None:
    result = validate_url("example.com/page", allow_private=True)
    assert result.ok
    assert result.normalized_url == "https://example.com/page"


def test_split_target_moves_page_into_paths() -> None:
    assert split_target("https://a.com/blog?x=1", ["/"]) == ("https://a.com", ["/blog?x=1"])
    assert split_target("https://a.com/", ["/", "/b"]) == ("https://a.com", ["/", "/b"])


def test_fragment_is_stripped() -> None:
    result = validate_url("https://example.com/p#section", allow_private=True)
    assert result.ok
    assert "#" not in result.normalized_url


@pytest.mark.parametrize(
    "host",
    [
        "127.0.0.1",
        "localhost",
        "0.0.0.0",
        "10.0.0.5",
        "192.168.1.1",
        "172.16.0.1",
        "169.254.1.1",  # link-local
        "::1",
        "fe80::1",  # link-local v6
    ],
)
def test_private_addresses_detected(host: str) -> None:
    assert is_private_address(host) is True


@pytest.mark.parametrize("host", ["8.8.8.8", "1.1.1.1"])
def test_public_ip_addresses(host: str) -> None:
    assert is_private_address(host) is False


def test_unresolvable_host_is_private() -> None:
    # Fail closed: a name that cannot resolve must not be treated as public.
    assert is_private_address("this-host-does-not-exist.invalid") is True


def test_private_blocked_by_default_but_allowed_when_enabled() -> None:
    blocked = validate_url("http://127.0.0.1:8000", allow_private=False)
    assert not blocked.ok
    assert "private" in blocked.message.lower() or "localhost" in blocked.message.lower()

    allowed = validate_url("http://127.0.0.1:8000", allow_private=True)
    assert allowed.ok
