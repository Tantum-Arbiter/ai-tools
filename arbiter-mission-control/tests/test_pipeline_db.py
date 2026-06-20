"""Quick smoke-test for pipeline persistence methods."""
from persistence import ArbiterDB
import tempfile, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

db = ArbiterDB(os.path.join(tempfile.mkdtemp(), "test.db"))

stages = [
    {"agent_id": "researcher", "agent_name": "Researcher", "status": "pending", "output": None},
    {"agent_id": "analyst", "agent_name": "Analyst", "gate": True, "status": "pending", "output": None},
]
pid = db.save_pipeline("test directive", stages)
assert pid and len(pid) == 12

pipe = db.get_pipeline(pid)
assert pipe["status"] == "pending"
assert len(pipe["stages"]) == 2
assert pipe["directive"] == "test directive"
assert pipe["current_idx"] == 0

# Update
pipe["stages"][0]["status"] = "complete"
pipe["stages"][0]["output"] = "research output here"
db.update_pipeline(pid, pipe["stages"], 1, "waiting")

pipe2 = db.get_pipeline(pid)
assert pipe2["status"] == "waiting"
assert pipe2["current_idx"] == 1
assert pipe2["stages"][0]["status"] == "complete"
assert pipe2["stages"][0]["output"] == "research output here"
assert pipe2["stages"][1]["status"] == "pending"

# List
pipes = db.get_pipelines()
assert len(pipes) == 1
pipes_w = db.get_pipelines(status="waiting")
assert len(pipes_w) == 1
pipes_c = db.get_pipelines(status="complete")
assert len(pipes_c) == 0

# Not found
assert db.get_pipeline("nonexistent") is None

db.close()
print("ALL PIPELINE DB TESTS PASSED")
