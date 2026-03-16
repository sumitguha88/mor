from pathlib import Path

from mor.parser import parse_concept_file


def test_parse_valid_concept(tmp_path: Path) -> None:
    concept_file = tmp_path / "eventual-consistency.md"
    concept_file.write_text(
        """# Concept: Eventual Consistency

## Canonical
eventual consistency

## Aliases
- async consistency

## Definition
A consistency model for distributed replicas.

## Related
- type: part_of_domain
  concept: distributed systems

## Parents
- consistency models

## NotSameAs
- strong consistency

## QueryHints
- boost: quorum

## AnswerRequirements
- mechanism
""",
        encoding="utf-8",
    )

    draft = parse_concept_file(concept_file)

    assert draft.title == "Eventual Consistency"
    assert draft.concept_id == "eventual-consistency"
    assert draft.canonical == "eventual consistency"
    assert draft.aliases == ["async consistency"]
    assert draft.related == ["distributed systems"]
    assert len(draft.relationships) == 1
    assert draft.relationships[0].relationship_type == "part_of_domain"
    assert draft.relationships[0].target == "distributed systems"
    assert draft.parents == ["consistency models"]
    assert not draft.parse_issues


def test_parse_legacy_related_entry_defaults_to_related_type(tmp_path: Path) -> None:
    concept_file = tmp_path / "legacy.md"
    concept_file.write_text(
        """# Concept: Legacy Example

## Canonical
legacy example

## Aliases

## Definition
Legacy concept.

## Related
- another concept

## Parents

## NotSameAs

## QueryHints

## AnswerRequirements
- definition
""",
        encoding="utf-8",
    )

    draft = parse_concept_file(concept_file)

    assert len(draft.relationships) == 1
    assert draft.relationships[0].relationship_type == "related"
    assert draft.relationships[0].target == "another concept"


def test_parse_invalid_structure_reports_error(tmp_path: Path) -> None:
    concept_file = tmp_path / "broken.md"
    concept_file.write_text(
        """## Canonical
missing concept header
""",
        encoding="utf-8",
    )

    draft = parse_concept_file(concept_file)

    assert any(issue.code == "invalid_markdown_structure" for issue in draft.parse_issues)
