"""
Workflow CRUD + /run endpoint tests.
"""

MINIMAL_WF = {"name": "Test Workflow Alpha", "description": "A test workflow."}

FULL_WF = {
    "name": "Test Workflow Beta",
    "description": "Full workflow with nodes and edges.",
    "nodes": [
        {"id": "n1", "type": "agentNode", "position": {"x": 0, "y": 0}, "data": {"label": "Agent A"}},
        {"id": "n2", "type": "agentNode", "position": {"x": 300, "y": 0}, "data": {"label": "Agent B"}},
    ],
    "edges": [
        {"id": "e1", "source": "n1", "target": "n2", "label": "handoff"}
    ],
    "template_type": "custom",
}


def _create(client, payload: dict) -> dict:
    r = client.post("/api/workflows", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


# ── Seed ──────────────────────────────────────────────────────────────────────

def test_seed_workflows_present(client, db_session):
    from app.seed.seed_data import seed_workflows
    from app.seed.workflow_templates import WORKFLOW_TEMPLATES

    seed_workflows(db=db_session)
    r = client.get("/api/workflows")
    assert r.status_code == 200
    names = [w["name"] for w in r.json()]
    for tmpl in WORKFLOW_TEMPLATES.values():
        assert tmpl["name"] in names, f"Seeded workflow '{tmpl['name']}' not found"


# ── LIST ──────────────────────────────────────────────────────────────────────

def test_list_workflows_returns_list(client):
    r = client.get("/api/workflows")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_list_workflows_pagination(client):
    r = client.get("/api/workflows?skip=0&limit=1")
    assert r.status_code == 200
    assert len(r.json()) <= 1


# ── CREATE ────────────────────────────────────────────────────────────────────

def test_create_workflow_minimal(client):
    wf = _create(client, MINIMAL_WF)
    assert wf["name"] == MINIMAL_WF["name"]
    assert wf["nodes"] == []
    assert wf["edges"] == []
    assert wf["template_type"] is None
    assert "id" in wf and "created_at" in wf


def test_create_workflow_full(client):
    wf = _create(client, FULL_WF)
    assert len(wf["nodes"]) == 2
    assert len(wf["edges"]) == 1
    assert wf["edges"][0]["label"] == "handoff"
    assert wf["template_type"] == "custom"


def test_create_workflow_missing_name(client):
    r = client.post("/api/workflows", json={"description": "no name"})
    assert r.status_code == 422


# ── GET ───────────────────────────────────────────────────────────────────────

def test_get_workflow_by_id(client):
    created = _create(client, {"name": "GetMe WF", "description": "desc"})
    r = client.get(f"/api/workflows/{created['id']}")
    assert r.status_code == 200
    assert r.json()["name"] == "GetMe WF"


def test_get_workflow_not_found(client):
    r = client.get("/api/workflows/99999")
    assert r.status_code == 404


# ── UPDATE ────────────────────────────────────────────────────────────────────

def test_update_workflow_partial(client):
    created = _create(client, {"name": "UpdateMe WF", "description": "old desc"})
    r = client.put(f"/api/workflows/{created['id']}", json={"description": "new desc"})
    assert r.status_code == 200
    assert r.json()["description"] == "new desc"
    assert r.json()["name"] == "UpdateMe WF"   # unchanged


def test_update_workflow_nodes_and_edges(client):
    created = _create(client, {"name": "NodesUpdate WF"})
    new_nodes = [{"id": "x1", "type": "agentNode", "position": {"x": 0, "y": 0}, "data": {}}]
    r = client.put(
        f"/api/workflows/{created['id']}",
        json={"nodes": new_nodes, "edges": []},
    )
    assert r.status_code == 200
    assert len(r.json()["nodes"]) == 1


def test_update_workflow_empty_body(client):
    created = _create(client, {"name": "EmptyUpdate WF"})
    r = client.put(f"/api/workflows/{created['id']}", json={})
    assert r.status_code == 422


def test_update_workflow_not_found(client):
    r = client.put("/api/workflows/99999", json={"description": "x"})
    assert r.status_code == 404


# ── DELETE ────────────────────────────────────────────────────────────────────

def test_delete_workflow(client):
    created = _create(client, {"name": "DeleteMe WF"})
    r = client.delete(f"/api/workflows/{created['id']}")
    assert r.status_code == 204
    assert client.get(f"/api/workflows/{created['id']}").status_code == 404


def test_delete_workflow_not_found(client):
    assert client.delete("/api/workflows/99999").status_code == 404


# ── RUN ───────────────────────────────────────────────────────────────────────

def test_run_workflow_creates_run_record(client):
    wf = _create(client, {"name": "Runnable WF"})
    r = client.post(
        f"/api/workflows/{wf['id']}/run",
        json={"message": "Test run with transaction TXN-001"},
    )
    # POST /run is now non-blocking — returns 202 Accepted with status=pending
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == "pending"
    assert body["run_id"] is not None
    assert body["workflow_id"] == wf["id"]
    assert body["workflow_name"] == "Runnable WF"
    assert "events_url" in body
    assert "poll_url" in body

    # BackgroundTasks run synchronously in TestClient — run should be done by now
    r2 = client.get(f"/api/runs/{body['run_id']}")
    assert r2.status_code == 200
    assert r2.json()["status"] in ("completed", "failed")


def test_run_workflow_empty_payload(client):
    wf = _create(client, {"name": "EmptyRun WF"})
    r = client.post(f"/api/workflows/{wf['id']}/run", json={})
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "pending"
    # Verify run completes via poll endpoint
    r2 = client.get(f"/api/runs/{body['run_id']}")
    assert r2.json()["status"] in ("completed", "failed")


def test_run_workflow_not_found(client):
    r = client.post("/api/workflows/99999/run", json={})
    assert r.status_code == 404


def test_multiple_runs_get_distinct_ids(client):
    wf = _create(client, {"name": "MultiRun WF"})
    run_ids = []
    for _ in range(3):
        r = client.post(f"/api/workflows/{wf['id']}/run", json={})
        assert r.status_code == 202
        run_ids.append(r.json()["run_id"])
    assert len(set(run_ids)) == 3, "Each run should get a unique ID"
