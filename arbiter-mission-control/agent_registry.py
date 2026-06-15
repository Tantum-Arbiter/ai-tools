"""
Agent Registry — Tracks status of all managed AI agents.
Agents report heartbeats via POST /api/agents/heartbeat.
ARBITER monitors them and surfaces health in the HUD.
"""
import logging
from datetime import datetime
from dataclasses import dataclass, field, asdict

log = logging.getLogger(__name__)


@dataclass
class AgentInfo:
    agent_id: str
    name: str
    description: str = ""
    status: str = "unknown"         # online | degraded | offline | error | unknown
    last_heartbeat: str = ""
    last_run_at: str = ""
    last_run_status: str = ""       # success | failed | running | idle
    tasks_completed: int = 0
    tasks_failed: int = 0
    current_task: str = ""
    metrics: dict = field(default_factory=dict)
    url: str = ""                   # URL to open for this agent's UI


# ── Default agents (pre-registered) ──────────────────────────────
DEFAULT_AGENTS = [
    AgentInfo(
        agent_id="content-pipeline",
        name="Content Pipeline",
        description="Generates images/videos via ComfyUI + GPT-4o briefs, posts to Instagram & YouTube",
        url="http://localhost:8188",
    ),
    AgentInfo(
        agent_id="engagement-hub",
        name="Engagement Hub",
        description="Monitors comments & DMs, generates AI replies, manages CRM pipeline",
    ),
    AgentInfo(
        agent_id="comfyui",
        name="ComfyUI (RTX 3080)",
        description="Stable Diffusion image generation server",
        url="http://localhost:8188",
    ),
]


class AgentRegistry:
    def __init__(self):
        self.agents: dict[str, AgentInfo] = {}
        for a in DEFAULT_AGENTS:
            self.agents[a.agent_id] = AgentInfo(**asdict(a))

    def heartbeat(self, agent_id: str, data: dict) -> AgentInfo:
        """Update agent status from a heartbeat payload."""
        now = datetime.utcnow().isoformat()
        if agent_id not in self.agents:
            self.agents[agent_id] = AgentInfo(
                agent_id=agent_id,
                name=data.get("name", agent_id),
                description=data.get("description", ""),
            )
        agent = self.agents[agent_id]
        agent.status = data.get("status", "online")
        agent.last_heartbeat = now
        if "last_run_status" in data:
            agent.last_run_status = data["last_run_status"]
            agent.last_run_at = now
        if "tasks_completed" in data:
            agent.tasks_completed = data["tasks_completed"]
        if "tasks_failed" in data:
            agent.tasks_failed = data["tasks_failed"]
        if "current_task" in data:
            agent.current_task = data["current_task"]
        if "metrics" in data:
            agent.metrics.update(data["metrics"])
        if "url" in data:
            agent.url = data["url"]
        if "name" in data:
            agent.name = data["name"]
        log.info(f"Agent heartbeat: {agent_id} → {agent.status}")
        return agent

    def get_all(self) -> list[dict]:
        # Mark agents with stale heartbeats as potentially offline
        now = datetime.utcnow()
        results = []
        for a in self.agents.values():
            d = asdict(a)
            if a.last_heartbeat:
                try:
                    last = datetime.fromisoformat(a.last_heartbeat)
                    stale_mins = (now - last).total_seconds() / 60
                    d["stale_minutes"] = round(stale_mins, 1)
                    if stale_mins > 10 and a.status == "online":
                        d["status"] = "degraded"
                    if stale_mins > 30:
                        d["status"] = "offline"
                except Exception:
                    d["stale_minutes"] = None
            else:
                d["stale_minutes"] = None
            results.append(d)
        return results

    def get(self, agent_id: str) -> dict | None:
        a = self.agents.get(agent_id)
        return asdict(a) if a else None

    def get_bulletins(self) -> list[dict]:
        """Return urgent bulletins across all agents."""
        bulletins = []
        for a in self.agents.values():
            if a.status in ("error", "offline") and a.last_heartbeat:
                bulletins.append({
                    "level": "critical" if a.status == "error" else "warning",
                    "source": a.name,
                    "message": f"{a.name} is {a.status.upper()}",
                    "agent_id": a.agent_id,
                    "timestamp": a.last_heartbeat,
                })
            if a.last_run_status == "failed":
                bulletins.append({
                    "level": "high",
                    "source": a.name,
                    "message": f"Last run FAILED: {a.current_task or 'unknown task'}",
                    "agent_id": a.agent_id,
                    "timestamp": a.last_run_at,
                })
        return bulletins
