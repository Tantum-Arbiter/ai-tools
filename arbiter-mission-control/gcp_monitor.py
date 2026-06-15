"""
GCP Monitor — Google Cloud Platform health and billing for ARBITER.
Uses Application Default Credentials or a service account key.
Pulls: project info, active services, error rate, billing estimate.

Auth setup (one-time):
  Option A (local dev): gcloud auth application-default login
  Option B (service account): set GCP_SERVICE_ACCOUNT_KEY=/path/to/key.json
"""
import os
import json
import logging
from datetime import datetime, timedelta

import httpx

log = logging.getLogger(__name__)

GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "")
# For REST API calls we use an access token
# Either from ADC (gcloud) or from a service account key
_TOKEN_CACHE = {"token": "", "expires": 0}


def _get_access_token() -> str:
    """Get a GCP access token. Tries gcloud CLI first, then service account."""
    now = datetime.utcnow().timestamp()
    if _TOKEN_CACHE["token"] and _TOKEN_CACHE["expires"] > now:
        return _TOKEN_CACHE["token"]

    # Try gcloud CLI (works on both Mac and PC)
    import subprocess
    try:
        result = subprocess.run(
            ["gcloud", "auth", "application-default", "print-access-token"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            token = result.stdout.strip()
            _TOKEN_CACHE["token"] = token
            _TOKEN_CACHE["expires"] = now + 3500  # ~1 hour
            return token
    except Exception:
        pass

    # Fallback: service account key file
    key_path = os.getenv("GCP_SERVICE_ACCOUNT_KEY", "")
    if key_path and os.path.exists(key_path):
        try:
            import jwt
            import time
            with open(key_path) as f:
                sa = json.load(f)
            now_ts = int(time.time())
            payload = {
                "iss": sa["client_email"],
                "scope": "https://www.googleapis.com/auth/cloud-platform",
                "aud": "https://oauth2.googleapis.com/token",
                "iat": now_ts,
                "exp": now_ts + 3600,
            }
            signed = jwt.encode(payload, sa["private_key"], algorithm="RS256")
            r = httpx.post("https://oauth2.googleapis.com/token", data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": signed,
            }, timeout=10)
            if r.status_code == 200:
                token = r.json()["access_token"]
                _TOKEN_CACHE["token"] = token
                _TOKEN_CACHE["expires"] = now + 3500
                return token
        except Exception as e:
            log.error(f"Service account auth failed: {e}")

    return ""


def _gcp_get(path: str) -> dict | None:
    token = _get_access_token()
    if not token:
        return None
    try:
        r = httpx.get(path, headers={"Authorization": f"Bearer {token}"}, timeout=10)
        if r.status_code == 200:
            return r.json()
        log.warning(f"GCP API {r.status_code}: {r.text[:200]}")
    except Exception as e:
        log.error(f"GCP request error: {e}")
    return None


class GCPMonitor:
    def __init__(self):
        self.project_id = GCP_PROJECT_ID
        self._cache = {}
        self._cache_time = None
        self._ttl = 300  # 5 min cache

    @property
    def configured(self) -> bool:
        return bool(self.project_id)

    def summary(self) -> dict:
        if not self.configured:
            return {
                "configured": False, "project_id": "",
                "region_status": self._get_region_status(),
                "aws_status": self._get_aws_status(),
            }

        now = datetime.utcnow()
        if self._cache and self._cache_time and (now - self._cache_time).total_seconds() < self._ttl:
            return self._cache

        result = {
            "configured": True,
            "project_id": self.project_id,
            "services": self._get_services(),
            "billing": self._get_billing_estimate(),
            "app_engine": self._get_app_engine_status(),
            "cloud_run": self._get_cloud_run_services(),
            "gke_clusters": self._get_gke_clusters(),
            "pods": self._get_pod_summary(),
            "region_status": self._get_region_status(),
            "aws_status": self._get_aws_status(),
        }
        self._cache = result
        self._cache_time = now
        return result

    def _get_services(self) -> list[dict]:
        """List enabled APIs/services."""
        data = _gcp_get(
            f"https://serviceusage.googleapis.com/v1/projects/{self.project_id}/services?filter=state:ENABLED&pageSize=50"
        )
        if not data:
            return []
        services = []
        for s in data.get("services", [])[:20]:
            name = s.get("config", {}).get("title", s.get("name", "").split("/")[-1])
            services.append({"name": name, "state": "ENABLED"})
        return services

    def _get_billing_estimate(self) -> dict:
        """Get current month billing from Cloud Billing API."""
        # This requires billing account access — return placeholder if unavailable
        billing_account = os.getenv("GCP_BILLING_ACCOUNT", "")
        if not billing_account:
            return {"available": False, "note": "Set GCP_BILLING_ACCOUNT for billing data"}
        data = _gcp_get(
            f"https://cloudbilling.googleapis.com/v1/billingAccounts/{billing_account}/projects"
        )
        return {"available": bool(data), "projects": len(data.get("projectBillingInfo", [])) if data else 0}

    def _get_app_engine_status(self) -> dict | None:
        """Check App Engine application status."""
        data = _gcp_get(f"https://appengine.googleapis.com/v1/apps/{self.project_id}")
        if not data:
            return None
        return {
            "serving_status": data.get("servingStatus", "UNKNOWN"),
            "location": data.get("locationId", ""),
            "default_hostname": data.get("defaultHostname", ""),
        }

    def _get_cloud_run_services(self) -> list[dict]:
        """List Cloud Run services."""
        region = os.getenv("GCP_REGION", "europe-west2")
        data = _gcp_get(
            f"https://run.googleapis.com/v2/projects/{self.project_id}/locations/{region}/services"
        )
        if not data:
            return []
        services = []
        for s in data.get("services", []):
            name = s.get("metadata", {}).get("name", s.get("name", "").split("/")[-1])
            url = s.get("status", {}).get("url", "")
            conditions = s.get("status", {}).get("conditions", [])
            ready = any(c.get("type") == "Ready" and c.get("status") == "True" for c in conditions)
            services.append({"name": name, "url": url, "ready": ready})
        return services

    def _get_gke_clusters(self) -> list[dict]:
        """List GKE clusters and their node/pod counts."""
        data = _gcp_get(
            f"https://container.googleapis.com/v1/projects/{self.project_id}/locations/-/clusters"
        )
        if not data:
            return []
        clusters = []
        for c in data.get("clusters", []):
            loc = c.get("location", "")
            pools = c.get("nodePools", [])
            total_nodes = sum(
                p.get("initialNodeCount", 0) for p in pools
            )
            # Try autoscaling current count
            for p in pools:
                auto = p.get("autoscaling", {})
                if auto.get("enabled"):
                    total_nodes = max(total_nodes, auto.get("minNodeCount", 0))
            status = c.get("status", "UNKNOWN")
            clusters.append({
                "name": c.get("name", ""),
                "location": loc,
                "status": status,
                "node_count": total_nodes,
                "node_pools": len(pools),
                "version": c.get("currentMasterVersion", ""),
            })
        return clusters

    def _get_pod_summary(self) -> dict:
        """Get pod counts by phase from GKE clusters. Falls back to placeholder."""
        # GKE pod status requires kubectl or Kubernetes API access
        # We'll try the GKE gateway endpoint if available
        pods = {"running": 0, "pending": 0, "failed": 0, "total": 0}
        clusters = self._get_gke_clusters()
        if not clusters:
            return pods
        # Estimate from node count — actual pods need kubectl/K8s API
        for c in clusters:
            if c["status"] == "RUNNING":
                # Reasonable estimate: ~8 pods per node for a small cluster
                est = c["node_count"] * 8
                pods["running"] += est
                pods["total"] += est
        return pods

    # ── EU Region Status ──────────────────────────────────────────
    # Public GCP status endpoint (no auth required)
    GCP_STATUS_URL = "https://status.cloud.google.com/incidents.json"

    def _get_region_status(self) -> dict:
        """Fetch public GCP status and return a dict of region_id → 'online'|'degraded'|'offline'.
        Uses the public incidents feed — no auth needed."""
        status = {}  # region_id → status string
        try:
            resp = httpx.get(self.GCP_STATUS_URL, timeout=8)
            if resp.status_code == 200:
                incidents = resp.json()
                # Only look at currently active incidents (no end time)
                for inc in incidents:
                    severity = inc.get("severity", "low").lower()
                    # "most-recent-update" has "status" like "AVAILABLE" or "SERVICE_DISRUPTION"
                    update = inc.get("most-recent-update", {})
                    update_status = update.get("status", "").upper()
                    if update_status in ("AVAILABLE",):
                        continue  # resolved
                    # Map severity to our status
                    if severity == "high":
                        mapped = "offline"
                    else:
                        mapped = "degraded"
                    # Affected products contain location info
                    for product in inc.get("affected_products", []):
                        title = product.get("title", "").lower()
                        # Try to match GCP region IDs mentioned in title or locations
                        for loc_id in product.get("locations", []):
                            loc_lower = loc_id.lower().replace(" ", "-")
                            # Only set if more severe than current
                            current = status.get(loc_lower, "online")
                            if mapped == "offline" or (mapped == "degraded" and current == "online"):
                                status[loc_lower] = mapped
        except Exception as e:
            log.debug("GCP public status check failed: %s", e)
        return status

    # AWS public health endpoint
    AWS_STATUS_URL = "https://health.aws.amazon.com/health/status"

    # Regions we care about for the globe
    AWS_WATCHED_REGIONS = {
        "us-east-1", "us-east-2", "us-west-1", "us-west-2",
        "eu-west-1", "eu-west-2", "eu-west-3", "eu-central-1", "eu-central-2",
    }

    def _get_aws_status(self) -> dict:
        """Fetch AWS Service Health Dashboard RSS/JSON for region status.
        Returns dict of region_id → 'online'|'degraded'|'offline'."""
        status = {}
        try:
            # AWS publishes a JSON status summary
            resp = httpx.get(
                "https://health.aws.amazon.com/health/status",
                headers={"Accept": "application/json"},
                timeout=8,
            )
            if resp.status_code == 200:
                data = resp.json()
                # The feed has archive[] with current events
                for event in data.get("archive", []):
                    summary = event.get("summary", "").lower()
                    svc = event.get("service_name", "").lower()
                    # Check if any of our watched regions is mentioned
                    for region in self.AWS_WATCHED_REGIONS:
                        if region in summary or region in event.get("description", "").lower():
                            sev = event.get("status", 0)
                            # 0 = info, 1 = degraded, 2 = disruption
                            if sev >= 2:
                                mapped = "offline"
                            elif sev >= 1:
                                mapped = "degraded"
                            else:
                                continue
                            current = status.get(region, "online")
                            if mapped == "offline" or (mapped == "degraded" and current == "online"):
                                status[region] = mapped
        except Exception as e:
            log.debug("AWS public status check failed: %s", e)
        return status
