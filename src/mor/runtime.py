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
    BundleDetails,
    BundleSummary,
    Concept,
    ConceptLink,
    ConceptReference,
    ConceptSummary,
    ExpandResponse,
    ExpansionEvidence,
    GraphPayload,
    QueryCoverageConcept,
    QueryCoverageResponse,
    QueryResolutionExplanation,
    QueryResolutionTrace,
    RelationshipPath,
    RelationshipPathStep,
    OntologyModel,
    OntologyAreaSummary,
    RuntimeMetadataResponse,
    OntologySelection,
    ResolveMatch,
    ResolveResponse,
    Relationship,
    ScaffoldResponse,
    ScaffoldConstraint,
    ScaffoldEvidenceSlot,
    ScaffoldSection,
    StatsResponse,
    ValidationReport,
    AmbiguousResolution,
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

    def metadata(self) -> RuntimeMetadataResponse:
        return RuntimeMetadataResponse(
            ontology_root=self.root,
            area_id=self.selection.area_id if self.selection else None,
            version=self.selection.version if self.selection else None,
            bundle_id=self.bundle_id(),
            metadata=self.selection.metadata if self.selection else None,
            version_metadata=self.selection.version_metadata if self.selection else None,
            structure=self.selection.structure if self.selection else None,
        )

    def bundle_id(self, area_id: str | None = None, version: str | None = None) -> str | None:
        resolved_area = area_id or (self.selection.area_id if self.selection else None)
        resolved_version = version or (self.selection.version if self.selection else None)
        if not resolved_area or not resolved_version:
            return None
        return _bundle_id(resolved_area, resolved_version)

    def list_concepts(self) -> list[ConceptSummary]:
        return sorted(
            [
                ConceptSummary(
                    id=concept.id,
                    canonical=concept.canonical,
                    aliases=concept.aliases,
                    related_count=len(concept.related_ids),
                    parent_count=len(concept.parent_ids),
                )
                for concept in self.model.concepts.values()
            ],
            key=lambda item: item.canonical,
        )

    def list_concepts_filtered(
        self,
        *,
        concept_type: str | None = None,
        bundle: str | None = None,
        area: str | None = None,
        version: str | None = None,
        tag: str | None = None,
    ) -> list[ConceptSummary]:
        target_runtime = self._runtime_for_filters(bundle=bundle, area=area, version=version)
        if target_runtime is not self:
            return target_runtime.list_concepts_filtered(concept_type=concept_type, tag=tag)

        if tag and not self._bundle_has_tag(tag):
            return []

        concepts = target_runtime.list_concepts()
        if concept_type is None:
            return concepts

        return [
            summary
            for summary in concepts
            if _concept_matches_type_filter(target_runtime.model.concepts[summary.id], concept_type)
        ]

    def list_areas(self) -> list[OntologyAreaSummary]:
        return list_ontology_areas(self.root)

    def get_concept(self, concept_id: str) -> Concept | None:
        return self.model.concepts.get(concept_id)

    def get_concept_by_term(self, concept_id_or_term: str) -> Concept | None:
        direct = self.model.concepts.get(concept_id_or_term)
        if direct is not None:
            return direct
        normalized = normalize_term(concept_id_or_term)
        canonical_id = self.model.canonical_index.get(normalized)
        if canonical_id:
            return self.model.concepts.get(canonical_id)
        resolution = self.resolve(concept_id_or_term)
        if resolution.matched and resolution.concept_id:
            return self.model.concepts.get(resolution.concept_id)
        return None

    def concept_source(self, concept_id: str) -> str | None:
        concept = self.get_concept(concept_id)
        if concept is None:
            return None
        return concept.source_path.read_text(encoding="utf-8")

    def list_bundles(self) -> list[BundleSummary]:
        areas = self.list_areas()
        if not areas and self.selection:
            bundle_id = self.bundle_id()
            if bundle_id is None:
                return []
            return [
                BundleSummary(
                    id=bundle_id,
                    area_id=self.selection.area_id or "default",
                    version=self.selection.version or "V1",
                    name=(self.selection.metadata.name if self.selection.metadata else self.selection.area_id or "Ontology"),
                    description=(
                        self.selection.version_metadata.description
                        if self.selection and self.selection.version_metadata
                        else "Ontology bundle."
                    ),
                    tags=self.selection.version_metadata.tags if self.selection and self.selection.version_metadata else [],
                    concept_count=len(self.model.concepts),
                    default=bool(self.selection.version_metadata.default) if self.selection and self.selection.version_metadata else False,
                )
            ]

        bundles: list[BundleSummary] = []
        for area_summary in areas:
            for version_name in area_summary.metadata.versions:
                selection = resolve_ontology_selection(self.root, area=area_summary.metadata.id, version=version_name)
                version_metadata = selection.version_metadata
                bundles.append(
                    BundleSummary(
                        id=_bundle_id(area_summary.metadata.id, version_name),
                        area_id=area_summary.metadata.id,
                        version=version_name,
                        name=version_metadata.name if version_metadata else area_summary.metadata.name,
                        description=version_metadata.description if version_metadata else area_summary.metadata.description,
                        tags=version_metadata.tags if version_metadata else area_summary.metadata.tags,
                        concept_count=len(list(selection.version_path.glob("*.md"))),
                        default=bool(version_metadata.default) if version_metadata else False,
                    )
                )
        return bundles

    def get_bundle(self, bundle_id: str) -> BundleDetails | None:
        parsed = _parse_bundle_id(bundle_id)
        if parsed is None:
            return None
        area_id, version = parsed
        runtime = self._runtime_for_filters(area=area_id, version=version)
        summary = next((item for item in self.list_bundles() if item.id == _bundle_id(area_id, version)), None)
        if summary is None:
            summary = BundleSummary(
                id=_bundle_id(area_id, version),
                area_id=area_id,
                version=version,
                name=runtime.selection.metadata.name if runtime.selection and runtime.selection.metadata else area_id,
                description=(
                    runtime.selection.version_metadata.description
                    if runtime.selection and runtime.selection.version_metadata
                    else "Ontology bundle."
                ),
                tags=runtime.selection.version_metadata.tags if runtime.selection and runtime.selection.version_metadata else [],
                concept_count=len(runtime.model.concepts),
                default=bool(runtime.selection.version_metadata.default) if runtime.selection and runtime.selection.version_metadata else False,
            )
        return BundleDetails(
            summary=summary,
            metadata=runtime.selection.metadata if runtime.selection else None,
            version_metadata=runtime.selection.version_metadata if runtime.selection else None,
            concepts=runtime.list_concepts(),
        )

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

    def get_related_concepts(
        self,
        concept_id_or_term: str,
        *,
        relationship_type: str | None = None,
        include_inferred: bool = True,
        include_incoming: bool = True,
    ) -> list[ConceptLink]:
        concept = self.get_concept_by_term(concept_id_or_term)
        if concept is None:
            return []

        links: list[ConceptLink] = []
        relationships = concept.all_relationships if include_inferred else concept.relationships
        for relationship in relationships:
            if relationship_type and relationship.relationship_type != relationship_type:
                continue
            links.append(
                ConceptLink(
                    relationship_type=relationship.relationship_type,
                    direction="outgoing",
                    target=self._concept_reference_from_relationship(relationship),
                    inferred=relationship.inferred,
                    rationale=f"{concept.canonical} {relationship.relationship_type} {relationship.target}.",
                )
            )

        for parent, parent_id in zip(concept.parents, concept.parent_ids, strict=False):
            if relationship_type and relationship_type != "parent":
                continue
            links.append(
                ConceptLink(
                    relationship_type="parent",
                    direction="outgoing",
                    target=self._concept_reference(parent_id, canonical_hint=parent),
                    rationale=f"{concept.canonical} is modeled under parent concept {parent}.",
                )
            )

        for label, target_id in zip(concept.not_same_as, concept.not_same_as_ids, strict=False):
            if relationship_type and relationship_type != "not_same_as":
                continue
            links.append(
                ConceptLink(
                    relationship_type="not_same_as",
                    direction="outgoing",
                    target=self._concept_reference(target_id, canonical_hint=label),
                    rationale=f"{concept.canonical} is explicitly distinguished from {label}.",
                )
            )

        if include_incoming:
            links.extend(
                self._incoming_links(
                    concept.id,
                    relationship_type=relationship_type,
                    include_inferred=include_inferred,
                )
            )

        unique_links: list[ConceptLink] = []
        seen: set[tuple[str, str, str, bool]] = set()
        for link in links:
            key = (
                link.direction,
                link.relationship_type,
                link.target.concept_id,
                link.inferred,
            )
            if key in seen:
                continue
            seen.add(key)
            unique_links.append(link)
        return unique_links

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
                        match_type="canonical" if normalize_term(concept.canonical) == normalized else "alias",
                        confidence=1.0 if normalize_term(concept.canonical) == normalized else 0.94,
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
                    match_type=(
                        "canonical"
                        if normalize_term(self.model.concepts[concept_id].canonical) == normalized
                        else "alias"
                    ),
                    confidence=0.7,
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
        resolved_concepts = [
            self._concept_reference(evidence.concept_id)
            for evidence in evidences
        ]
        suppressed_terms = [token for token in normalized_query.split() if token not in query_tokens]
        explanation = (
            "Expanded query using direct matches, ontology relations, and query hints."
            if evidences
            else "No ontology concepts matched the query."
        )
        return ExpandResponse(
            query=query,
            matched_concepts=evidences,
            expanded_terms=expanded_terms,
            resolved_concepts=resolved_concepts,
            suppressed_terms=unique_preserve(suppressed_terms),
            explanation=explanation,
        )

    def scaffold(
        self,
        intent: str,
        query: str | None = None,
        concept_ids: list[str] | None = None,
        *,
        include_evidence_slots: bool = False,
        include_constraints: bool = False,
        include_relationship_paths: bool = False,
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
        evidence_slots: list[ScaffoldEvidenceSlot] = []
        if include_evidence_slots:
            evidence_slots = [
                ScaffoldEvidenceSlot(
                    section_id=section.id,
                    label=(
                        f"Evidence for {section.title}: {'; '.join(section.source_concepts)}"
                        if section.source_concepts
                        else f"Evidence for {section.title}"
                    ),
                    concept_ids=[
                        self.model.canonical_index.get(normalize_term(canonical), "")
                        for canonical in section.source_concepts
                    ],
                )
                for section in sections
            ]
            for slot in evidence_slots:
                slot.concept_ids = [concept_id for concept_id in slot.concept_ids if concept_id]

        constraints: list[ScaffoldConstraint] = []
        if include_constraints:
            constraints.append(
                ScaffoldConstraint(
                    label="canonical_terminology",
                    details="Use canonical MOR concept names when describing resolved ontology concepts.",
                )
            )
            constraints.append(
                ScaffoldConstraint(
                    label="semantic_boundaries",
                    details="Respect explicit NotSameAs distinctions and do not merge differentiated concepts.",
                )
            )
            if query:
                coverage = self.compute_query_coverage(query)
                if coverage.coverage_score < 0.5:
                    constraints.append(
                        ScaffoldConstraint(
                            label="coverage_limit",
                            details=(
                                "Ontology coverage is partial for this query. "
                                f"Unresolved terms: {', '.join(coverage.unresolved_terms) or 'none'}."
                            ),
                        )
                    )

        relationship_paths = (
            self._relationship_paths_for_ids(selected_ids)
            if include_relationship_paths
            else []
        )
        explanation = (
            "Generated scaffold from intent defaults and concept answer requirements."
            if selected_concepts
            else "Generated scaffold from intent defaults."
        )
        return ScaffoldResponse(
            intent=intent,
            sections=sections,
            concepts=[concept.canonical for concept in selected_concepts],
            required_sections=section_ids,
            evidence_slots=evidence_slots,
            constraints=constraints,
            relationship_paths=relationship_paths,
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
        areas = self.list_areas()
        return StatsResponse(
            concept_count=len(self.model.concepts),
            alias_count=alias_count,
            relation_count=relation_count,
            hierarchy_edge_count=hierarchy_edge_count,
            orphan_count=orphan_count,
            validation_errors=self.report.errors,
            validation_warnings=self.report.warnings,
            validation_valid=self.report.valid,
            area_id=self.selection.area_id if self.selection else None,
            version=self.selection.version if self.selection else None,
            bundle_id=self.bundle_id(),
            bundle_count=(
                sum(len(area.metadata.versions) for area in areas)
                if areas
                else (1 if self.selection else 0)
            ),
            area_count=len(areas) if areas else (1 if self.selection else 0),
            structure_id=self.selection.structure.id if self.selection and self.selection.structure else None,
        )

    def explain_query_resolution(
        self,
        query: str,
        *,
        max_expanded_concepts: int = 5,
    ) -> QueryResolutionExplanation:
        normalized_query = normalize_term(query)
        significant_tokens = tokenize(query)
        suppressed_terms = [token for token in normalized_query.split() if token not in significant_tokens]

        traces: dict[tuple[str, str], QueryResolutionTrace] = {}
        ambiguities: dict[str, AmbiguousResolution] = {}
        detected_terms: list[str] = []

        for label, concept_ids in self.model.label_index.items():
            if not label or not _contains_normalized_phrase(normalized_query, label):
                continue
            detected_terms.append(label)
            if len(concept_ids) == 1:
                concept = self.model.concepts[concept_ids[0]]
                match_type = "canonical" if normalize_term(concept.canonical) == label else "alias"
                traces[(label, concept.id)] = QueryResolutionTrace(
                    term=label,
                    concept=self._concept_reference(concept.id),
                    matched_label=_matching_label(concept, label),
                    match_type=match_type,
                    confidence=1.0 if match_type == "canonical" else 0.92,
                )
            else:
                ambiguities[label] = AmbiguousResolution(
                    term=label,
                    matches=[
                        ResolveMatch(
                            concept_id=concept_id,
                            canonical=self.model.concepts[concept_id].canonical,
                            matched_label=_matching_label(self.model.concepts[concept_id], label),
                            match_type=(
                                "canonical"
                                if normalize_term(self.model.concepts[concept_id].canonical) == label
                                else "alias"
                            ),
                            confidence=0.68,
                        )
                        for concept_id in concept_ids
                    ],
                    rationale=f"The term '{label}' maps to multiple ontology concepts.",
                )

        for token in significant_tokens:
            matches = self.model.label_index.get(token, [])
            if not matches:
                continue
            detected_terms.append(token)
            if len(matches) == 1:
                concept = self.model.concepts[matches[0]]
                traces.setdefault(
                    (token, concept.id),
                    QueryResolutionTrace(
                        term=token,
                        concept=self._concept_reference(concept.id),
                        matched_label=_matching_label(concept, token),
                        match_type="canonical" if normalize_term(concept.canonical) == token else "alias",
                        confidence=0.84 if normalize_term(concept.canonical) == token else 0.78,
                    ),
                )
            else:
                ambiguities.setdefault(
                    token,
                    AmbiguousResolution(
                        term=token,
                        matches=[
                            ResolveMatch(
                                concept_id=concept_id,
                                canonical=self.model.concepts[concept_id].canonical,
                                matched_label=_matching_label(self.model.concepts[concept_id], token),
                                match_type=(
                                    "canonical"
                                    if normalize_term(self.model.concepts[concept_id].canonical) == token
                                    else "alias"
                                ),
                                confidence=0.6,
                            )
                            for concept_id in matches
                        ],
                        rationale=f"The token '{token}' is ambiguous in the ontology label index.",
                    ),
                )

        canonical_matches = [
            trace for trace in traces.values() if trace.match_type == "canonical"
        ]
        alias_matches = [trace for trace in traces.values() if trace.match_type == "alias"]
        matched_token_set = {
            token
            for term in detected_terms
            for token in term.split()
        }
        unmatched_terms = [
            token
            for token in significant_tokens
            if token not in matched_token_set and token not in ambiguities
        ]

        expansion = self.expand(query, max_concepts=max_expanded_concepts)
        relationship_paths = self._relationship_paths_for_ids(
            [item.concept_id for item in expansion.matched_concepts]
        )
        notes = _build_query_resolution_notes(
            canonical_matches=canonical_matches,
            alias_matches=alias_matches,
            ambiguities=list(ambiguities.values()),
            unmatched_terms=unmatched_terms,
            relationship_paths=relationship_paths,
        )
        return QueryResolutionExplanation(
            query=query,
            detected_terms=unique_preserve(detected_terms),
            canonical_matches=sorted(canonical_matches, key=lambda item: (-item.confidence, item.term)),
            alias_matches=sorted(alias_matches, key=lambda item: (-item.confidence, item.term)),
            unmatched_terms=unique_preserve(unmatched_terms),
            ambiguous_matches=sorted(ambiguities.values(), key=lambda item: item.term),
            expanded_concepts=expansion.matched_concepts,
            relationship_paths=relationship_paths,
            suppressed_terms=unique_preserve(suppressed_terms),
            notes=notes,
            rationale=_query_resolution_rationale(canonical_matches, alias_matches, ambiguities, unmatched_terms),
        )

    def compute_query_coverage(self, query: str) -> QueryCoverageResponse:
        explanation = self.explain_query_resolution(query)
        coverage_by_concept: dict[str, QueryCoverageConcept] = {}
        covered_terms: list[str] = []

        for trace in [*explanation.canonical_matches, *explanation.alias_matches]:
            concept_id = trace.concept.concept_id
            covered_terms.append(trace.term)
            item = coverage_by_concept.setdefault(
                concept_id,
                QueryCoverageConcept(concept=trace.concept, matched_terms=[]),
            )
            if trace.term not in item.matched_terms:
                item.matched_terms.append(trace.term)

        significant_tokens = tokenize(query)
        covered_token_count = len(
            {
                token
                for term in covered_terms
                for token in term.split()
                if token in significant_tokens
            }
        )
        total_tokens = len(significant_tokens)
        coverage_score = round(covered_token_count / total_tokens, 4) if total_tokens else 0.0
        unresolved_terms = unique_preserve(
            [*explanation.unmatched_terms, *(item.term for item in explanation.ambiguous_matches)]
        )
        return QueryCoverageResponse(
            query=query,
            covered_concepts=list(coverage_by_concept.values()),
            covered_terms=unique_preserve(covered_terms),
            unresolved_terms=unresolved_terms,
            suppressed_terms=explanation.suppressed_terms,
            coverage_score=coverage_score,
            explanation=_coverage_explanation(coverage_score, coverage_by_concept, unresolved_terms),
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

    def _runtime_for_filters(
        self,
        *,
        bundle: str | None = None,
        area: str | None = None,
        version: str | None = None,
    ) -> "OntologyRuntime":
        target_area = area
        target_version = version
        if bundle:
            parsed = _parse_bundle_id(bundle)
            if parsed is None:
                raise ValueError(f"Unknown bundle '{bundle}'. Expected '<area>@<version>'.")
            target_area, target_version = parsed
        if not target_area and not target_version:
            return self
        if (
            target_area == (self.selection.area_id if self.selection else None)
            and target_version == (self.selection.version if self.selection else None)
        ):
            return self
        return OntologyRuntime(self.root, area=target_area, version=target_version)

    def _bundle_has_tag(self, tag: str) -> bool:
        if self.selection is None:
            return False
        bundle_tags = self.selection.version_metadata.tags if self.selection.version_metadata else []
        if not bundle_tags and self.selection.metadata:
            bundle_tags = self.selection.metadata.tags
        return normalize_term(tag) in {normalize_term(item) for item in bundle_tags}

    def _concept_reference(self, concept_id: str | None, canonical_hint: str | None = None) -> ConceptReference:
        if concept_id and concept_id in self.model.concepts:
            concept = self.model.concepts[concept_id]
            return ConceptReference(
                concept_id=concept.id,
                canonical=concept.canonical,
                title=concept.title,
                uri=f"ontology://concept/{concept.id}",
            )
        fallback = canonical_hint or concept_id or "unknown"
        return ConceptReference(
            concept_id=concept_id or slugify(fallback),
            canonical=fallback,
            title=None,
            uri=None,
        )

    def _concept_reference_from_relationship(self, relationship: Relationship) -> ConceptReference:
        return self._concept_reference(relationship.target_id, canonical_hint=relationship.target)

    def _incoming_links(
        self,
        concept_id: str,
        *,
        relationship_type: str | None = None,
        include_inferred: bool = True,
    ) -> list[ConceptLink]:
        links: list[ConceptLink] = []
        for source in self.model.concepts.values():
            relationships = source.all_relationships if include_inferred else source.relationships
            for relationship in relationships:
                if relationship.target_id != concept_id:
                    continue
                if relationship_type and relationship.relationship_type != relationship_type:
                    continue
                links.append(
                    ConceptLink(
                        relationship_type=relationship.relationship_type,
                        direction="incoming",
                        target=self._concept_reference(source.id),
                        inferred=relationship.inferred,
                        rationale=f"{source.canonical} links to the requested concept via {relationship.relationship_type}.",
                    )
                )
            if (not relationship_type or relationship_type == "parent") and concept_id in source.parent_ids:
                links.append(
                    ConceptLink(
                        relationship_type="child",
                        direction="incoming",
                        target=self._concept_reference(source.id),
                        rationale=f"{source.canonical} is modeled under the requested concept.",
                    )
                )
            if (not relationship_type or relationship_type == "not_same_as") and concept_id in source.not_same_as_ids:
                links.append(
                    ConceptLink(
                        relationship_type="not_same_as",
                        direction="incoming",
                        target=self._concept_reference(source.id),
                        rationale=f"{source.canonical} is explicitly distinguished from the requested concept.",
                    )
                )
        return links

    def _relationship_paths_for_ids(
        self,
        concept_ids: list[str],
        *,
        limit: int = 6,
    ) -> list[RelationshipPath]:
        ordered_ids = [concept_id for concept_id in unique_preserve(concept_ids) if concept_id in self.model.concepts]
        if len(ordered_ids) < 2:
            return []

        paths: list[RelationshipPath] = []
        seen: set[tuple[str, str, str]] = set()
        for source_id in ordered_ids:
            for target_id in ordered_ids:
                if source_id == target_id:
                    continue
                direct = self._direct_path(source_id, target_id)
                if direct is not None:
                    key = (
                        source_id,
                        target_id,
                        "->".join(step.relationship_type for step in direct.steps),
                    )
                    if key not in seen:
                        seen.add(key)
                        paths.append(direct)
                        if len(paths) >= limit:
                            return paths
                    continue
                for intermediate_id in ordered_ids:
                    if intermediate_id in {source_id, target_id}:
                        continue
                    first = self._direct_path(source_id, intermediate_id)
                    second = self._direct_path(intermediate_id, target_id)
                    if first is None or second is None:
                        continue
                    combined = RelationshipPath(
                        source=self._concept_reference(source_id),
                        target=self._concept_reference(target_id),
                        steps=[*first.steps, *second.steps],
                        rationale=(
                            f"{self.model.concepts[source_id].canonical} reaches "
                            f"{self.model.concepts[target_id].canonical} via "
                            f"{self.model.concepts[intermediate_id].canonical}."
                        ),
                    )
                    key = (
                        source_id,
                        target_id,
                        "->".join(step.relationship_type for step in combined.steps),
                    )
                    if key in seen:
                        continue
                    seen.add(key)
                    paths.append(combined)
                    if len(paths) >= limit:
                        return paths
        return paths

    def _direct_path(self, source_id: str, target_id: str) -> RelationshipPath | None:
        source = self.model.concepts[source_id]
        for relationship in source.all_relationships:
            if relationship.target_id != target_id:
                continue
            return RelationshipPath(
                source=self._concept_reference(source_id),
                target=self._concept_reference(target_id),
                steps=[
                    RelationshipPathStep(
                        source=self._concept_reference(source_id),
                        relationship_type=relationship.relationship_type,
                        target=self._concept_reference(target_id),
                        inferred=relationship.inferred,
                    )
                ],
                rationale=(
                    f"{source.canonical} connects directly to "
                    f"{self.model.concepts[target_id].canonical} via {relationship.relationship_type}."
                ),
            )

        if target_id in source.parent_ids:
            return RelationshipPath(
                source=self._concept_reference(source_id),
                target=self._concept_reference(target_id),
                steps=[
                    RelationshipPathStep(
                        source=self._concept_reference(source_id),
                        relationship_type="parent",
                        target=self._concept_reference(target_id),
                    )
                ],
                rationale=(
                    f"{source.canonical} connects directly to "
                    f"{self.model.concepts[target_id].canonical} through the parent hierarchy."
                ),
            )
        return None

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
                    match_type="alternative",
                    confidence=0.5,
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


def _contains_normalized_phrase(query: str, phrase: str) -> bool:
    return f" {phrase} " in f" {query} "


def _bundle_id(area_id: str, version: str) -> str:
    return f"{area_id}@{version.upper()}"


def _parse_bundle_id(value: str) -> tuple[str, str] | None:
    if "@" not in value:
        return None
    area_id, version = value.split("@", 1)
    if not area_id or not version:
        return None
    return area_id, version.upper()


def _concept_matches_type_filter(concept: Concept, concept_type: str) -> bool:
    normalized = normalize_term(concept_type)
    candidates = {
        normalize_term(concept.id),
        normalize_term(concept.canonical),
        normalize_term(concept.title),
        *(normalize_term(parent) for parent in concept.parents),
    }
    return normalized in candidates


def _build_query_resolution_notes(
    *,
    canonical_matches: list[QueryResolutionTrace],
    alias_matches: list[QueryResolutionTrace],
    ambiguities: list[AmbiguousResolution],
    unmatched_terms: list[str],
    relationship_paths: list[RelationshipPath],
) -> list[str]:
    notes: list[str] = []
    if canonical_matches:
        notes.append(
            "Canonical matches anchor the interpretation: "
            + ", ".join(trace.concept.canonical for trace in canonical_matches[:4])
            + "."
        )
    if alias_matches:
        notes.append(
            "Alias matches were normalized to canonical concepts: "
            + ", ".join(trace.concept.canonical for trace in alias_matches[:4])
            + "."
        )
    if ambiguities:
        notes.append(
            "Ambiguous ontology terms remain and may need follow-up resolution: "
            + ", ".join(item.term for item in ambiguities[:4])
            + "."
        )
    if relationship_paths:
        notes.append("Relationship paths were found between expanded concepts and can guide answer structure.")
    if unmatched_terms:
        notes.append(
            "Some query terms were not covered by ontology labels: "
            + ", ".join(unmatched_terms[:6])
            + "."
        )
    if not notes:
        notes.append("The query did not produce strong ontology matches.")
    return notes


def _query_resolution_rationale(
    canonical_matches: list[QueryResolutionTrace],
    alias_matches: list[QueryResolutionTrace],
    ambiguities: dict[str, AmbiguousResolution],
    unmatched_terms: list[str],
) -> str:
    if canonical_matches or alias_matches:
        if ambiguities:
            return "The query was partially grounded in ontology concepts, but some terms remain ambiguous."
        if unmatched_terms:
            return "The query was grounded in ontology concepts with partial lexical coverage."
        return "The query was grounded in ontology concepts using direct canonical and alias matches."
    if ambiguities:
        return "The ontology recognized terms in the query, but they remain ambiguous."
    return "The ontology found limited direct support for the query."


def _coverage_explanation(
    coverage_score: float,
    coverage_by_concept: dict[str, QueryCoverageConcept],
    unresolved_terms: list[str],
) -> str:
    if coverage_score >= 0.75:
        return "Most of the query is covered by explicit ontology concepts."
    if coverage_score >= 0.4:
        return "The ontology covers part of the query, but some concepts remain outside the model."
    if coverage_by_concept:
        return (
            "The ontology found only limited concept coverage. "
            f"Unresolved terms: {', '.join(unresolved_terms) or 'none'}."
        )
    return "The ontology could not confidently cover the query."


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
        if normalized_label and _contains_normalized_phrase(normalized_query, normalized_label):
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
