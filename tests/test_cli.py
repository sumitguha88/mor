from pathlib import Path

from typer.testing import CliRunner

from mor.cli import app


runner = CliRunner()
ONTOLOGY_ROOT = Path(__file__).resolve().parents[1] / "ontology"
EXAMPLES_ROOT = Path(__file__).resolve().parents[1] / "examples" / "benchmark_cases.json"


def test_cli_resolve_command() -> None:
    result = runner.invoke(app, ["resolve", "grind stage", "--ontology-root", str(ONTOLOGY_ROOT)])

    assert result.exit_code == 0
    assert '"canonical": "pigment dispersion"' in result.stdout


def test_cli_init_concept(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["init-concept", "Test Concept", "--ontology-root", str(tmp_path)],
    )

    assert result.exit_code == 0
    concept_path = tmp_path / "paint-manufacturing" / "V1" / "test-concept.md"
    metadata_path = tmp_path / "paint-manufacturing" / "V1" / "ontology.json"
    structure_path = tmp_path / "structure" / "markdown-concept-v1.json"
    assert concept_path.exists()
    assert metadata_path.exists()
    assert structure_path.exists()
    assert '"structure": "markdown-concept-v1"' in metadata_path.read_text(encoding="utf-8")
    assert "type: related_to" in concept_path.read_text(encoding="utf-8")


def test_cli_benchmark_command() -> None:
    result = runner.invoke(
        app,
        [
            "benchmark",
            "--cases-path",
            str(EXAMPLES_ROOT),
            "--ontology-root",
            str(ONTOLOGY_ROOT),
        ],
    )

    assert result.exit_code == 0
    assert '"aggregate_ontology_assisted"' in result.stdout


def test_cli_can_select_marketing_area() -> None:
    result = runner.invoke(
        app,
        [
            "resolve",
            "paid search",
            "--ontology-root",
            str(ONTOLOGY_ROOT),
            "--area",
            "marketing",
            "--version",
            "V1",
        ],
    )

    assert result.exit_code == 0
    assert '"canonical": "search advertising"' in result.stdout
