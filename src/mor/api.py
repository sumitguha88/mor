"""FastAPI application for MOR."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException

from mor.models import ExpandRequest, ResolveRequest, ScaffoldRequest, ValidateRequest
from mor.runtime import OntologyRuntime


def create_app(
    ontology_root: str | Path = "ontology",
    area: str | None = None,
    version: str | None = None,
) -> FastAPI:
    runtime = OntologyRuntime(ontology_root, area=area, version=version)
    app = FastAPI(title="Markdown Ontology Runtime", version="0.1.0")
    app.state.runtime = runtime

    @app.get("/concepts")
    def list_concepts() -> list[dict[str, object]]:
        return [item.model_dump(mode="json") for item in runtime.list_concepts()]

    @app.get("/concepts/{concept_id}")
    def get_concept(concept_id: str) -> dict[str, object]:
        concept = runtime.get_concept(concept_id)
        if concept is None:
            raise HTTPException(status_code=404, detail="Concept not found")
        return concept.model_dump(mode="json")

    @app.post("/resolve")
    def resolve_term(request: ResolveRequest) -> dict[str, object]:
        return runtime.resolve(request.term).model_dump(mode="json")

    @app.post("/expand")
    def expand_query(request: ExpandRequest) -> dict[str, object]:
        return runtime.expand(
            request.query,
            max_concepts=request.max_concepts,
            max_terms=request.max_terms,
        ).model_dump(mode="json")

    @app.post("/validate")
    def validate_ontology(request: ValidateRequest) -> dict[str, object]:
        return runtime.validate(reload=request.reload).model_dump(mode="json")

    @app.post("/scaffold")
    def scaffold_answer(request: ScaffoldRequest) -> dict[str, object]:
        return runtime.scaffold(
            intent=request.intent,
            query=request.query,
            concept_ids=request.concept_ids,
        ).model_dump(mode="json")

    @app.get("/stats")
    def stats() -> dict[str, object]:
        return runtime.stats().model_dump(mode="json")

    return app


app = create_app()
