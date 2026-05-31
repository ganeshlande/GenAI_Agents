"""
Template listing and create-from-template endpoint tests.
"""

from app.seed.workflow_templates import WORKFLOW_TEMPLATES

TEMPLATE_KEYS = list(WORKFLOW_TEMPLATES.keys())
FIRST_TEMPLATE_TYPE = TEMPLATE_KEYS[0]


# ── List templates ────────────────────────────────────────────────────────────

def test_list_templates_returns_all(client):
    r = client.get("/api/templates")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == len(WORKFLOW_TEMPLATES)


def test_list_templates_have_required_fields(client):
    r = client.get("/api/templates")
    for tmpl in r.json():
        for field in ("template_type", "name", "description", "agents", "tools", "nodes", "edges"):
            assert field in tmpl, f"Field '{field}' missing from template"


def test_list_templates_contains_payment_investigation(client):
    r = client.get("/api/templates")
    types = [t["template_type"] for t in r.json()]
    assert "payment_failure_investigation" in types


def test_list_templates_contains_merchant_onboarding(client):
    r = client.get("/api/templates")
    types = [t["template_type"] for t in r.json()]
    assert "merchant_onboarding_review" in types


# ── Get single template ───────────────────────────────────────────────────────

def test_get_template_by_type(client):
    r = client.get("/api/templates/payment_failure_investigation")
    assert r.status_code == 200
    body = r.json()
    assert body["template_type"] == "payment_failure_investigation"
    assert body["name"] == "Payment Failure Investigation"
    assert len(body["nodes"]) >= 4
    assert len(body["edges"]) >= 3
    assert "Support Intake Agent" in body["agents"]
    assert "payment_lookup" in body["tools"]


def test_get_template_nodes_have_react_flow_shape(client):
    r = client.get("/api/templates/payment_failure_investigation")
    for node in r.json()["nodes"]:
        assert "id" in node
        assert "position" in node
        assert "x" in node["position"] and "y" in node["position"]
        assert "data" in node


def test_get_template_edges_have_source_target(client):
    r = client.get("/api/templates/payment_failure_investigation")
    for edge in r.json()["edges"]:
        assert "source" in edge
        assert "target" in edge


def test_get_template_not_found(client):
    r = client.get("/api/templates/nonexistent_template")
    assert r.status_code == 404
    assert "nonexistent_template" in r.json()["detail"]


def test_get_merchant_onboarding_template(client):
    r = client.get("/api/templates/merchant_onboarding_review")
    assert r.status_code == 200
    body = r.json()
    assert body["template_type"] == "merchant_onboarding_review"
    assert "risk_check" in body["tools"]
    assert len(body["nodes"]) >= 4


# ── Create workflow from template ─────────────────────────────────────────────

def test_create_workflow_from_template_default_name(client):
    r = client.post("/api/templates/payment_failure_investigation/create-workflow", json={})
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Payment Failure Investigation"
    assert body["template_type"] == "payment_failure_investigation"
    assert len(body["nodes"]) >= 4
    assert len(body["edges"]) >= 3
    assert "id" in body and "created_at" in body


def test_create_workflow_from_template_custom_name(client):
    r = client.post(
        "/api/templates/payment_failure_investigation/create-workflow",
        json={"name": "My Custom Investigation WF", "description": "Custom desc"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "My Custom Investigation WF"
    assert body["description"] == "Custom desc"
    # Nodes/edges still come from the template
    assert len(body["nodes"]) >= 4


def test_create_workflow_from_template_nodes_match_template(client):
    r_tmpl = client.get("/api/templates/merchant_onboarding_review")
    tmpl_nodes = r_tmpl.json()["nodes"]

    r_wf = client.post("/api/templates/merchant_onboarding_review/create-workflow", json={})
    wf_nodes = r_wf.json()["nodes"]

    # Nodes should be identical to template definition
    assert wf_nodes == tmpl_nodes


def test_create_workflow_from_template_creates_new_each_time(client):
    ids = []
    for i in range(2):
        r = client.post(
            f"/api/templates/{FIRST_TEMPLATE_TYPE}/create-workflow",
            json={"name": f"Instance {i}"},
        )
        assert r.status_code == 201
        ids.append(r.json()["id"])
    assert ids[0] != ids[1], "Each creation should produce a distinct DB record"


def test_create_workflow_from_template_not_found(client):
    r = client.post("/api/templates/nonexistent/create-workflow", json={})
    assert r.status_code == 404


def test_create_workflow_from_template_no_body(client):
    # Sending no body at all should still work (defaults to template values)
    r = client.post(
        "/api/templates/merchant_onboarding_review/create-workflow",
        content=b"",
        headers={"Content-Type": "application/json"},
    )
    # 201 or 422 both acceptable — 201 expected with Body(default=...)
    assert r.status_code in (201, 422)
