"""Typer CLI for MOR."""

from __future__ import annotations

from pathlib import Path

import typer

from mor.api import create_app
from mor.langfuse_eval import (
    DEFAULT_EVAL_DATASET_NAME,
    DEFAULT_EVAL_DATASET_PATH,
    DEFAULT_EVAL_EXPERIMENT_NAME,
    DEFAULT_LLM_MODEL,
    run_eval_experiment,
    upload_eval_dataset,
)
from mor.mcp import MORServer
from mor.registry import DEFAULT_STRUCTURE_ID, STRUCTURE_DIR_NAME, default_ontology_structure
from mor.runtime import OntologyRuntime
from mor.utils import json_dumps, slugify

app = typer.Typer(add_completion=False, help="Markdown Ontology Runtime CLI.")


def _runtime(ontology_root: Path, area: str | None, version: str | None) -> OntologyRuntime:
    return OntologyRuntime(ontology_root, area=area, version=version)


def _area_option() -> str | None:
    return typer.Option(None, "--area", help="Ontology area id, such as paint.")


def _version_option() -> str | None:
    return typer.Option(None, "--version", help="Ontology version folder, such as V1.")


def _ensure_area_layout(ontology_root: Path, area: str, version: str) -> Path:
    area_path = ontology_root / area
    version_path = area_path / version.upper()
    version_path.mkdir(parents=True, exist_ok=True)
    _ensure_structure_layout(ontology_root)
    metadata_path = version_path / "ontology.json"
    if not metadata_path.exists():
        existing_area_count = sum(
            1
            for path in ontology_root.iterdir()
            if path.is_dir()
            and path.name != STRUCTURE_DIR_NAME
            and any(child.is_dir() and (child / "ontology.json").exists() for child in path.iterdir())
        )
        metadata_path.write_text(
            json_dumps(
                {
                    "id": area,
                    "name": area.replace("-", " ").title(),
                    "description": "Describe this ontology area.",
                    "version": version.upper(),
                    "structure": DEFAULT_STRUCTURE_ID,
                    "default": existing_area_count == 0,
                    "is_default_version": True,
                    "tags": [],
                }
            )
            + "\n",
            encoding="utf-8",
        )
    return version_path


def _ensure_structure_layout(ontology_root: Path) -> Path:
    structure_root = ontology_root / STRUCTURE_DIR_NAME
    structure_root.mkdir(parents=True, exist_ok=True)
    structure_path = structure_root / f"{DEFAULT_STRUCTURE_ID}.json"
    if not structure_path.exists():
        structure_path.write_text(
            json_dumps(default_ontology_structure().model_dump(mode="json")) + "\n",
            encoding="utf-8",
        )
    return structure_root


@app.command("init")
def init_project(
    ontology_root: Path = typer.Option(Path("ontology"), "--ontology-root", help="Ontology directory."),
    area: str = typer.Option("paint", "--area", help="Ontology area id."),
    version: str = typer.Option("V1", "--version", help="Ontology version folder."),
) -> None:
    version_path = _ensure_area_layout(ontology_root, area, version)
    sample_path = version_path / "example-concept.md"
    if not sample_path.exists():
        sample_path.write_text(_concept_template("Example Concept"), encoding="utf-8")
    typer.echo(f"Initialized ontology area at {version_path}")


@app.command("init-concept")
def init_concept(
    name: str,
    ontology_root: Path = typer.Option(Path("ontology"), "--ontology-root", help="Ontology directory."),
    area: str | None = _area_option(),
    version: str | None = _version_option(),
) -> None:
    try:
        runtime = _runtime(ontology_root, area, version)
        target_dir = runtime.selection.version_path if runtime.selection else ontology_root
    except ValueError:
        target_dir = _ensure_area_layout(
            ontology_root,
            area or "paint",
            version or "V1",
        )
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{slugify(name)}.md"
    if path.exists():
        raise typer.BadParameter(f"Concept file already exists: {path}")
    path.write_text(_concept_template(name), encoding="utf-8")
    typer.echo(str(path))


@app.command()
def validate(
    ontology_root: Path = typer.Option(Path("ontology"), "--ontology-root", help="Ontology directory."),
    area: str | None = _area_option(),
    version: str | None = _version_option(),
) -> None:
    runtime = _runtime(ontology_root, area, version)
    typer.echo(json_dumps(runtime.validate().model_dump(mode="json")))


@app.command()
def resolve(
    term: str,
    ontology_root: Path = typer.Option(Path("ontology"), "--ontology-root", help="Ontology directory."),
    area: str | None = _area_option(),
    version: str | None = _version_option(),
) -> None:
    runtime = _runtime(ontology_root, area, version)
    typer.echo(json_dumps(runtime.resolve(term).model_dump(mode="json")))


@app.command()
def expand(
    query: str,
    ontology_root: Path = typer.Option(Path("ontology"), "--ontology-root", help="Ontology directory."),
    area: str | None = _area_option(),
    version: str | None = _version_option(),
) -> None:
    runtime = _runtime(ontology_root, area, version)
    typer.echo(json_dumps(runtime.expand(query).model_dump(mode="json")))


