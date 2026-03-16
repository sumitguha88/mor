"""Markdown ontology parser."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from mor.models import ConceptDraft, OntologyStructure, RelationshipDraft, ValidationIssue
from mor.registry import default_ontology_structure, resolve_ontology_selection
from mor.utils import slugify

_SECTION_RE = re.compile(r"^##\s+([A-Za-z][A-Za-z0-9 ]*)\s*$")


def parse_concept_file(path: Path, structure: OntologyStructure | None = None) -> ConceptDraft:
    structure = structure or default_ontology_structure()
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    issues: list[ValidationIssue] = []
    sections_raw: dict[str, list[tuple[int, str]]] = defaultdict(list)
    sections_present: set[str] = set()

    title = path.stem.replace("-", " ")
    title = title.title()
    current_section: str | None = None
    header_seen = False

    for line_no, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not header_seen:
            if not stripped:
                continue
            header_match = _header_re(structure.concept_header_prefix).match(stripped)
            if header_match:
                title = header_match.group(1).strip()
                header_seen = True
                continue
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="invalid_markdown_structure",
                    message=f"Expected '{structure.concept_header_prefix} <name>' as the first heading.",
                    source_path=path,
                    line=line_no,
                )
            )
            header_seen = True

        section_match = _SECTION_RE.match(stripped)
        if section_match:
            current_section = section_match.group(1).strip()
            if current_section in sections_present:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        code="invalid_markdown_structure",
                        message=f"Section '{current_section}' appears more than once.",
                        source_path=path,
                        line=line_no,
                        section=current_section,
                    )
                )
            sections_present.add(current_section)
            if current_section not in set(structure.all_sections):
                issues.append(
                    ValidationIssue(
                        severity="error",
                        code="unknown_section",
                        message=f"Unsupported section '{current_section}'.",
                        source_path=path,
                        line=line_no,
                        section=current_section,
                    )
                )
            continue

        if stripped.startswith("#") and not stripped.startswith("## "):
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="invalid_markdown_structure",
                    message="Only one '# Concept:' header and '##' section headers are allowed.",
                    source_path=path,
                    line=line_no,
                    section=current_section,
                )
            )
            continue

        if not stripped:
            continue

        if current_section is None:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="invalid_markdown_structure",
                    message="Content must appear inside a known section.",
                    source_path=path,
                    line=line_no,
                )
            )
            continue

        sections_raw[current_section].append((line_no, line.rstrip()))

    relationship_values, relationship_issues = _parse_relationships(
        path,
        sections_raw.get(structure.relationship_section, []),
        structure,
    )
    list_values, list_issues = _parse_list_sections(path, sections_raw, structure)
    text_values = _parse_text_sections(sections_raw, structure)
    issues.extend(list_issues)
    issues.extend(relationship_issues)

    canonical = text_values.get(structure.canonical_section)
    concept_id = slugify(canonical or title)
    return ConceptDraft(
        source_path=path,
        title=title,
        concept_id=concept_id,
        canonical=canonical,
        aliases=list_values.get(structure.aliases_section, []),
        definition=text_values.get(structure.definition_section),
        relationships=relationship_values,
        related=[relationship.target for relationship in relationship_values],
        parents=list_values.get(structure.parents_section, []),
        not_same_as=list_values.get(structure.not_same_as_section, []),
        query_hints=list_values.get(structure.query_hints_section, []),
        answer_requirements=list_values.get(structure.answer_requirements_section, []),
        sections_present=sections_present,
        parse_issues=issues,
    )


def parse_ontology(root: Path, area: str | None = None, version: str | None = None) -> list[ConceptDraft]:
    selection = resolve_ontology_selection(root, area=area, version=version)
    structure = selection.structure or default_ontology_structure()
    return [parse_concept_file(path, structure=structure) for path in sorted(selection.version_path.glob("*.md"))]


def _parse_text_sections(
    sections_raw: dict[str, list[tuple[int, str]]],
    structure: OntologyStructure,
) -> dict[str, str]:
    values: dict[str, str] = {}
    for name in structure.text_sections:
        lines = [line.strip() for _, line in sections_raw.get(name, []) if line.strip()]
        if lines:
            values[name] = " ".join(lines).strip()
    return values


def _parse_list_sections(
    path: Path,
    sections_raw: dict[str, list[tuple[int, str]]],
    structure: OntologyStructure,
) -> tuple[dict[str, list[str]], list[ValidationIssue]]:
    values: dict[str, list[str]] = {}
    issues: list[ValidationIssue] = []
    for name, entries in sections_raw.items():
        if name not in set(structure.list_sections) or name == structure.relationship_section:
            continue
        items: list[str] = []
        for line_no, line in entries:
            stripped = line.strip()
            if not stripped:
                continue
            if not stripped.startswith("- "):
                issues.append(
                    ValidationIssue(
                        severity="error",
                        code="invalid_markdown_structure",
                        message=f"Section '{name}' must use '- item' bullet entries.",
                        source_path=path,
                        line=line_no,
                        section=name,
                    )
                )
                continue
            items.append(stripped[2:].strip())
        values[name] = items
    return values, issues


def _parse_relationships(
    path: Path,
    entries: list[tuple[int, str]],
    structure: OntologyStructure,
) -> tuple[list[RelationshipDraft], list[ValidationIssue]]:
    relationships: list[RelationshipDraft] = []
    issues: list[ValidationIssue] = []
    if not entries:
        return relationships, issues

    blocks: list[list[tuple[int, str]]] = []
    current_block: list[tuple[int, str]] = []
    for line_no, line in entries:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("- "):
            if current_block:
                blocks.append(current_block)
            current_block = [(line_no, stripped[2:].strip())]
            continue
        if not current_block:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="invalid_markdown_structure",
                    message="Related entries must start with '- type: <relationship>' or '- <concept>'.",
                    source_path=path,
                    line=line_no,
                    section=structure.relationship_section,
                )
            )
            continue
        current_block.append((line_no, stripped))

    if current_block:
        blocks.append(current_block)

    for block in blocks:
        relationship, block_issues = _parse_relationship_block(path, block, structure)
        issues.extend(block_issues)
        if relationship:
            relationships.append(relationship)
    return relationships, issues


def _parse_relationship_block(
    path: Path,
    block: list[tuple[int, str]],
    structure: OntologyStructure,
) -> tuple[RelationshipDraft | None, list[ValidationIssue]]:
    issues: list[ValidationIssue] = []
    relationship_type: str | None = None
    target: str | None = None

    first_line_no, first_value = block[0]
    if ":" not in first_value:
        return RelationshipDraft(relationship_type="related", target=first_value), issues

    key, value = _split_key_value(first_value)
    if key is None:
        issues.append(
            ValidationIssue(
                severity="error",
                code="invalid_relationship_entry",
                message="Could not parse relationship entry in Related section.",
                source_path=path,
                line=first_line_no,
                section=structure.relationship_section,
            )
        )
        return None, issues
    if key in set(structure.relationship_type_keys):
        relationship_type = value
    elif key in set(structure.relationship_target_keys):
        target = value
    else:
        issues.append(
            ValidationIssue(
                severity="error",
                code="invalid_relationship_entry",
                message=f"Unsupported Related entry key '{key}'. Use 'type' and 'concept'.",
                source_path=path,
                line=first_line_no,
                section=structure.relationship_section,
            )
        )

    for line_no, line_value in block[1:]:
        nested_key, nested_value = _split_key_value(line_value)
        if nested_key is None:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="invalid_relationship_entry",
                    message="Nested Related fields must use 'key: value' syntax.",
                    source_path=path,
                    line=line_no,
                    section=structure.relationship_section,
                )
            )
            continue
        if nested_key in set(structure.relationship_type_keys):
            relationship_type = nested_value
        elif nested_key in set(structure.relationship_target_keys):
            target = nested_value
        else:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="invalid_relationship_entry",
                    message=f"Unsupported Related entry key '{nested_key}'. Use 'type' and 'concept'.",
                    source_path=path,
                    line=line_no,
                    section=structure.relationship_section,
                )
            )

    if not relationship_type or not target:
        issues.append(
            ValidationIssue(
                severity="error",
                code="invalid_relationship_entry",
                message="Each Related relationship must include both 'type' and 'concept'.",
                source_path=path,
                line=first_line_no,
                section=structure.relationship_section,
            )
        )
        return None, issues

    return RelationshipDraft(relationship_type=relationship_type, target=target), issues


def _split_key_value(value: str) -> tuple[str | None, str | None]:
    if ":" not in value:
        return None, None
    key, raw_value = value.split(":", 1)
    return key.strip().lower(), raw_value.strip()


def _header_re(prefix: str) -> re.Pattern[str]:
    return re.compile(rf"^{re.escape(prefix)}\s*(.+?)\s*$")
