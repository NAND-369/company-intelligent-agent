"""URL security and SSRF validation utility."""

import ipaddress
import logging
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Cloud metadata, link-local, and reserved networks
FORBIDDEN_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),       # IPv4 Loopback
    ipaddress.ip_network("10.0.0.0/8"),        # Private network RFC 1918
    ipaddress.ip_network("172.16.0.0/12"),     # Private network RFC 1918
    ipaddress.ip_network("192.168.0.0/16"),    # Private network RFC 1918
    ipaddress.ip_network("169.254.0.0/16"),    # IPv4 Link-Local / Cloud Metadata (169.254.169.254)
    ipaddress.ip_network("0.0.0.0/8"),         # Current network
    ipaddress.ip_network("::1/128"),           # IPv6 Loopback
    ipaddress.ip_network("fe80::/10"),         # IPv6 Link-Local
    ipaddress.ip_network("fc00::/7"),          # IPv6 Unique Local
]

FORBIDDEN_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "127.0.0.1",
    "::1",
    "metadata.google.internal",
    "metadata",
    "instance-data",
}


def validate_target_url(url: str, allow_file_scheme: bool = False) -> tuple[bool, Optional[str]]:
    """
    Validate that a URL is well-formed, uses http/https (or file:// if explicitly allowed for local testing),
    and does not target internal/private networks (SSRF defense).
    Returns (is_valid, error_reason).
    """
    if not url or not isinstance(url, str):
        return False, "URL cannot be empty."

    url_clean = url.strip()
    try:
        parsed = urlparse(url_clean)
    except Exception as exc:
        return False, f"Malformed URL syntax: {exc!s}"

    # 1. Scheme validation (permit file:// for offline testing fixtures if enabled)
    if allow_file_scheme and parsed.scheme.lower() == "file":
        return True, None

    if parsed.scheme.lower() not in ("http", "https"):
        return False, f"Unsupported URL scheme '{parsed.scheme}'. Only http and https are permitted."

    # 2. Enforce presence of valid hostname
    hostname = parsed.hostname
    if not hostname:
        return False, "URL must include a valid hostname."

    hostname_lower = hostname.lower().strip()

    # 3. Check forbidden hostname aliases
    if hostname_lower in FORBIDDEN_HOSTNAMES:
        return False, f"Access to internal/restricted host '{hostname}' is forbidden (SSRF protection)."

    # 4. Check literal IP addresses against private and cloud metadata networks
    try:
        ip = ipaddress.ip_address(hostname_lower)
        for net in FORBIDDEN_NETWORKS:
            if ip in net:
                return False, f"Access to internal IP address '{ip}' is forbidden (SSRF protection)."
    except ValueError:
        # Hostname is a domain name (not a raw IP literal)
        pass

    return True, None
