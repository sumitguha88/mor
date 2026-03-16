"""Ontology validation logic."""

from __future__ import annotations

from collections import defaultdict

from mor.models import ConceptDraft, OntologyStructure, ValidationIssue, ValidationReport
from mor.registry import default_ontology_structure
from mor.utils import normalize_term


def validate_drafts(
    drafts: list[ConceptDraft],
    structure: OntologyStructure | None = None,
) -> ValidationReport:
    structure = structure or default_ontology_structure()
    issues: list[ValidationIssue] = []
    for draft in drafts:
        issues.extend(draft.parse_issues)
        for section in structure.required_sections:
            if section not in draft.sections_present:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        code="missing_section",
                        message=f"Missing required section '{section}'.",
                        source_path=draft.source_path,
                        concept_id=draft.concept_id,
                        section=section,
                    )
                )
        if structure.canonical_section in draft.sections_present and not draft.canonical:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="empty_section",
                    message="Canonical section must contain a value.",
                    source_path=draft.source_path,
                    concept_id=draft.concept_id,
                    section=structure.canonical_section,
                )
            )
        if structure.definition_section in draft.sections_present and not draft.definition:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="empty_section",
                    message="Definition section must contain a value.",
                    source_path=draft.source_path,
                    concept_id=draft.concept_id,
                    section=structure.definition_section,
                )
            )

    label_index = _build_label_index(drafts)
    issues.extend(_validate_alias_conflicts(drafts, label_index))
    issues.extend(_validate_references(drafts, label_index))
    issues.extend(_validate_circular_hierarchies(drafts, label_index))
    issues.extend(_validate_orphans(drafts, label_index))
    return ValidationReport.from_issues(issues)


def _build_label_index(drafts: list[ConceptDraft]) -> dict[str, list[str]]:
    label_index: dict[str, set[str]] = defaultdict(set)
    for draft in drafts:
        for label in draft.all_labels:
            normalized = normalize_term(label)
            if normalized:
                label_index[normalized].add(draft.concept_id)
    return {key: sorted(value) for key, value in label_index.items()}


def _validate_alias_conflicts(
    drafts: list[ConceptDraft], label_index: dict[str, list[str]]
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for normalized_label, concept_ids in label_index.items():
        if len(concept_ids) < 2:
            continue
        for concept_id in concept_ids:
            draft = next(draft for draft in drafts if draft.concept_id == concept_id)
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="alias_conflict",
                    message=f"Label '{normalized_label}' maps to multiple concepts: {', '.join(concept_ids)}.",
                    source_path=draft.source_path,
                    concept_id=draft.concept_id,
                )
            )
    return issues


def _validate_references(
    drafts: list[ConceptDraft], label_index: dict[str, list[str]]
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for draft in drafts:
        for section_name, references in (
            ("Related", [relationship.target for relationship in draft.relationships]),
            ("Parents", draft.parents),
            ("NotSameAs", draft.not_same_as),
        ):
            for reference in references:
                normalized = normalize_term(reference)
                matches = label_index.get(normalized, [])
                if not matches:
                    issues.append(
                        ValidationIssue(
                            severity="error",
                            code="broken_reference",
                            message=f"Reference '{reference}' in {section_name} does not resolve.",
                            source_path=draft.source_path,
                            concept_id=draft.concept_id,
                            section=section_name,
                            details={"reference": reference},
                        )
                    )
                elif len(matches) > 1:
                    issues.append(
                        ValidationIssue(
                            severity="warning",
                            code="ambiguous_reference",
                            message=f"Reference '{reference}' in {section_name} resolves to multiple concepts.",
                            source_path=draft.source_path,
                            concept_id=draft.concept_id,
                            section=section_name,
                            details={"reference": reference, "matches": matches},
                        )
                    )
    return issues


def _validate_circular_hierarchies(
    drafts: list[ConceptDraft], label_index: dict[str, list[str]]
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    graph: dict[str, list[str]] = defaultdict(list)
    draft_index = {draft.concept_id: draft for draft in drafts}
    for draft in drafts:
        for parent in draft.parents:
            matches = label_index.get(normalize_term(parent), [])
            if len(matches) == 1:
                graph[draft.concept_id].append(matches[0])

    cycle_keys: set[tuple[str, ...]] = set()
    for start in graph:
        _dfs_cycles(start, graph, draft_index, [], set(), cycle_keys, issues)
    return issues


def _dfs_cycles(
    current: str,
    graph: dict[str, list[str]],
    draft_index: dict[str, ConceptDraft],
    path: list[str],
    seen: set[str],
    cycle_keys: set[tuple[str, ...]],
    issues: list[ValidationIssue],
) -> None:
    if current in seen:
        cycle_start = path.index(current)
        cycle = path[cycle_start:] + [current]
        cycle_key = tuple(sorted(set(cycle)))
        if cycle_key in cycle_keys:
            return
        cycle_keys.add(cycle_key)
        for concept_id in set(cycle):
            draft = draft_index[concept_id]
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="circular_hierarchy",
                    message=f"Circular parent hierarchy detected: {' -> '.join(cycle)}.",
                    source_path=draft.source_path,
                    concept_id=concept_id,
                )
            )
        return

    path.append(current)
    seen.add(current)
    for neighbor in graph.get(current, []):
        _dfs_cycles(neighbor, graph, draft_index, path, seen.copy(), cycle_keys, issues)
    path.pop()


def _validate_orphans(
    drafts: list[ConceptDraft], label_index: dict[str, list[str]]
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    inbound: dict[str, int] = defaultdict(int)
    outbound: dict[str, int] = defaultdict(int)
    for draft in drafts:
        references = [relationship.target for relationship in draft.relationships] + draft.parents + draft.not_same_as
        for reference in references:
            matches = label_index.get(normalize_term(reference), [])
            if len(matches) == 1:
                outbound[draft.concept_id] += 1
                inbound[matches[0]] += 1

    for draft in drafts:
        if inbound[draft.concept_id] == 0 and outbound[draft.concept_id] == 0:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    code="orphan_concept",
                    message="Concept is orphaned; it has no resolved inbound or outbound links.",
                    source_path=draft.source_path,
                    concept_id=draft.concept_id,
                )
            )
    return issues
