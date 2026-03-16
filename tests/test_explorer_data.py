from pathlib import Path

from mor.explorer_data import build_graph_payload
from mor.runtime import OntologyRuntime


ONTOLOGY_ROOT = Path(__file__).resolve().parents[1] / "ontology"


def test_build_graph_payload_for_default_area() -> None:
    runtime = OntologyRuntime(ONTOLOGY_ROOT)

    payload = build_graph_payload(runtime)

    assert payload.area_id == "paint-manufacturing"
    assert payload.version == "V1"
    assert any(node.id == "pigment-dispersion" for node in payload.nodes)
    pigment_node = next(node for node in payload.nodes if node.id == "pigment-dispersion")
    assert pigment_node.properties["canonical"] == "pigment dispersion"
    assert "grind stage" in pigment_node.properties["aliases"]
    assert any(
        relationship["type"] == "disperses" and relationship["concept"] == "pigment"
        for relationship in pigment_node.properties["relationships"]
    )
    assert any(edge.relation == "parent" for edge in payload.edges)
    assert any(edge.relation == "disperses" for edge in payload.edges)


def test_build_graph_payload_for_marketing_area() -> None:
    runtime = OntologyRuntime(ONTOLOGY_ROOT, area="marketing", version="V1")

    payload = build_graph_payload(runtime, include_not_same_as=False)

    assert payload.area_id == "marketing"
    assert any(node.id == "search-advertising" for node in payload.nodes)


def test_build_graph_payload_includes_inferred_inverse_edges_for_v3() -> None:
    runtime = OntologyRuntime(ONTOLOGY_ROOT, area="paint-manufacturing", version="V3")

    payload = build_graph_payload(runtime)

    raw_material_node = next(node for node in payload.nodes if node.id == "raw-material")
    assert any(
        relationship["type"] == "contained_in"
        and relationship["concept_id"] == "product"
        and relationship["inferred"]
        for relationship in raw_material_node.properties["inferred_relationships"]
    )
    assert not any(
        edge.relation == "contained_in"
        and edge.source == "raw-material"
        and edge.target == "product"
        for edge in payload.edges
    )
