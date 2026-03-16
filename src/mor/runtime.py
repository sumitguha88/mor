"""Runtime services for MOR."""

from __future__ import annotations

import difflib
import json
from collections import defaultdict
from pathlib import Path

from mor.constants import DEFAULT_INTENT_SECTIONS, SECTION_TITLES
from mor.models import (
    BenchmarkCase,
    BenchmarkCaseResult,
    BenchmarkScenarioMetrics,
    BenchmarkSummary,
    Concept,
    ConceptSummary,
    ExpandResponse,
    ExpansionEvidence,
    GraphPayload,
    OntologyModel,
    OntologyAreaSummary,
    OntologySelection,
    ResolveMatch,
    ResolveResponse,
    Relationship,
    ScaffoldResponse,
    ScaffoldSection,
    StatsResponse,
    ValidationReport,
)
from mor.explorer_data import build_graph_payload
from mor.parser import parse_ontology
from mor.registry import list_ontology_areas, resolve_ontology_selection
from mor.utils import normalize_term, slugify, tokenize, unique_preserve
from mor.validator import validate_drafts


class OntologyRuntime:
    """Shared runtime for CLI, API, MCP, and tests."""

    def __init__(
        self,
        ontology_root: str | Path = "ontology",
        area: str | None = None,
        version: str | None = None,
    ) -> None:
        self.root = Path(ontology_root)
        self.area = area
        self.version = version
        self.selection: OntologySelection | None = None
        self.drafts = []
        self.model = OntologyModel(root=self.root, concepts={}, canonical_index={}, label_index={})
        self.report = ValidationReport(valid=True, errors=0, warnings=0, issues=[])
        self.reload()

    def reload(self) -> None:
        self.selection = resolve_ontology_selection(self.root, area=self.area, version=self.version)
        self.drafts = parse_ontology(self.root, area=self.area, version=self.version)
        self.report = validate_drafts(self.drafts, structure=self.selection.structure if self.selection else None)
        self.model = self._build_model()

    def validate(self, reload: bool = True) -> ValidationReport:
        if reload:
            self.reload()
        return self.report

    def list_concepts(self) -> list[ConceptSummary]:
        return [
            ConceptSummary(
                id=concept.id,
                canonical=concept.canonical,
                aliases=concept.aliases,
                related_count=len(concept.related_ids),
                parent_count=len(concept.parent_ids),
            )
            for concept in self.model.concepts.values()
        ]

    def list_areas(self) -> list[OntologyAreaSummary]:
        return list_ontology_areas(self.root)

    def get_concept(self, concept_id: str) -> Concept | None:
        return self.model.concepts.get(concept_id)

    def graph_payload(
        self,
        include_related: bool = True,
        include_parents: bool = True,
        include_not_same_as: bool = True,
    ) -> GraphPayload:
        return build_graph_payload(
            self,
            include_related=include_related,
            include_parents=include_parents,
            include_not_same_as=include_not_same_as,
        )

    def resolve(self, term: str) -> ResolveResponse:
        normalized = normalize_term(term)
        matches = self.model.label_index.get(normalized, [])
        if len(matches) == 1:
            concept = self.model.concepts[matches[0]]
            matched_label = _matching_label(concept, normalized)
            return ResolveResponse(
                term=term,
                matched=True,
                ambiguous=False,
                concept_id=concept.id,
                canonical=concept.canonical,
                matches=[
                    ResolveMatch(
                        concept_id=concept.id,
                        canonical=concept.canonical,
                        matched_label=matched_label,
                    )
                ],
                explanation=f"Resolved '{term}' to canonical concept '{concept.canonical}'.",
            )
        if len(matches) > 1:
            resolved_matches = [
                ResolveMatch(
                    concept_id=concept_id,
                    canonical=self.model.concepts[concept_id].canonical,
                    matched_label=_matching_label(self.model.concepts[concept_id], normalized),
                )
                for concept_id in matches
            ]
            return ResolveResponse(
                term=term,
                matched=False,
                ambiguous=True,
                matches=resolved_matches,
                explanation=f"'{term}' is ambiguous across multiple ontology concepts.",
            )

        alternatives = self._alternative_matches(term)
        return ResolveResponse(
            term=term,
            matched=False,
            ambiguous=False,
            alternatives=alternatives,
            explanation=f"No exact ontology match for '{term}'.",
        )

    def expand(self, query: str, max_concepts: int = 5, max_terms: int = 12) -> ExpandResponse:
        normalized_query = normalize_term(query)
        query_tokens = set(tokenize(query))
        scored: list[tuple[float, Concept, list[str]]] = []
        for concept in self.model.concepts.values():
            score, reasons = _score_concept(concept, normalized_query, query_tokens)
            if score > 0:
                scored.append((score, concept, reasons))
        scored.sort(key=lambda item: (-item[0], item[1].canonical))
        matched = scored[:max_concepts]

        terms: list[str] = []
        evidences: list[ExpansionEvidence] = []
        for score, concept, reasons in matched:
            evidences.append(
                ExpansionEvidence(
                    concept_id=concept.id,
                    canonical=concept.canonical,
                    score=score,
                    reasons=reasons,
                )
            )
            terms.append(concept.canonical)
            terms.extend(self._expand_terms_for_concept(concept))

        expanded_terms = unique_preserve(terms)[:max_terms]
        explanation = (
            "Expanded query using direct matches, ontology relations, and query hints."
            if evidences
            else "No ontology concepts matched the query."
        )
        return ExpandResponse(
            query=query,
            matched_concepts=evidences,
            expanded_terms=expanded_terms,
            explanation=explanation,
        )

    def scaffold(
        self, intent: str, query: str | None = None, concept_ids: list[str] | None = None
    ) -> ScaffoldResponse:
        selected_ids = concept_ids or []
        if query and not selected_ids:
            expansion = self.expand(query)
            selected_ids = [evidence.concept_id for evidence in expansion.matched_concepts]
        selected_concepts = [self.model.concepts[concept_id] for concept_id in selected_ids if concept_id in self.model.concepts]
        base_sections = list(DEFAULT_INTENT_SECTIONS.get(intent, ("definition", "mechanism", "tradeoffs")))
        section_ids = list(base_sections)
        rationales: dict[str, str] = {
            section_id: f"Added from intent template '{intent}'."
            for section_id in base_sections
        }
        sources: dict[str, list[str]] = defaultdict(list)

        for concept in selected_concepts:
            for requirement in concept.answer_requirements:
                section_id = _section_id_from_requirement(requirement)
                if section_id not in section_ids:
                    section_ids.append(section_id)
                rationales.setdefault(
                    section_id,
                    f"Added from ontology answer requirements for '{concept.canonical}'.",
                )
                sources[section_id].append(concept.canonical)

        sections = [
            ScaffoldSection(
                id=section_id,
                title=SECTION_TITLES.get(section_id, _titleize(section_id)),
                rationale=rationales[section_id],
                source_concepts=unique_preserve(sources.get(section_id, [])),
            )
            for section_id in section_ids
        ]
        explanation = (
            "Generated scaffold from intent defaults and concept answer requirements."
            if selected_concepts
            else "Generated scaffold from intent defaults."
        )
        return ScaffoldResponse(
            intent=intent,
            sections=sections,
            concepts=[concept.canonical for concept in selected_concepts],
            explanation=explanation,
        )

    def stats(self) -> StatsResponse:
        relation_count = sum(len(concept.all_relationships) for concept in self.model.concepts.values())
        hierarchy_edge_count = sum(len(concept.parent_ids) for concept in self.model.concepts.values())
        orphan_count = sum(
            1
            for concept in self.model.concepts.values()
            if not concept.all_relationships and not concept.parent_ids and not concept.not_same_as_ids
        )
        alias_count = sum(len(concept.aliases) for concept in self.model.concepts.values())
        return StatsResponse(
            concept_count=len(self.model.concepts),
            alias_count=alias_count,
            relation_count=relation_count,
            hierarchy_edge_count=hierarchy_edge_count,
            orphan_count=orphan_count,
            validation_errors=self.report.errors,
            validation_warnings=self.report.warnings,
        )

    def benchmark(self, cases_path: str | Path | None = None) -> BenchmarkSummary:
        path = Path(cases_path) if cases_path else Path("examples/benchmark_cases.json")
        raw_cases = json.loads(path.read_text(encoding="utf-8"))
        cases = [BenchmarkCase.model_validate(item) for item in raw_cases]
        results: list[BenchmarkCaseResult] = []
        baseline_metrics: list[BenchmarkScenarioMetrics] = []
        assisted_metrics: list[BenchmarkScenarioMetrics] = []

        for case in cases:
            baseline = self._run_benchmark_case(case, assisted=False)
            assisted = self._run_benchmark_case(case, assisted=True)
            baseline_metrics.append(baseline)
            assisted_metrics.append(assisted)
            results.append(BenchmarkCaseResult(name=case.name, baseline=baseline, ontology_assisted=assisted))

        return BenchmarkSummary(
            cases=results,
            aggregate_baseline=_average_metrics(baseline_metrics),
            aggregate_ontology_assisted=_average_metrics(assisted_metrics),
        )

    def _build_model(self) -> OntologyModel:
        valid_concepts: dict[str, Concept] = {}
        canonical_index: dict[str, str] = {}
        label_index: dict[str, list[str]] = defaultdict(list)
        error_paths = {
            issue.source_path
            for issue in self.report.issues
            if issue.severity == "error" and issue.source_path is not None
        }

        for draft in self.drafts:
            if draft.source_path in error_paths:
                continue
            if not draft.canonical or not draft.definition:
                continue
            concept = Concept(
                id=draft.concept_id,
                title=draft.title,
                source_path=draft.source_path,
                canonical=draft.canonical,
                aliases=draft.aliases,
                definition=draft.definition,
                relationships=[
                    Relationship(
                        relationship_type=relationship.relationship_type,
                        target=relationship.target,
                    )
                    for relationship in draft.relationships
                ],
                related=draft.related,
                parents=draft.parents,
                not_same_as=draft.not_same_as,
                query_hints=draft.query_hints,
                answer_requirements=draft.answer_requirements,
            )
            valid_concepts[concept.id] = concept
            canonical_index[normalize_term(concept.canonical)] = concept.id
            for label in [concept.canonical, *concept.aliases]:
                normalized = normalize_term(label)
                if concept.id not in label_index[normalized]:
                    label_index[normalized].append(concept.id)

        for concept in valid_concepts.values():
            concept.related_ids = _resolve_reference_ids(concept.related, label_index)
            concept.relationships = _resolve_relationship_targets(concept.relationships, label_index)
            concept.parent_ids = _resolve_reference_ids(concept.parents, label_index)
            concept.not_same_as_ids = _resolve_reference_ids(concept.not_same_as, label_index)

        inverse_relationships = (
            self.selection.structure.inverse_relationships
            if self.selection and self.selection.structure
            else {}
        )
        if inverse_relationships:
            _apply_inverse_relationships(valid_concepts, inverse_relationships)

        return OntologyModel(
            root=self.root,
            area_id=self.selection.area_id if self.selection else None,
            version=self.selection.version if self.selection else None,
            concepts=valid_concepts,
            canonical_index=canonical_index,
            label_index=dict(label_index),
        )

    def _alternative_matches(self, term: str) -> list[ResolveMatch]:
        labels = list(self.model.label_index.keys())
        normalized = normalize_term(term)
        close = difflib.get_close_matches(normalized, labels, n=5, cutoff=0.5)
        alternatives: list[ResolveMatch] = []
        for candidate in close:
            concept_id = self.model.label_index[candidate][0]
            concept = self.model.concepts[concept_id]
            alternatives.append(
                ResolveMatch(
                    concept_id=concept.id,
                    canonical=concept.canonical,
                    matched_label=_matching_label(concept, candidate),
                )
            )
        return alternatives

    def _expand_terms_for_concept(self, concept: Concept) -> list[str]:
        expanded: list[str] = []
        seen_ids: list[str] = []
        for concept_id in concept.related_ids + concept.parent_ids:
            if concept_id not in seen_ids:
                seen_ids.append(concept_id)
        for relationship in concept.inferred_relationships:
            if relationship.target_id and relationship.target_id not in seen_ids:
                seen_ids.append(relationship.target_id)
        for concept_id in seen_ids:
            related = self.model.concepts.get(concept_id)
            if related:
                expanded.append(related.canonical)
        for hint in concept.query_hints:
            expanded.append(_query_hint_value(hint))
        return expanded

    def _run_benchmark_case(self, case: BenchmarkCase, assisted: bool) -> BenchmarkScenarioMetrics:
        if assisted:
            expansion = self.expand(case.query)
            matched_concepts = {item.concept_id for item in expansion.matched_concepts}
            expanded_terms = {normalize_term(term) for term in expansion.expanded_terms}
            scaffold = self.scaffold(case.intent, query=case.query)
        else:
            matched_concepts = _baseline_match(self.model, case.query)
            expanded_terms = {normalize_term(self.model.concepts[concept_id].canonical) for concept_id in matched_concepts}
            scaffold = ScaffoldResponse(
                intent=case.intent,
                sections=[
                    ScaffoldSection(
                        id=section_id,
                        title=SECTION_TITLES.get(section_id, _titleize(section_id)),
                        rationale="Baseline generic scaffold.",
                    )
                    for section_id in ("definition", "details")
                ],
                concepts=[self.model.concepts[concept_id].canonical for concept_id in matched_concepts],
                explanation="Generated baseline generic scaffold.",
            )

        expected_concepts = set(case.expected_concepts)
        expected_sections = {slugify(section) for section in case.expected_sections}
        expected_terms = {normalize_term(term) for term in case.expected_terms}
        concept_resolution_success = _safe_ratio(len(matched_concepts & expected_concepts), len(expected_concepts))
        ontology_coverage = _safe_ratio(len(matched_concepts), max(len(expected_concepts), 1))
        answer_sections = {section.id for section in scaffold.sections}
        answer_completeness = _safe_ratio(len(answer_sections & expected_sections), len(expected_sections))
        terminology_consistency = _safe_ratio(len(expanded_terms & expected_terms), len(expected_terms))
        return BenchmarkScenarioMetrics(
            concept_resolution_success=concept_resolution_success,
            ontology_coverage=min(ontology_coverage, 1.0),
            answer_completeness=answer_completeness,
            terminology_consistency=terminology_consistency,
        )


