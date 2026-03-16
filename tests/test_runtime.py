from pathlib import Path

from mor.runtime import OntologyRuntime


ONTOLOGY_ROOT = Path(__file__).resolve().parents[1] / "ontology"
EXAMPLES_ROOT = Path(__file__).resolve().parents[1] / "examples"


def test_runtime_resolves_alias() -> None:
    runtime = OntologyRuntime(ONTOLOGY_ROOT)

    result = runtime.resolve("latex paint")

    assert result.matched is True
    assert result.canonical == "emulsion paint"
    assert result.concept_id == "emulsion-paint"
    assert result.matches[0].match_type == "alias"


def test_runtime_expands_query() -> None:
    runtime = OntologyRuntime(ONTOLOGY_ROOT)

    result = runtime.expand("paint viscosity control")

    assert "paint" in result.expanded_terms
    assert "viscosity" in result.expanded_terms
    assert result.matched_concepts
    assert result.resolved_concepts


def test_runtime_generates_scaffold_with_optional_extras() -> None:
    runtime = OntologyRuntime(ONTOLOGY_ROOT)

    result = runtime.scaffold(
        "concept_comparison",
        concept_ids=["emulsion-paint", "paint-type"],
        include_evidence_slots=True,
        include_constraints=True,
        include_relationship_paths=True,
    )
    section_ids = [section.id for section in result.sections]

    assert section_ids[:4] == ["definition", "similarities", "differences", "tradeoffs"]
    assert "comparison" in section_ids
    assert result.evidence_slots
    assert result.constraints
    assert result.relationship_paths


def test_runtime_lists_bundle_and_metadata() -> None:
    runtime = OntologyRuntime(ONTOLOGY_ROOT)

    metadata = runtime.metadata()
    bundles = runtime.list_bundles()
    bundle = runtime.get_bundle("paint@V1")

    assert metadata.area_id == "paint"
    assert metadata.version == "V1"
    assert bundles[0].id == "paint@V1"
    assert bundle is not None
    assert bundle.summary.area_id == "paint"
    assert bundle.concepts


def test_runtime_get_related_concepts() -> None:
    runtime = OntologyRuntime(ONTOLOGY_ROOT)

    links = runtime.get_related_concepts("emulsion paint")

    assert any(link.relationship_type == "type_of" for link in links)
    assert any(link.target.concept_id == "paint-type" for link in links)


def test_runtime_explain_query_resolution_shape() -> None:
    runtime = OntologyRuntime(ONTOLOGY_ROOT)

    result = runtime.explain_query_resolution("compare latex paint viscosity and gloss")

    assert any(match.concept.canonical == "emulsion paint" for match in result.alias_matches)
    assert "compare" in result.unmatched_terms
    assert result.notes
    assert result.rationale


def test_runtime_compute_query_coverage_shape() -> None:
    runtime = OntologyRuntime(ONTOLOGY_ROOT)

    result = runtime.compute_query_coverage("compare latex paint viscosity and gloss")

    assert result.covered_concepts
    assert result.coverage_score > 0
    assert "compare" in result.unresolved_terms


def test_runtime_stats_include_bundle_metadata() -> None:
    runtime = OntologyRuntime(ONTOLOGY_ROOT)

    result = runtime.stats()

    assert result.concept_count > 0
    assert result.bundle_id == "paint@V1"
    assert result.bundle_count >= 1


def test_runtime_benchmark() -> None:
    runtime = OntologyRuntime(ONTOLOGY_ROOT)

    result = runtime.benchmark(EXAMPLES_ROOT / "benchmark_cases.json")

    assert len(result.cases) == 2
    assert result.aggregate_ontology_assisted.ontology_coverage >= 0
