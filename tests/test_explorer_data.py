from pathlib import Path

from mor.explorer_data import build_graph_payload
from mor.runtime import OntologyRuntime


ONTOLOGY_ROOT = Path(__file__).resolve().parents[1] / "ontology"


def test_build_graph_payload_for_default_area() -> None:
    runtime = OntologyRuntime(ONTOLOGY_ROOT)

    payload = build_graph_payload(runtime)

    assert payload.area_id == "paint"
    assert payload.version == "V1"
    assert any(node.id == "emulsion-paint" for node in payload.nodes)
    emulsion_node = next(node for node in payload.nodes if node.id == "emulsion-paint")
    assert emulsion_node.properties["canonical"] == "emulsion paint"
    assert "latex paint" in emulsion_node.properties["aliases"]
    assert any(
        relationship["type"] == "type_of" and relationship["concept"] == "paint type"
        for relationship in emulsion_node.properties["relationships"]
    )
    assert any(edge.relation == "parent" for edge in payload.edges)
    assert any(edge.relation == "type_of" for edge in payload.edges)

def test_build_graph_payload_for_paint_area() -> None:
    runtime = OntologyRuntime(ONTOLOGY_ROOT, area="paint", version="V1")

    payload = build_graph_payload(runtime, include_not_same_as=False)

    assert payload.area_id == "paint"
    assert any(node.id == "paint" for node in payload.nodes)