@app.command()
def scaffold(
    intent: str = typer.Option(..., "--intent", help="Scaffold intent identifier."),
    query: str | None = typer.Option(None, "--query", help="Optional user query."),
    concept_id: list[str] | None = typer.Option(None, "--concept-id", help="Explicit concept ids."),
    ontology_root: Path = typer.Option(Path("ontology"), "--ontology-root", help="Ontology directory."),
    area: str | None = _area_option(),
    version: str | None = _version_option(),
) -> None:
    runtime = _runtime(ontology_root, area, version)
    typer.echo(
        json_dumps(
            runtime.scaffold(intent=intent, query=query, concept_ids=concept_id).model_dump(mode="json")
        )
    )


@app.command()
def stats(
    ontology_root: Path = typer.Option(Path("ontology"), "--ontology-root", help="Ontology directory."),
    area: str | None = _area_option(),
    version: str | None = _version_option(),
) -> None:
    runtime = _runtime(ontology_root, area, version)
    typer.echo(json_dumps(runtime.stats().model_dump(mode="json")))


@app.command()
def benchmark(
    cases_path: Path = typer.Option(Path("examples/benchmark_cases.json"), "--cases-path"),
    ontology_root: Path = typer.Option(Path("ontology"), "--ontology-root", help="Ontology directory."),
    area: str | None = _area_option(),
    version: str | None = _version_option(),
) -> None:
    runtime = _runtime(ontology_root, area, version)
    typer.echo(json_dumps(runtime.benchmark(cases_path).model_dump(mode="json")))


@app.command("langfuse-upload-dataset")
def langfuse_upload_dataset(
    dataset_path: Path = typer.Option(DEFAULT_EVAL_DATASET_PATH, "--dataset-path"),
    dataset_name: str = typer.Option(DEFAULT_EVAL_DATASET_NAME, "--dataset-name"),
    description: str | None = typer.Option(None, "--description"),
    langfuse_public_key: str | None = typer.Option(None, "--langfuse-public-key"),
    langfuse_secret_key: str | None = typer.Option(None, "--langfuse-secret-key"),
    langfuse_host: str | None = typer.Option(None, "--langfuse-host"),
) -> None:
    result = upload_eval_dataset(
        dataset_path=dataset_path,
        dataset_name=dataset_name,
        description=description,
        public_key=langfuse_public_key,
        secret_key=langfuse_secret_key,
        host=langfuse_host,
    )
    typer.echo(json_dumps(result.model_dump(mode="json")))


@app.command("eval-llm")
def eval_llm(
    dataset_path: Path = typer.Option(DEFAULT_EVAL_DATASET_PATH, "--dataset-path"),
    dataset_name: str | None = typer.Option(None, "--dataset-name"),
    ontology_root: Path = typer.Option(Path("ontology"), "--ontology-root", help="Ontology directory."),
    area: str | None = _area_option(),
    version: str | None = _version_option(),
    experiment_name: str = typer.Option(DEFAULT_EVAL_EXPERIMENT_NAME, "--experiment-name"),
    run_name: str | None = typer.Option(None, "--run-name"),
    mode: str = typer.Option("ontology_assisted", "--mode", help="baseline or ontology_assisted"),
    provider: str = typer.Option("mock", "--provider", help="mock or openai"),
    model: str = typer.Option(DEFAULT_LLM_MODEL, "--model"),
    langfuse_public_key: str | None = typer.Option(None, "--langfuse-public-key"),
    langfuse_secret_key: str | None = typer.Option(None, "--langfuse-secret-key"),
    langfuse_host: str | None = typer.Option(None, "--langfuse-host"),
    openai_api_key: str | None = typer.Option(None, "--openai-api-key"),
    openai_base_url: str | None = typer.Option(None, "--openai-base-url"),
    max_items: int | None = typer.Option(None, "--max-items"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    if mode not in {"baseline", "ontology_assisted"}:
        raise typer.BadParameter("Mode must be 'baseline' or 'ontology_assisted'.")
    if provider not in {"mock", "openai"}:
        raise typer.BadParameter("Provider must be 'mock' or 'openai'.")
    result = run_eval_experiment(
        ontology_root=ontology_root,
        area=area,
        version=version,
        dataset_path=dataset_path,
        dataset_name=dataset_name,
        experiment_name=experiment_name,
        run_name=run_name,
        mode=mode,
        provider=provider,
        model=model,
        public_key=langfuse_public_key,
        secret_key=langfuse_secret_key,
        host=langfuse_host,
        openai_api_key=openai_api_key,
        openai_base_url=openai_base_url,
        max_items=max_items,
        dry_run=dry_run,
    )
    typer.echo(json_dumps(result.model_dump(mode="json")))


@app.command("serve-api")
def serve_api(
    ontology_root: Path = typer.Option(Path("ontology"), "--ontology-root", help="Ontology directory."),
    area: str | None = _area_option(),
    version: str | None = _version_option(),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
) -> None:
    import uvicorn

    uvicorn.run(create_app(ontology_root, area=area, version=version), host=host, port=port)


@app.command("serve-mcp")
def serve_mcp(
    ontology_root: Path = typer.Option(Path("ontology"), "--ontology-root", help="Ontology directory."),
    area: str | None = _area_option(),
    version: str | None = _version_option(),
) -> None:
    MORServer(ontology_root, area=area, version=version).serve_stdio()


def _concept_template(name: str) -> str:
    return f"""# Concept: {name}

## Canonical
{name.lower()}

## Aliases
- {name.lower()}

## Definition
Describe the concept in one paragraph.

## Related
- type: related_to
  concept: related concept

## Parents
- parent concept

## NotSameAs
- contrasting concept

## QueryHints
- boost: domain keyword

## AnswerRequirements
- definition
- mechanism
- tradeoffs
"""
