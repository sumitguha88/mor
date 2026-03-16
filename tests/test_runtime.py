from pathlib import Path

from mor.runtime import OntologyRuntime


ONTOLOGY_ROOT = Path(__file__).resolve().parents[1] / "ontology"
EXAMPLES_ROOT = Path(__file__).resolve().parents[1] / "examples"


def test_runtime_resolves_alias() -> None:
    runtime = OntologyRuntime(ONTOLOGY_ROOT)

    result = runtime.resolve("grind stage")

    assert result.matched is True
    assert result.canonical == "pigment dispersion"
    assert result.concept_id == "pigment-dispersion"


def test_runtime_expands_query() -> None:
    runtime = OntologyRuntime(ONTOLOGY_ROOT)

    result = runtime.expand("how do we control viscosity in decorative paint production")

    assert "paint manufacturing" in result.expanded_terms
    assert "quality control" in result.expanded_terms
    assert result.matched_concepts


def test_runtime_generates_scaffold() -> None:
    runtime = OntologyRuntime(ONTOLOGY_ROOT)

    result = runtime.scaffold(
        "architecture_explanation",
        query="how do we control viscosity in decorative paint production",
    )
    section_ids = [section.id for section in result.sections]

    assert section_ids[:4] == ["definition", "mechanism", "tradeoffs", "comparison"]
    assert "viscosity control" in result.concepts


def test_runtime_benchmark() -> None:
    runtime = OntologyRuntime(ONTOLOGY_ROOT)

    result = runtime.benchmark(EXAMPLES_ROOT / "benchmark_cases.json")

    assert len(result.cases) == 2
    assert result.aggregate_ontology_assisted.concept_resolution_success >= (
        result.aggregate_baseline.concept_resolution_success
    )


def test_runtime_can_select_marketing_area() -> None:
    runtime = OntologyRuntime(ONTOLOGY_ROOT, area="marketing", version="V1")

    result = runtime.resolve("paid search")

    assert result.matched is True
    assert result.canonical == "search advertising"


def test_runtime_infers_inverse_relationships_for_v3() -> None:
    runtime = OntologyRuntime(ONTOLOGY_ROOT, area="paint-manufacturing", version="V3")

    raw_material = runtime.get_concept("raw-material")

    assert raw_material is not None
    assert any(
        relationship.relationship_type == "contained_in"
        and relationship.target_id == "product"
        and relationship.inferred
        for relationship in raw_material.inferred_relationships
    )
    assert any(
        relationship.relationship_type == "supplied_by"
        and relationship.target_id == "supplier"
        and relationship.inferred
        for relationship in raw_material.inferred_relationships
    )
