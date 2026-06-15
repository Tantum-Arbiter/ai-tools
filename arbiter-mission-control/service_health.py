"""
Service Health Monitor — checks public status pages for key services.
Returns uptime/status for cloud, AI, comms, gaming, and email services.
All endpoints are public — no auth required.
Focus: UK-based impact.
"""
import logging
from datetime import datetime, timedelta

import os

import httpx

log = logging.getLogger(__name__)

# Atlassian Statuspage-based services expose /api/v2/status.json
# and /api/v2/components.json publicly.
SERVICES = {
    "cloudflare": {
        "name": "Cloudflare",
        "icon": "🛡",
        "status_url": "https://www.cloudflarestatus.com/api/v2/status.json",
        "components_url": "https://www.cloudflarestatus.com/api/v2/components.json",
        "type": "statuspage",
    },
    "openai": {
        "name": "OpenAI",
        "icon": "🤖",
        "status_url": "https://status.openai.com/api/v2/status.json",
        "components_url": "https://status.openai.com/api/v2/components.json",
        "type": "statuspage",
    },
    "anthropic": {
        "name": "Claude",
        "icon": "🧠",
        "status_url": "https://status.anthropic.com/api/v2/status.json",
        "components_url": "https://status.anthropic.com/api/v2/components.json",
        "type": "statuspage",
    },
    "gcp": {
        "name": "Google Cloud",
        "icon": "☁",
        "status_url": "https://status.cloud.google.com/incidents.json",
        "components_url": None,
        "type": "gcp",
    },
    "aws": {
        "name": "AWS",
        "icon": "📦",
        "status_url": "https://health.aws.amazon.com/health/status",
        "components_url": None,
        "type": "aws",
    },
    "github": {
        "name": "GitHub",
        "icon": "🐙",
        "status_url": "https://www.githubstatus.com/api/v2/status.json",
        "components_url": "https://www.githubstatus.com/api/v2/components.json",
        "type": "statuspage",
    },
    "whatsapp": {
        "name": "WhatsApp",
        "icon": "💬",
        "status_url": "https://web.whatsapp.com",
        "components_url": None,
        "type": "ping",
    },
    "gmail": {
        "name": "Gmail",
        "icon": "📧",
        "status_url": "https://www.google.com/appsstatus/dashboard/incidents.json",
        "components_url": None,
        "type": "google_workspace",
    },
    "outlook": {
        "name": "Outlook",
        "icon": "📮",
        "status_url": "https://portal.office.com/servicestatus",
        "components_url": None,
        "type": "ping",
    },
    "xbox": {
        "name": "Xbox Live",
        "icon": "🎮",
        "status_url": "https://xnotify.xboxlive.com/servicestatusv6/GB/en-GB",
        "components_url": None,
        "type": "xbox",
    },
    "playstation": {
        "name": "PlayStation",
        "icon": "🕹",
        "status_url": "https://status.playstation.com/en-gb/",
        "components_url": None,
        "type": "ping",
    },
    "apple_login": {
        "name": "Apple Login",
        "icon": "",
        "status_url": "https://www.apple.com/uk/support/systemstatus/",
        "components_url": None,
        "type": "apple_system",
    },
    "google_login": {
        "name": "Google Login",
        "icon": "G",
        "status_url": "https://www.google.com/appsstatus/dashboard/incidents.json",
        "components_url": None,
        "type": "google_identity",
    },
    "expo_eas": {
        "name": "EAS Build",
        "icon": "",
        "status_url": "https://status.expo.dev/api/v2/status.json",
        "components_url": "https://status.expo.dev/api/v2/components.json",
        "type": "statuspage",
    },
    "comfyui": {
        "name": "ComfyUI",
        "icon": "🖥",
        "status_url": None,
        "components_url": None,
        "type": "comfyui_local",
    },
}

# Map Statuspage indicator → our status
_SP_MAP = {
    "none": "operational",
    "minor": "degraded",
    "major": "major_outage",
    "critical": "major_outage",
    "maintenance": "maintenance",
}


