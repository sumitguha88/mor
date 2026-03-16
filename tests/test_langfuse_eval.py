from pathlib import Path

from typer.testing import CliRunner

from mor.cli import app
from mor.langfuse_eval import load_eval_dataset, run_eval_experiment


runner = CliRunner()
ROOT = Path(__file__).resolve().parents[1]
ONTOLOGY_ROOT = ROOT / "ontology"
DATASET_PATH = ROOT / "examples" / "evals" / "paint-v2-eval.json"


def test_load_eval_dataset() -> None:
    items = load_eval_dataset(DATASET_PATH)

    assert len(items) == 5
    assert items[0].input["version"] == "V2"
    assert "expected_concepts" in items[0].expected_output


def test_run_eval_experiment_dry_run() -> None:
    result = run_eval_experiment(
        ontology_root=ONTOLOGY_ROOT,
        area="paint-manufacturing",
        version="V2",
        dataset_path=DATASET_PATH,
        mode="ontology_assisted",
        provider="mock",
        dry_run=True,
        max_items=2,
    )

    assert result.mode == "ontology_assisted"
    assert result.provider == "mock"
    assert len(result.item_results) == 2
    assert any(score.name == "avg_answer_completeness" for score in result.run_evaluations)
    assert result.item_results[0].output.area == "paint-manufacturing"


def test_cli_eval_llm_dry_run() -> None:
    result = runner.invoke(
        app,
        [
            "eval-llm",
            "--dataset-path",
            str(DATASET_PATH),
            "--ontology-root",
            str(ONTOLOGY_ROOT),
            "--area",
            "paint-manufacturing",
            "--version",
            "V2",
            "--provider",
            "mock",
            "--mode",
            "baseline",
            "--dry-run",
            "--max-items",
            "1",
        ],
    )

    assert result.exit_code == 0
    assert '"mode": "baseline"' in result.stdout
    assert '"provider": "mock"' in result.stdout
    assert '"processed_items"' in result.stdout
