from pathlib import Path

from mor.parser import parse_ontology
from mor.validator import validate_drafts


def test_validator_detects_missing_section(tmp_path: Path) -> None:
    concept_file = tmp_path / "example.md"
    concept_file.write_text(
        """# Concept: Example

## Canonical
example

## Aliases
- sample
""",
        encoding="utf-8",
    )

    report = validate_drafts(parse_ontology(tmp_path))

    assert report.valid is False
    assert any(issue.code == "missing_section" for issue in report.issues)


def test_validator_detects_alias_conflict(tmp_path: Path) -> None:
    first = tmp_path / "a.md"
    second = tmp_path / "b.md"
    first.write_text(
        """# Concept: Alpha

## Canonical
alpha

## Aliases
- overlap

## Definition
Alpha definition.

## Related

## Parents

## NotSameAs

## QueryHints

## AnswerRequirements
- definition
""",
        encoding="utf-8",
    )
    second.write_text(
        """# Concept: Beta

## Canonical
beta

## Aliases
- overlap

## Definition
Beta definition.

## Related

## Parents

## NotSameAs

## QueryHints

## AnswerRequirements
- definition
""",
        encoding="utf-8",
    )

    report = validate_drafts(parse_ontology(tmp_path))

    assert any(issue.code == "alias_conflict" for issue in report.issues)


def test_validator_detects_circular_hierarchy(tmp_path: Path) -> None:
    first = tmp_path / "a.md"
    second = tmp_path / "b.md"
    for path, canonical, parent in (
        (first, "alpha", "beta"),
        (second, "beta", "alpha"),
    ):
        path.write_text(
            f"""# Concept: {canonical.title()}

## Canonical
{canonical}

## Aliases

## Definition
Definition for {canonical}.

## Related

## Parents
- {parent}

## NotSameAs

## QueryHints

## AnswerRequirements
- definition
""",
            encoding="utf-8",
        )

    report = validate_drafts(parse_ontology(tmp_path))

    assert any(issue.code == "circular_hierarchy" for issue in report.issues)