class ServiceHealthMonitor:
    def __init__(self, ttl: int = 120):
        self._ttl = ttl
        self._cache = None
        self._cache_time = None

    def summary(self) -> list[dict]:
        now = datetime.utcnow()
        if self._cache and self._cache_time and (now - self._cache_time).total_seconds() < self._ttl:
            return self._cache
        results = []
        for svc_id, svc in SERVICES.items():
            results.append(self._check(svc_id, svc))
        self._cache = results
        self._cache_time = now
        return results

    def _check(self, svc_id: str, svc: dict) -> dict:
        base = {
            "id": svc_id,
            "name": svc["name"],
            "icon": svc["icon"],
            "status": "operational",
            "description": "All systems operational",
            "components": [],
        }
        try:
            stype = svc.get("type", "statuspage")
            if stype == "statuspage":
                return self._check_statuspage(svc, base)
            elif stype == "gcp":
                return self._check_gcp(svc, base)
            elif stype == "aws":
                return self._check_aws(svc, base)
            elif stype == "google_workspace":
                return self._check_google_workspace(svc, base)
            elif stype == "xbox":
                return self._check_xbox(svc, base)
            elif stype == "ping":
                return self._check_ping(svc, base)
            elif stype == "apple_system":
                return self._check_apple_system(svc, base)
            elif stype == "google_identity":
                return self._check_google_identity(svc, base)
            elif stype == "comfyui_local":
                return self._check_comfyui_local(svc, base)
            return base
        except Exception as e:
            log.debug("Health check failed for %s: %s", svc_id, e)
            base["status"] = "unknown"
            base["description"] = "Status check failed"
            return base

    def _check_statuspage(self, svc: dict, base: dict) -> dict:
        resp = httpx.get(svc["status_url"], timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            indicator = data.get("status", {}).get("indicator", "none")
            desc = data.get("status", {}).get("description", "")
            base["status"] = _SP_MAP.get(indicator, "operational")
            base["description"] = desc
        # Fetch active incidents with impact descriptions
        incidents_url = svc["status_url"].replace("/status.json", "/incidents/unresolved.json")
        try:
            ir = httpx.get(incidents_url, timeout=8)
            if ir.status_code == 200:
                incidents = ir.json().get("incidents", [])
                if incidents:
                    active_incidents = []
                    for inc in incidents[:5]:
                        impact = inc.get("impact", "none")
                        name = inc.get("name", "")
                        affected = [c.get("name", "") for c in inc.get("components", [])]
                        updates = inc.get("incident_updates", [])
                        latest_update = updates[0].get("body", "") if updates else ""
                        active_incidents.append({
                            "name": name,
                            "impact": impact,  # none|minor|major|critical
                            "affected_components": affected,
                            "latest_update": latest_update[:200],
                            "created_at": inc.get("created_at", ""),
                        })
                    base["incidents"] = active_incidents
                    # Upgrade status based on worst incident impact
                    worst = max((i["impact"] for i in active_incidents),
                                key=lambda x: {"critical": 3, "major": 2, "minor": 1}.get(x, 0))
                    if worst in ("critical", "major"):
                        base["status"] = "major_outage"
                    elif worst == "minor" and base["status"] == "operational":
                        base["status"] = "degraded"
        except Exception:
            pass
        if svc.get("components_url"):
            try:
                cr = httpx.get(svc["components_url"], timeout=8)
                if cr.status_code == 200:
                    comps = cr.json().get("components", [])
                    base["components"] = [
                        {"name": c["name"], "status": c.get("status", "operational")}
                        for c in comps if not c.get("group") and c.get("name")
                    ][:8]
            except Exception:
                pass
        return base

    def _check_gcp(self, svc: dict, base: dict) -> dict:
        resp = httpx.get(svc["status_url"], timeout=8,
                         headers={"Accept": "application/json"})
        if resp.status_code != 200:
            return base
        incidents = resp.json()
        # Filter for active incidents (not resolved)
        active = [i for i in incidents
                  if i.get("most-recent-update", {}).get("status", "").upper()
                  not in ("AVAILABLE",)]
        # Filter for UK/EU-relevant or global incidents
        eu = [i for i in active
              if any(loc.lower() in str(i).lower()
                     for loc in ("europe", "eu-west", "london", "global"))]
        if not eu:
            return base
        sev = max((i.get("severity", "low") for i in eu),
                  key=lambda s: {"high": 2, "medium": 1}.get(s, 0))
        base["status"] = "major_outage" if sev == "high" else "degraded"
        # Extract incident details with affected services and impact
        gcp_incidents = []
        for inc in eu[:5]:
            affected_products = []
            for prod in inc.get("affected_products", []):
                affected_products.append(prod.get("title", ""))
            updates = inc.get("updates", [])
            latest = updates[0] if updates else inc.get("most-recent-update", {})
            gcp_incidents.append({
                "name": inc.get("external_desc", inc.get("service_name", "GCP Incident")),
                "impact": inc.get("severity", "low"),
                "affected_components": affected_products,
                "latest_update": latest.get("text", "")[:200],
                "created_at": inc.get("begin", ""),
                "status": latest.get("status", ""),
            })
        base["incidents"] = gcp_incidents
        base["description"] = f"{len(eu)} UK-relevant incident(s)"
        if gcp_incidents:
            names = ", ".join(set(c for i in gcp_incidents for c in i["affected_components"][:3]))
            if names:
                base["description"] += f" affecting {names}"
        return base

    def _check_aws(self, svc: dict, base: dict) -> dict:
        resp = httpx.get(svc["status_url"], timeout=8,
                         headers={"Accept": "application/json"})
        if resp.status_code != 200:
            return base
        data = resp.json()
        events = data.get("archive", [])
        # Filter for eu-west (UK) events
        uk_events = [e for e in events
                     if e.get("status", 0) >= 1
                     and any(r in str(e).lower()
                             for r in ("eu-west", "london", "global", "europe"))]
        if uk_events:
            worst = max(e.get("status", 0) for e in uk_events)
            base["status"] = "major_outage" if worst >= 2 else "degraded"
            base["description"] = f"{len(uk_events)} UK-region event(s)"
        return base

    def _check_google_workspace(self, svc: dict, base: dict) -> dict:
        """Check Google Workspace status for Gmail (UK focus)."""
        resp = httpx.get(svc["status_url"], timeout=8,
                         headers={"Accept": "application/json"})
        if resp.status_code != 200:
            return base
        try:
            incidents = resp.json()
            active = [i for i in incidents
                      if i.get("most-recent-update", {}).get("status", "").upper()
                      not in ("AVAILABLE",)
                      and "gmail" in str(i).lower()]
            if active:
                base["status"] = "degraded"
                base["description"] = f"{len(active)} Gmail incident(s)"
        except Exception:
            pass
        return base

    def _check_xbox(self, svc: dict, base: dict) -> dict:
        """Check Xbox Live status — GB endpoint."""
        resp = httpx.get(svc["status_url"], timeout=8,
                         headers={"Accept": "application/json"})
        if resp.status_code != 200:
            return base
        try:
            data = resp.json()
            services = data if isinstance(data, list) else data.get("CoreServices", [])
            issues = [s for s in services
                      if isinstance(s, dict) and s.get("Status", {}).get("Id", 0) != 0]
            if issues:
                base["status"] = "degraded"
                base["description"] = f"{len(issues)} Xbox service(s) impacted"
        except Exception:
            pass
        return base

    def _check_ping(self, svc: dict, base: dict) -> dict:
        """Simple reachability check — if it responds, it's operational."""
        resp = httpx.get(svc["status_url"], timeout=10, follow_redirects=True,
                         headers={"User-Agent": "Arbiter-Health/1.0"})
        if resp.status_code < 400:
            base["status"] = "operational"
            base["description"] = "Service reachable"
        else:
            base["status"] = "degraded"
            base["description"] = f"HTTP {resp.status_code}"
        return base

    def _check_apple_system(self, svc: dict, base: dict) -> dict:
        """Check Apple System Status page for Sign in with Apple."""
        resp = httpx.get(svc["status_url"], timeout=10, follow_redirects=True,
                         headers={"User-Agent": "Arbiter-Health/1.0"})
        if resp.status_code < 400:
            body = resp.text.lower()
            # Look for any mention of issues with sign-in / Apple ID
            if any(kw in body for kw in ("issue", "outage", "unavailable")):
                if "sign in" in body or "apple id" in body:
                    base["status"] = "degraded"
                    base["description"] = "Apple ID / Sign In issues reported"
                    return base
            base["status"] = "operational"
            base["description"] = "Sign in with Apple operational"
        else:
            base["status"] = "unknown"
            base["description"] = "Status page unreachable"
        return base

    def _check_google_identity(self, svc: dict, base: dict) -> dict:
        """Check Google Identity / OAuth status via Workspace incidents."""
        resp = httpx.get(svc["status_url"], timeout=8,
                         headers={"Accept": "application/json"})
        if resp.status_code != 200:
            return base
        try:
            incidents = resp.json()
            # Filter for identity/auth related incidents
            active = [i for i in incidents
                      if i.get("most-recent-update", {}).get("status", "").upper()
                      not in ("AVAILABLE",)
                      and any(kw in str(i).lower()
                              for kw in ("sign-in", "oauth", "identity", "accounts", "authentication"))]
            if active:
                base["status"] = "degraded"
                base["description"] = f"{len(active)} auth incident(s)"
        except Exception:
            pass
        return base

    def _check_comfyui_local(self, svc: dict, base: dict) -> dict:
        """Check ComfyUI on local network (RTX 3080 PC)."""
        comfyui_url = os.getenv("COMFYUI_BASE_URL", "http://localhost:8188")
        try:
            resp = httpx.get(f"{comfyui_url}/system_stats", timeout=3)
            if resp.status_code == 200:
                base["status"] = "operational"
                base["description"] = "RTX 3080 — ComfyUI online"
            else:
                base["status"] = "major_outage"
                base["description"] = "ComfyUI not responding"
        except Exception:
            base["status"] = "major_outage"
            base["description"] = "RTX 3080 PC unreachable"
        return base