def _matching_label(concept: Concept, normalized: str) -> str:
    for label in [concept.canonical, *concept.aliases]:
        if normalize_term(label) == normalized:
            return label
    return concept.canonical


def _resolve_reference_ids(references: list[str], label_index: dict[str, list[str]]) -> list[str]:
    concept_ids: list[str] = []
    for reference in references:
        matches = label_index.get(normalize_term(reference), [])
        if len(matches) == 1 and matches[0] not in concept_ids:
            concept_ids.append(matches[0])
    return concept_ids


def _resolve_relationship_targets(
    relationships: list[Relationship], label_index: dict[str, list[str]]
) -> list[Relationship]:
    resolved: list[Relationship] = []
    for relationship in relationships:
        matches = label_index.get(normalize_term(relationship.target), [])
        target_id = matches[0] if len(matches) == 1 else None
        resolved.append(
            Relationship(
                relationship_type=relationship.relationship_type,
                target=relationship.target,
                target_id=target_id,
                inferred=relationship.inferred,
            )
        )
    return resolved


def _apply_inverse_relationships(
    concepts: dict[str, Concept],
    inverse_map: dict[str, str],
) -> None:
    for concept in concepts.values():
        for relationship in concept.relationships:
            target_id = relationship.target_id
            inverse_type = inverse_map.get(relationship.relationship_type)
            if not target_id or not inverse_type or target_id not in concepts:
                continue
            target_concept = concepts[target_id]
            if _has_relationship(target_concept.all_relationships, inverse_type, concept.id):
                continue
            target_concept.inferred_relationships.append(
                Relationship(
                    relationship_type=inverse_type,
                    target=concept.canonical,
                    target_id=concept.id,
                    inferred=True,
                )
            )


