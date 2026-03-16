from pathlib import Path

from fastapi.testclient import TestClient

from mor.api import create_app


ONTOLOGY_ROOT = Path(__file__).resolve().parents[1] / "ontology"


def test_api_endpoints() -> None:
    client = TestClient(create_app(ONTOLOGY_ROOT))

    concepts = client.get("/concepts")
    assert concepts.status_code == 200
    assert any(item["id"] == "pigment-dispersion" for item in concepts.json())

    resolve = client.post("/resolve", json={"term": "grind stage"})
    assert resolve.status_code == 200
    assert resolve.json()["canonical"] == "pigment dispersion"

    expand = client.post(
        "/expand",
        json={"query": "how do we control viscosity in decorative paint production"},
    )
    assert expand.status_code == 200
    assert "quality control" in expand.json()["expanded_terms"]

    scaffold = client.post(
        "/scaffold",
        json={
            "intent": "architecture_explanation",
            "query": "how do we control viscosity in decorative paint production",
        },
    )
    assert scaffold.status_code == 200
    assert scaffold.json()["sections"][0]["id"] == "definition"

    stats = client.get("/stats")
    assert stats.status_code == 200
    assert stats.json()["concept_count"] > 0


def test_api_can_target_marketing_area() -> None:
    client = TestClient(create_app(ONTOLOGY_ROOT, area="marketing", version="V1"))

    resolve = client.post("/resolve", json={"term": "paid search"})

    assert resolve.status_code == 200
    assert resolve.json()["canonical"] == "search advertising"
