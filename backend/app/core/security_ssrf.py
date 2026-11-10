"""SSRF (Server-Side Request Forgery) defense utilities for URL validation and fetching."""
import ipaddress
import logging
import socket
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class SSRFValidationError(ValueError):
    """Raised when a URL targets private, loopback, cloud metadata, or internal networks."""
    pass


FORBIDDEN_HOSTNAMES = {
    "localhost",
    "127.0.0.1",
    "::1",
    "0.0.0.0",
    "metadata.google.internal",
    "instance-data",
}


def validate_url_safe(url: str) -> str:
    """Validate that a URL uses http/https and does not resolve to private, loopback, or metadata IPs.

    Args:
        url: The candidate URL string.

    Returns:
        The validated clean URL string.

    Raises:
        SSRFValidationError: If scheme is unsupported, hostname is missing, or IP is private/local.
    """
    clean_url = str(url).strip()
    if not clean_url:
        raise SSRFValidationError("URL cannot be empty")

    try:
        parsed = urlparse(clean_url)
    except Exception as e:
        raise SSRFValidationError(f"Invalid URL structure: {e}") from e

    # 1. Scheme check: only http and https allowed
    if parsed.scheme.lower() not in {"http", "https"}:
        raise SSRFValidationError(
            f"Unsupported URL scheme '{parsed.scheme}'. Only HTTP and HTTPS are permitted."
        )

    # 2. Hostname check
    hostname = parsed.hostname
    if not hostname:
        raise SSRFValidationError("URL must include a valid hostname")

    hostname_lower = hostname.lower()

    if hostname_lower in FORBIDDEN_HOSTNAMES:
        raise SSRFValidationError(f"Access to internal host '{hostname}' is forbidden.")

    if hostname_lower.endswith(".local") or hostname_lower.endswith(".internal"):
        raise SSRFValidationError(f"Access to internal network domain '{hostname}' is forbidden.")

    # 3. Resolve DNS and inspect every IP address
    try:
        # Check if the hostname is already an IP address string
        try:
            ip = ipaddress.ip_address(hostname_lower)
            ip_candidates = [ip]
        except ValueError:
            # Resolve DNS
            addr_info = socket.getaddrinfo(hostname, None)
            ip_candidates = []
            for item in addr_info:
                ip_str = item[4][0]
                ip_candidates.append(ipaddress.ip_address(ip_str))
    except (socket.gaierror, socket.herror) as e:
        raise SSRFValidationError(f"Unable to resolve host '{hostname}': {e}") from e
    except Exception as e:
        raise SSRFValidationError(f"Host validation error for '{hostname}': {e}") from e

    if not ip_candidates:
        raise SSRFValidationError(f"Could not resolve any IP addresses for host '{hostname}'")

    for ip in ip_candidates:
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            logger.warning(
                "SSRF attempt blocked: hostname '%s' resolved to restricted IP %s",
                hostname,
                ip,
            )
            raise SSRFValidationError(
                f"Access to private, loopback, or metadata address ({ip}) is strictly forbidden."
            )

    return clean_url
