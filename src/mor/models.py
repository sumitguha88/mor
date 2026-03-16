"""Typed models used across MOR."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ValidationIssue(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    severity: Literal["error", "warning"]
    code: str
    message: str
    source_path: Path | None = None
    concept_id: str | None = None
    section: str | None = None
    line: int | None = None
    details: dict[str, object] = Field(default_factory=dict)


class ValidationReport(BaseModel):
    valid: bool
    errors: int
    warnings: int
    issues: list[ValidationIssue]

    @classmethod
    def from_issues(cls, issues: list[ValidationIssue]) -> "ValidationReport":
        errors = sum(1 for issue in issues if issue.severity == "error")
        warnings = sum(1 for issue in issues if issue.severity == "warning")
        return cls(valid=errors == 0, errors=errors, warnings=warnings, issues=issues)

    def errors_for_concept(self, concept_id: str | None) -> list[ValidationIssue]:
        if concept_id is None:
            return []
        return [
            issue for issue in self.issues if issue.severity == "error" and issue.concept_id == concept_id
        ]

    def errors_for_path(self, source_path: Path) -> list[ValidationIssue]:
        return [
            issue for issue in self.issues if issue.severity == "error" and issue.source_path == source_path
        ]


class ConceptDraft(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    source_path: Path
    title: str
    concept_id: str
    canonical: str | None = None
    aliases: list[str] = Field(default_factory=list)
    definition: str | None = None
    relationships: list["RelationshipDraft"] = Field(default_factory=list)
    related: list[str] = Field(default_factory=list)
    parents: list[str] = Field(default_factory=list)
    not_same_as: list[str] = Field(default_factory=list)
    query_hints: list[str] = Field(default_factory=list)
    answer_requirements: list[str] = Field(default_factory=list)
    sections_present: set[str] = Field(default_factory=set)
    parse_issues: list[ValidationIssue] = Field(default_factory=list)

    @property
    def all_labels(self) -> list[str]:
        labels = [self.canonical] if self.canonical else [self.title]
        labels.extend(self.aliases)
        return [label for label in labels if label]


class Concept(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, str_strip_whitespace=True)

    id: str
    title: str
    source_path: Path
    canonical: str
    aliases: list[str] = Field(default_factory=list)
    definition: str
    relationships: list["Relationship"] = Field(default_factory=list)
    inferred_relationships: list["Relationship"] = Field(default_factory=list)
    related: list[str] = Field(default_factory=list)
    related_ids: list[str] = Field(default_factory=list)
    parents: list[str] = Field(default_factory=list)
    parent_ids: list[str] = Field(default_factory=list)
    not_same_as: list[str] = Field(default_factory=list)
    not_same_as_ids: list[str] = Field(default_factory=list)
    query_hints: list[str] = Field(default_factory=list)
    answer_requirements: list[str] = Field(default_factory=list)

    @property
    def all_relationships(self) -> list["Relationship"]:
        return [*self.relationships, *self.inferred_relationships]


class OntologyModel(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    root: Path
    area_id: str | None = None
    version: str | None = None
    concepts: dict[str, Concept]
    canonical_index: dict[str, str]
    label_index: dict[str, list[str]]


class RelationshipDraft(BaseModel):
    relationship_type: str
    target: str


class Relationship(BaseModel):
    relationship_type: str
    target: str
    target_id: str | None = None
    inferred: bool = False


class OntologyMetadata(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    id: str
    name: str
    description: str
    domain: str | None = None
    default: bool = False
    default_version: str = "V1"
    versions: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class OntologyVersionMetadata(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    id: str
    name: str
    description: str
    version: str
    structure: str
    domain: str | None = None
    default: bool = False
    is_default_version: bool = False
    tags: list[str] = Field(default_factory=list)


class OntologyStructure(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    id: str
    name: str
    description: str
    concept_header_prefix: str = "# Concept:"
    required_sections: list[str] = Field(default_factory=list)
    optional_sections: list[str] = Field(default_factory=list)
    list_sections: list[str] = Field(default_factory=list)
    text_sections: list[str] = Field(default_factory=list)
    canonical_section: str = "Canonical"
    aliases_section: str = "Aliases"
    definition_section: str = "Definition"
    relationship_section: str = "Related"
    parents_section: str = "Parents"
    not_same_as_section: str = "NotSameAs"
    query_hints_section: str = "QueryHints"
    answer_requirements_section: str = "AnswerRequirements"
    relationship_type_keys: list[str] = Field(default_factory=lambda: ["type", "relationship", "predicate"])
    relationship_target_keys: list[str] = Field(default_factory=lambda: ["concept", "entity", "target"])
    inverse_relationships: dict[str, str] = Field(default_factory=dict)

    @property
    def all_sections(self) -> list[str]:
        return [*self.required_sections, *self.optional_sections]


class OntologySelection(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    requested_root: Path
    area_id: str | None = None
    version: str | None = None
    metadata: OntologyMetadata | None = None
    version_metadata: OntologyVersionMetadata | None = None
    structure: OntologyStructure | None = None
    area_path: Path | None = None
    version_path: Path


class OntologyAreaSummary(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    area_path: Path
    metadata: OntologyMetadata


class GraphNode(BaseModel):
    id: str
    label: str
    group: str
    title: str
    properties: dict[str, Any] = Field(default_factory=dict)
    value: float = 1.0


class GraphEdge(BaseModel):
    source: str
    target: str
    relation: str
    title: str
    arrows: str | None = None
    dashes: bool = False
    inferred: bool = False


class GraphPayload(BaseModel):
    area_id: str | None = None
    version: str | None = None
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class ConceptSummary(BaseModel):
    id: str
    canonical: str
    aliases: list[str]
    related_count: int
    parent_count: int


class ConceptReference(BaseModel):
    concept_id: str
    canonical: str
    title: str | None = None
    uri: str | None = None


class ConceptLink(BaseModel):
    relationship_type: str
    direction: Literal["outgoing", "incoming"]
    target: ConceptReference
    inferred: bool = False
    source_label: str | None = None
    rationale: str | None = None


class ResolveMatch(BaseModel):
    concept_id: str
    canonical: str
    matched_label: str
    match_type: Literal["canonical", "alias", "alternative"] = "canonical"
    confidence: float = 1.0


class ResolveResponse(BaseModel):
    term: str
    matched: bool
    ambiguous: bool = False
    concept_id: str | None = None
    canonical: str | None = None
    matches: list[ResolveMatch] = Field(default_factory=list)
    alternatives: list[ResolveMatch] = Field(default_factory=list)
    explanation: str


class ExpansionEvidence(BaseModel):
    concept_id: str
    canonical: str
    score: float
    reasons: list[str]


class ExpandResponse(BaseModel):
    query: str
    matched_concepts: list[ExpansionEvidence]
    expanded_terms: list[str]
    resolved_concepts: list[ConceptReference] = Field(default_factory=list)
    suppressed_terms: list[str] = Field(default_factory=list)
    explanation: str


class RelationshipPathStep(BaseModel):
    source: ConceptReference
    relationship_type: str
    target: ConceptReference
    inferred: bool = False


class RelationshipPath(BaseModel):
    source: ConceptReference
    target: ConceptReference
    steps: list[RelationshipPathStep]
    rationale: str


class QueryResolutionTrace(BaseModel):
    term: str
    concept: ConceptReference
    matched_label: str
    match_type: Literal["canonical", "alias"]
    confidence: float


class AmbiguousResolution(BaseModel):
    term: str
    matches: list[ResolveMatch]
    rationale: str


class QueryCoverageConcept(BaseModel):
    concept: ConceptReference
    matched_terms: list[str] = Field(default_factory=list)


class QueryCoverageResponse(BaseModel):
    query: str
    covered_concepts: list[QueryCoverageConcept]
    covered_terms: list[str]
    unresolved_terms: list[str]
    suppressed_terms: list[str] = Field(default_factory=list)
    coverage_score: float
    explanation: str


class QueryResolutionExplanation(BaseModel):
    query: str
    detected_terms: list[str]
    canonical_matches: list[QueryResolutionTrace]
    alias_matches: list[QueryResolutionTrace]
    unmatched_terms: list[str]
    ambiguous_matches: list[AmbiguousResolution]
    expanded_concepts: list[ExpansionEvidence]
    relationship_paths: list[RelationshipPath]
    suppressed_terms: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    rationale: str


class ScaffoldEvidenceSlot(BaseModel):
    section_id: str
    label: str
    concept_ids: list[str] = Field(default_factory=list)


class ScaffoldConstraint(BaseModel):
    label: str
    details: str


class ScaffoldSection(BaseModel):
    id: str
    title: str
    rationale: str
    source_concepts: list[str] = Field(default_factory=list)


class ScaffoldResponse(BaseModel):
    intent: str
    sections: list[ScaffoldSection]
    concepts: list[str]
    required_sections: list[str] = Field(default_factory=list)
    evidence_slots: list[ScaffoldEvidenceSlot] = Field(default_factory=list)
    constraints: list[ScaffoldConstraint] = Field(default_factory=list)
    relationship_paths: list[RelationshipPath] = Field(default_factory=list)
    explanation: str


class StatsResponse(BaseModel):
    concept_count: int
    alias_count: int
    relation_count: int
    hierarchy_edge_count: int
    orphan_count: int
    validation_errors: int
    validation_warnings: int
    validation_valid: bool = True
    area_id: str | None = None
    version: str | None = None
    bundle_id: str | None = None
    bundle_count: int = 0
    area_count: int = 0
    structure_id: str | None = None


class RuntimeMetadataResponse(BaseModel):
    ontology_root: Path
    area_id: str | None = None
    version: str | None = None
    bundle_id: str | None = None
    metadata: OntologyMetadata | None = None
    version_metadata: OntologyVersionMetadata | None = None
    structure: OntologyStructure | None = None


class BundleSummary(BaseModel):
    id: str
    area_id: str
    version: str
    name: str
    description: str
    tags: list[str] = Field(default_factory=list)
    concept_count: int | None = None
    default: bool = False


class BundleDetails(BaseModel):
    summary: BundleSummary
    metadata: OntologyMetadata | None = None
    version_metadata: OntologyVersionMetadata | None = None
    concepts: list[ConceptSummary] = Field(default_factory=list)


class BenchmarkCase(BaseModel):
    name: str
    query: str
    intent: str = "architecture_explanation"
    expected_concepts: list[str] = Field(default_factory=list)
    expected_sections: list[str] = Field(default_factory=list)
    expected_terms: list[str] = Field(default_factory=list)


class BenchmarkScenarioMetrics(BaseModel):
    concept_resolution_success: float
    ontology_coverage: float
    answer_completeness: float
    terminology_consistency: float


class BenchmarkCaseResult(BaseModel):
    name: str
    baseline: BenchmarkScenarioMetrics
    ontology_assisted: BenchmarkScenarioMetrics


class BenchmarkSummary(BaseModel):
    cases: list[BenchmarkCaseResult]
    aggregate_baseline: BenchmarkScenarioMetrics
    aggregate_ontology_assisted: BenchmarkScenarioMetrics


class EvalDatasetItem(BaseModel):
    id: str
    input: dict[str, Any]
    expected_output: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvalScore(BaseModel):
    name: str
    value: int | float | str | bool
    comment: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvalTaskOutput(BaseModel):
    query: str
    answer: str
    mode: Literal["baseline", "ontology_assisted"]
    provider: str
    model: str
    area: str | None = None
    version: str | None = None
    matched_concepts: list[str] = Field(default_factory=list)
    expanded_terms: list[str] = Field(default_factory=list)
    scaffold_sections: list[str] = Field(default_factory=list)
    prompt_preview: str | None = None


class EvalItemResult(BaseModel):
    item_id: str
    output: EvalTaskOutput
    evaluations: list[EvalScore] = Field(default_factory=list)


class EvalRunSummary(BaseModel):
    experiment_name: str
    run_name: str
    mode: Literal["baseline", "ontology_assisted"]
    provider: str
    model: str
    item_results: list[EvalItemResult] = Field(default_factory=list)
    run_evaluations: list[EvalScore] = Field(default_factory=list)
    dataset_run_id: str | None = None
    dataset_run_url: str | None = None


class EvalDatasetUploadSummary(BaseModel):
    dataset_name: str
    dataset_description: str | None = None
    item_count: int
    item_ids: list[str] = Field(default_factory=list)


class ResolveRequest(BaseModel):
    term: str


class ExpandRequest(BaseModel):
    query: str
    max_concepts: int = 5
    max_terms: int = 12


class ScaffoldRequest(BaseModel):
    intent: str
    query: str | None = None
    concept_ids: list[str] = Field(default_factory=list)


class ValidateRequest(BaseModel):
    reload: bool = True
