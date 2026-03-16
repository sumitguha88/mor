"""Ontology area, version, and structure discovery."""

from __future__ import annotations

import json
from pathlib import Path

from mor.models import (
    OntologyAreaSummary,
    OntologyMetadata,
    OntologySelection,
    OntologyStructure,
    OntologyVersionMetadata,
)
from mor.utils import normalize_term

STRUCTURE_DIR_NAME = "structure"
DEFAULT_STRUCTURE_ID = "markdown-concept-v1"


def default_ontology_structure() -> OntologyStructure:
    return OntologyStructure(
        id=DEFAULT_STRUCTURE_ID,
        name="Markdown Concept Format V1",
        description="Default MOR markdown concept structure with typed Related relationships.",
        concept_header_prefix="# Concept:",
        required_sections=[
            "Canonical",
            "Aliases",
            "Definition",
            "Related",
            "NotSameAs",
            "QueryHints",
            "AnswerRequirements",
        ],
        optional_sections=["Parents"],
        list_sections=[
            "Aliases",
            "Related",
            "NotSameAs",
            "QueryHints",
            "AnswerRequirements",
            "Parents",
        ],
        text_sections=["Canonical", "Definition"],
        canonical_section="Canonical",
        aliases_section="Aliases",
        definition_section="Definition",
        relationship_section="Related",
        parents_section="Parents",
        not_same_as_section="NotSameAs",
        query_hints_section="QueryHints",
        answer_requirements_section="AnswerRequirements",
        relationship_type_keys=["type", "relationship", "predicate"],
        relationship_target_keys=["concept", "entity", "target"],
        inverse_relationships={
            "supplies": "supplied_by",
            "supplied_by": "supplies",
            "ships_to": "receives_from",
            "receives_from": "ships_to",
            "contains": "contained_in",
            "contained_in": "contains",
            "manufactures": "manufactured_on",
            "manufactured_on": "manufactures",
            "stores": "stored_in",
            "stored_in": "stores",
            "produces": "produced_by",
            "produced_by": "produces",
            "has_production_line": "part_of",
            "has_warehouse": "part_of",
        },
    )


def resolve_ontology_selection(
    ontology_root: str | Path,
    area: str | None = None,
    version: str | None = None,
) -> OntologySelection:
    root = Path(ontology_root)
    if _has_markdown_files(root):
        return OntologySelection(
            requested_root=root,
            version_path=root,
            structure=default_ontology_structure(),
        )

    if _is_version_folder(root):
        version_metadata = _load_version_metadata(root)
        area_path = root.parent
        area_metadata, version_index = _load_area_record(area_path)
        structure = _load_structure(area_path.parent, version_metadata)
        return OntologySelection(
            requested_root=root,
            area_id=version_metadata.id,
            version=root.name,
            metadata=area_metadata,
            version_metadata=version_metadata,
            structure=structure,
            area_path=area_path,
            version_path=root,
        )

    if _is_area_folder(root):
        area_metadata, version_index = _load_area_record(root)
        selected_version_path, version_metadata = _select_version(root, version_index, version)
        structure = _load_structure(root.parent, version_metadata)
        return OntologySelection(
            requested_root=root,
            area_id=area_metadata.id,
            version=selected_version_path.name,
            metadata=area_metadata,
            version_metadata=version_metadata,
            structure=structure,
            area_path=root,
            version_path=selected_version_path,
        )

    area_index = _discover_area_records(root)
    if not area_index:
        raise ValueError(f"No ontology markdown files or ontology area folders found under '{root}'.")

    selected_area_path, area_metadata, version_index = _select_area(area_index, area)
    selected_version_path, version_metadata = _select_version(selected_area_path, version_index, version)
    structure = _load_structure(root, version_metadata)
    return OntologySelection(
        requested_root=root,
        area_id=area_metadata.id,
        version=selected_version_path.name,
        metadata=area_metadata,
        version_metadata=version_metadata,
        structure=structure,
        area_path=selected_area_path,
        version_path=selected_version_path,
    )


def list_ontology_areas(ontology_root: str | Path) -> list[OntologyAreaSummary]:
    root = Path(ontology_root)
    return [
        OntologyAreaSummary(area_path=area_path, metadata=metadata)
        for area_path, metadata, _ in _discover_area_records(root)
    ]


def _discover_area_records(
    root: Path,
) -> list[tuple[Path, OntologyMetadata, list[tuple[Path, OntologyVersionMetadata]]]]:
    items: list[tuple[Path, OntologyMetadata, list[tuple[Path, OntologyVersionMetadata]]]] = []
    if not root.exists():
        return items
    for path in sorted(root.iterdir()):
        if path.name == STRUCTURE_DIR_NAME or not _is_area_folder(path):
            continue
        metadata, version_index = _load_area_record(path)
        items.append((path, metadata, version_index))
    return items