def _has_relationship(relationships: list[Relationship], relationship_type: str, target_id: str) -> bool:
    return any(
        relationship.relationship_type == relationship_type and relationship.target_id == target_id
        for relationship in relationships
    )


def _query_hint_value(hint: str) -> str:
    return hint.split(":", 1)[1].strip() if ":" in hint else hint


def _score_concept(concept: Concept, normalized_query: str, query_tokens: set[str]) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    for label in [concept.canonical, *concept.aliases]:
        normalized_label = normalize_term(label)
        label_tokens = set(tokenize(label))
        if normalized_label and normalized_label in normalized_query:
            score += 6.0
            reasons.append(f"Exact label match: {label}")
        overlap = label_tokens & query_tokens
        if overlap:
            score += 2.0 * len(overlap)
            reasons.append(f"Label token overlap: {', '.join(sorted(overlap))}")

    for hint in concept.query_hints:
        value = _query_hint_value(hint)
        overlap = set(tokenize(value)) & query_tokens
        if overlap:
            score += 2.5 * len(overlap)
            reasons.append(f"Query hint overlap: {value}")

    for relationship in concept.relationships:
        overlap = set(tokenize(relationship.target)) & query_tokens
        if overlap:
            score += 1.5 * len(overlap)
            reasons.append(
                f"Relationship overlap ({relationship.relationship_type}): {relationship.target}"
            )

    return score, unique_preserve(reasons)


