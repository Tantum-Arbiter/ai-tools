"""
RevenueCat Monitor — App revenue and subscription tracking for ARBITER.
Uses RevenueCat REST API v2 to pull subscriber metrics, MRR, and revenue.

Setup:
  1. Go to app.revenuecat.com → Project Settings → API Keys
  2. Copy your SECRET API key (starts with sk_)
  3. Set REVENUECAT_API_KEY in .env
  4. Set REVENUECAT_PROJECT_ID in .env (from the URL: app.revenuecat.com/projects/PROJECT_ID)
"""
import os
import logging
from datetime import datetime, timedelta

import httpx

log = logging.getLogger(__name__)

RC_API_KEY = os.getenv("REVENUECAT_API_KEY", "")
RC_PROJECT_ID = os.getenv("REVENUECAT_PROJECT_ID", "")
RC_BASE = "https://api.revenuecat.com"


class RevenueCatMonitor:
    def __init__(self):
        self.api_key = RC_API_KEY
        self.project_id = RC_PROJECT_ID
        self._cache = {}
        self._cache_time = None
        self._ttl = 300  # 5 min cache

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _get(self, path: str) -> dict | None:
        if not self.configured:
            return None
        try:
            r = httpx.get(f"{RC_BASE}{path}", headers=self._headers(), timeout=15)
            if r.status_code == 200:
                return r.json()
            log.warning(f"RevenueCat {r.status_code}: {r.text[:200]}")
        except Exception as e:
            log.error(f"RevenueCat request error: {e}")
        return None

    def summary(self) -> dict:
        """Get overview metrics for the dashboard."""
        if not self.configured:
            return {"configured": False}

        now = datetime.utcnow()
        if self._cache and self._cache_time and (now - self._cache_time).total_seconds() < self._ttl:
            return self._cache

        overview = self._get_overview()
        result = {
            "configured": True,
            "overview": overview,
        }

        self._cache = result
        self._cache_time = now
        return result

    def _get_overview(self) -> dict:
        """Get overview metrics from RevenueCat REST API v2."""
        if not self.project_id:
            return self._get_overview_v1()

        data = self._get(f"/v2/projects/{self.project_id}/metrics/overview")
        if not data:
            return self._get_overview_v1()

        metrics = data.get("metrics", {})
        return {
            "active_subscribers": metrics.get("active_subscribers", 0),
            "active_trials": metrics.get("active_trials", 0),
            "mrr": metrics.get("mrr", 0),
            "revenue": metrics.get("revenue", 0),
            "new_customers": metrics.get("new_customers", 0),
            "churned_subscribers": metrics.get("churned_subscribers", 0),
            "refund_rate": metrics.get("refund_rate", 0),
        }

    def _get_overview_v1(self) -> dict:
        """Fallback: Use v1 subscribers endpoint for basic data."""
        # v1 doesn't have aggregate metrics, return structure with zeros
        return {
            "active_subscribers": 0,
            "active_trials": 0,
            "mrr": 0,
            "revenue": 0,
            "new_customers": 0,
            "churned_subscribers": 0,
            "refund_rate": 0,
            "note": "Set REVENUECAT_PROJECT_ID for full metrics",
        }

    def get_subscriber(self, app_user_id: str) -> dict | None:
        """Look up a specific subscriber."""
        data = self._get(f"/v1/subscribers/{app_user_id}")
        if not data:
            return None
        sub = data.get("subscriber", {})
        return {
            "first_seen": sub.get("first_seen", ""),
            "entitlements": list(sub.get("entitlements", {}).keys()),
            "subscriptions": list(sub.get("subscriptions", {}).keys()),
            "non_subscriptions": list(sub.get("non_subscriptions", {}).keys()),
        }

    def recent_transactions(self) -> list[dict]:
        """Get recent transactions if available (v2 only)."""
        if not self.project_id:
            return []
        data = self._get(f"/v2/projects/{self.project_id}/transactions?limit=10")
        if not data:
            return []
        return [
            {
                "id": t.get("id", ""),
                "type": t.get("type", ""),
                "revenue": t.get("revenue_in_usd", {}).get("amount", 0),
                "product_id": t.get("product_id", ""),
                "purchased_at": t.get("purchased_at", ""),
            }
            for t in data.get("transactions", [])[:10]
        ]
