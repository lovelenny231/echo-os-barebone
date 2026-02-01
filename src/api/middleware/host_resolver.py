"""
ECHO OS Barebone: Host-based tenant resolution middleware.

Resolves tenant from Host header for multi-tenant URL structure:
  {tenant_slug}.{BASE_DOMAIN}/{client_slug} -> tenant_id, client_id

Example:
  Host: tenant1.example.com
  Path: /client1
  -> request.state.tenant_slug = "tenant1"
  -> request.state.client_slug = "client1" (from path)
"""

import os
import re
import logging
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# Get base domain from environment
BASE_DOMAIN = os.getenv("BASE_DOMAIN", "example.com")

# Build pattern dynamically from BASE_DOMAIN
# Escape dots in domain for regex
escaped_domain = BASE_DOMAIN.replace(".", r"\.")
HOST_PATTERN = re.compile(
    rf"^([a-z0-9][a-z0-9-]*[a-z0-9]?)\.{escaped_domain}$",
    re.IGNORECASE
)

# Reserved subdomains that should not be treated as tenant slugs
RESERVED_SUBDOMAINS = frozenset([
    "www",
    "api",
    "admin",
    "client",
    "office",
    "dev",
    "staging",
    "test",
])


class HostResolverMiddleware(BaseHTTPMiddleware):
    """Middleware to resolve tenant_slug from Host header.

    Sets request.state.tenant_slug if a valid tenant subdomain is detected.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request and resolve tenant from Host header.

        Priority: X-Forwarded-Host > Host
        """
        x_forwarded_host = request.headers.get("x-forwarded-host", "")
        host = request.headers.get("host", "")

        effective_host = x_forwarded_host or host
        tenant_slug = self._extract_tenant_slug(effective_host)

        if x_forwarded_host:
            logger.debug(f"Using X-Forwarded-Host: {x_forwarded_host} (Host: {host})")

        if tenant_slug:
            request.state.tenant_slug = tenant_slug
            logger.debug(f"Resolved tenant_slug from host: {tenant_slug} (host={host})")
        else:
            request.state.tenant_slug = None

        return await call_next(request)

    def _extract_tenant_slug(self, host: str) -> Optional[str]:
        """Extract tenant_slug from host header.

        Args:
            host: Host header value (e.g., "tenant1.example.com:443")

        Returns:
            tenant_slug if valid subdomain, None otherwise
        """
        # Remove port if present
        if ":" in host:
            host = host.split(":")[0]

        # Match against pattern
        match = HOST_PATTERN.match(host)
        if not match:
            return None

        subdomain = match.group(1).lower()

        # Check reserved subdomains
        if subdomain in RESERVED_SUBDOMAINS:
            logger.debug(f"Reserved subdomain ignored: {subdomain}")
            return None

        return subdomain


def get_tenant_slug_from_request(request: Request) -> Optional[str]:
    """Helper function to get tenant_slug from request state.

    Args:
        request: Starlette/FastAPI Request object

    Returns:
        tenant_slug if resolved, None otherwise
    """
    return getattr(request.state, "tenant_slug", None)