def _section_id_from_requirement(requirement: str) -> str:
    normalized = normalize_term(requirement)
    if "comparison" in normalized:
        return "comparison"
    if "tradeoff" in normalized:
        return "tradeoffs"
    if "mechanism" in normalized:
        return "mechanism"
    if "definition" in normalized:
        return "definition"
    if "implementation" in normalized:
        return "implementation"
    return slugify(requirement)


def _titleize(value: str) -> str:
    return value.replace("-", " ").title()


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 1.0
    return round(numerator / denominator, 4)


def _baseline_match(model: OntologyModel, query: str) -> set[str]:
    normalized_query = normalize_term(query)
    matched: set[str] = set()
    for concept in model.concepts.values():
        if normalize_term(concept.canonical) in normalized_query:
            matched.add(concept.id)
    return matched


def _average_metrics(metrics: list[BenchmarkScenarioMetrics]) -> BenchmarkScenarioMetrics:
    if not metrics:
        return BenchmarkScenarioMetrics(
            concept_resolution_success=0.0,
            ontology_coverage=0.0,
            answer_completeness=0.0,
            terminology_consistency=0.0,
        )
    count = len(metrics)
    return BenchmarkScenarioMetrics(
        concept_resolution_success=round(
            sum(item.concept_resolution_success for item in metrics) / count, 4
        ),
        ontology_coverage=round(sum(item.ontology_coverage for item in metrics) / count, 4),
        answer_completeness=round(sum(item.answer_completeness for item in metrics) / count, 4),
        terminology_consistency=round(
            sum(item.terminology_consistency for item in metrics) / count, 4
        ),
    )