def _select_area(
    area_index: list[tuple[Path, OntologyMetadata, list[tuple[Path, OntologyVersionMetadata]]]],
    area: str | None,
) -> tuple[Path, OntologyMetadata, list[tuple[Path, OntologyVersionMetadata]]]:
    if area:
        normalized_area = normalize_term(area)
        for area_path, metadata, version_index in area_index:
            candidate_labels = {normalize_term(area_path.name), normalize_term(metadata.id), normalize_term(metadata.name)}
            if normalized_area in candidate_labels:
                return area_path, metadata, version_index
        raise ValueError(f"Unknown ontology area '{area}'.")

    if len(area_index) == 1:
        return area_index[0]

    defaults = [item for item in area_index if item[1].default]
    if len(defaults) == 1:
        return defaults[0]
    if len(defaults) > 1:
        raise ValueError("Multiple ontology areas are marked as default.")
    available = ", ".join(metadata.id for _, metadata, _ in area_index)
    raise ValueError(f"Multiple ontology areas available. Specify one explicitly: {available}.")


def _select_version(
    area_path: Path,
    version_index: list[tuple[Path, OntologyVersionMetadata]],
    version: str | None,
) -> tuple[Path, OntologyVersionMetadata]:
    if not version_index:
        raise ValueError(f"No version folders found under '{area_path}'.")

    if version:
        requested = version.upper()
        for version_path, metadata in version_index:
            if version_path.name.upper() == requested or metadata.version.upper() == requested:
                return version_path, metadata
        area_id = version_index[0][1].id if version_index else area_path.name
        raise ValueError(f"Unknown ontology version '{version}' for area '{area_id}'.")

    explicit_defaults = [
        (version_path, metadata)
        for version_path, metadata in version_index
        if metadata.is_default_version
    ]
    if len(explicit_defaults) == 1:
        return explicit_defaults[0]
    if len(explicit_defaults) > 1:
        area_id = version_index[0][1].id
        raise ValueError(f"Multiple versions are marked as default for area '{area_id}'.")

    for version_path, metadata in version_index:
        if version_path.name.upper() == "V1":
            return version_path, metadata
    return version_index[-1]


def _load_area_record(area_path: Path) -> tuple[OntologyMetadata, list[tuple[Path, OntologyVersionMetadata]]]:
    version_index = [
        (path, _load_version_metadata(path))
        for path in sorted(area_path.iterdir())
        if _is_version_folder(path)
    ]
    if not version_index:
        raise ValueError(f"No version folders found under '{area_path}'.")

    summary_source_path, summary_source = _select_version(area_path, version_index, None)
    tags = list(dict.fromkeys(tag for _, metadata in version_index for tag in metadata.tags))
    metadata = OntologyMetadata(
        id=summary_source.id,
        name=summary_source.name,
        description=summary_source.description,
        domain=summary_source.domain,
        default=any(item.default for _, item in version_index),
        default_version=summary_source_path.name,
        versions=[version_path.name for version_path, _ in version_index],
        tags=tags,
    )
    return metadata, version_index


def _load_version_metadata(version_path: Path) -> OntologyVersionMetadata:
    payload = json.loads((version_path / "ontology.json").read_text(encoding="utf-8"))
    metadata = OntologyVersionMetadata.model_validate(payload)
    if not metadata.version:
        metadata.version = version_path.name
    return metadata


def _load_structure(ontology_root: Path, version_metadata: OntologyVersionMetadata) -> OntologyStructure:
    default_structure = default_ontology_structure()
    structure_ref = version_metadata.structure.strip()
    if not structure_ref:
        return default_structure

    structure_root = ontology_root / STRUCTURE_DIR_NAME
    structure_path = Path(structure_ref)
    if not structure_path.is_absolute():
        if structure_path.suffix == ".json" or structure_path.parent != Path("."):
            structure_path = structure_root / structure_path
        else:
            structure_path = structure_root / f"{structure_ref}.json"

    if not structure_path.exists():
        if version_metadata.structure == default_structure.id:
            return default_structure
        raise ValueError(
            f"Unknown ontology structure '{version_metadata.structure}' for "
            f"area '{version_metadata.id}' version '{version_metadata.version}'."
        )

    payload = json.loads(structure_path.read_text(encoding="utf-8"))
    return OntologyStructure.model_validate(payload)


def _is_area_folder(path: Path) -> bool:
    return path.is_dir() and any(_is_version_folder(child) for child in path.iterdir())


def _is_version_folder(path: Path) -> bool:
    return path.is_dir() and (path / "ontology.json").exists()


def _has_markdown_files(path: Path) -> bool:
    return path.is_dir() and any(path.glob("*.md"))
