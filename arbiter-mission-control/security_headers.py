"""HTTP security headers applied to every response by the mission-control server.

The CSP allows inline scripts/styles (the dashboard is dense with inline
onclick= / style= attributes) and the jsdelivr CDN (Chart.js, topojson),
but locks connect-src to 'self' so an XSS-injected payload cannot exfiltrate
the API key from localStorage to an external origin. Referrer-Policy is
no-referrer to plug the ?api_key= query-string leak path.
"""
from __future__ import annotations

_CSP_DIRECTIVES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("default-src", ("'self'",)),
    ("script-src", ("'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net")),
    ("style-src", ("'self'", "'unsafe-inline'")),
    ("img-src", ("'self'", "data:", "blob:")),
    ("font-src", ("'self'", "data:")),
    ("connect-src", ("'self'",)),
    ("media-src", ("'self'", "blob:", "data:")),
    ("object-src", ("'none'",)),
    ("base-uri", ("'self'",)),
    ("form-action", ("'self'",)),
    ("frame-ancestors", ("'none'",)),
)


def _build_csp() -> str:
    parts = [f"{name} {' '.join(sources)}" for name, sources in _CSP_DIRECTIVES]
    return "; ".join(parts)


def build_security_headers() -> dict[str, str]:
    return {
        "Content-Security-Policy": _build_csp(),
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Permissions-Policy": (
            "geolocation=(), camera=(), microphone=(self), "
            "payment=(), usb=(), magnetometer=(), gyroscope=(), "
            "accelerometer=(), fullscreen=(self)"
        ),
        "Cross-Origin-Opener-Policy": "same-origin",
        "Cross-Origin-Resource-Policy": "same-origin",
    }


def parse_csp(value: str) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for raw in value.split(";"):
        directive = raw.strip()
        if not directive:
            continue
        parts = directive.split()
        name, sources = parts[0], parts[1:]
        result[name] = sources
    return result
