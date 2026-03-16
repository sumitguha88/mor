"""Langfuse-backed and local dry-run evaluation helpers for MOR."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from statistics import mean
from typing import Any

from mor.constants import DEFAULT_INTENT_SECTIONS, SECTION_TITLES
from mor.models import (
    EvalDatasetItem,
    EvalDatasetUploadSummary,
    EvalItemResult,
    EvalRunSummary,
    EvalScore,
    EvalTaskOutput,
)
from mor.runtime import OntologyRuntime
from mor.utils import normalize_term, slugify, tokenize, unique_preserve

DEFAULT_EVAL_DATASET_PATH = Path("examples/evals/paint-v2-eval.json")
DEFAULT_EVAL_DATASET_NAME = "mor-paint-v2-eval"
DEFAULT_EVAL_EXPERIMENT_NAME = "MOR Paint V2 Evaluation"
DEFAULT_LLM_MODEL = "gpt-4.1-mini"
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", re.MULTILINE)


class _BaseAnswerGenerator:
    provider_name = "base"

    def __init__(self, model: str) -> None:
        self.model = model

    def generate(self, *, prompt: str, query: str, sections: list[str], concepts: list[str]) -> str:
        raise NotImplementedError


class _MockAnswerGenerator(_BaseAnswerGenerator):
    provider_name = "mock"

    def generate(self, *, prompt: str, query: str, sections: list[str], concepts: list[str]) -> str:
        lines = [f"Answering query: {query}"]
        if concepts:
            lines.append(f"Relevant concepts: {', '.join(concepts[:6])}.")
        for section_id in sections:
            title = SECTION_TITLES.get(section_id, _titleize(section_id))
            if section_id == "definition":
                body = f"This section defines the query in terms of {', '.join(concepts[:3]) or 'the ontology'}."
            elif section_id == "mechanism":
                body = (
                    "This section explains the relationship flow across the ontology, "
                    f"including {', '.join(concepts[:4]) or 'the main concepts'}."
                )
            elif section_id == "comparison":
                body = "This section compares adjacent concepts and their typed relationships."
            elif section_id == "implementation":
                body = "This section shows how the entities and relationships would be used operationally."
            elif section_id == "tradeoffs":
                body = "This section outlines tradeoffs, assumptions, and modeling boundaries."
            else:
                body = f"This section addresses {title.lower()} for the query."
            lines.append(f"## {title}\n{body}")
        lines.append(f"\nPrompt basis: {prompt[:220].strip()}")
        return "\n\n".join(lines).strip()


class _OpenAIAnswerGenerator(_BaseAnswerGenerator):
    provider_name = "openai"

    def __init__(self, model: str, api_key: str | None = None, base_url: str | None = None) -> None:
        super().__init__(model)
        try:
            from openai import OpenAI
        except ModuleNotFoundError as exc:  # pragma: no cover
            raise RuntimeError(
                "OpenAI SDK is not installed. Install the eval extras with: pip install -e '.[eval]'"
            ) from exc
        self._client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"), base_url=base_url or os.getenv("OPENAI_BASE_URL"))

    def generate(self, *, prompt: str, query: str, sections: list[str], concepts: list[str]) -> str:
        response = self._client.responses.create(
            model=self.model,
            instructions="You are a precise ontology-guided analyst. Follow the requested markdown headings exactly.",
            input=prompt,
            temperature=0.2,
        )
        output_text = getattr(response, "output_text", "")
        if output_text:
            return output_text.strip()
        return _extract_response_text(response)


def load_eval_dataset(path: str | Path = DEFAULT_EVAL_DATASET_PATH) -> list[EvalDatasetItem]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return [EvalDatasetItem.model_validate(item) for item in raw]


def upload_eval_dataset(
    *,
    dataset_path: str | Path = DEFAULT_EVAL_DATASET_PATH,
    dataset_name: str = DEFAULT_EVAL_DATASET_NAME,
    description: str | None = None,
    public_key: str | None = None,
    secret_key: str | None = None,
    host: str | None = None,
) -> EvalDatasetUploadSummary:
    dataset = load_eval_dataset(dataset_path)
    client = _get_langfuse_client(public_key=public_key, secret_key=secret_key, host=host)
    dataset_description = description or "Sample MOR evaluation dataset for paint V1."
    client.create_dataset(
        name=dataset_name,
        description=dataset_description,
        metadata={"framework": "mor", "area": "paint", "version": "V1"},
        input_schema=_input_schema(),
        expected_output_schema=_expected_output_schema(),
    )
    for item in dataset:
        client.create_dataset_item(
            dataset_name=dataset_name,
            id=item.id,
            input=item.input,
            expected_output=item.expected_output,
            metadata=item.metadata,
        )
    client.flush()
    return EvalDatasetUploadSummary(
        dataset_name=dataset_name,
        dataset_description=dataset_description,
        item_count=len(dataset),
        item_ids=[item.id for item in dataset],
    )


def run_eval_experiment(
    *,
    ontology_root: str | Path = "ontology",
    area: str | None = None,
    version: str | None = None,
    dataset_path: str | Path = DEFAULT_EVAL_DATASET_PATH,
    dataset_name: str | None = None,
    experiment_name: str = DEFAULT_EVAL_EXPERIMENT_NAME,
    run_name: str | None = None,
    mode: str = "ontology_assisted",
    provider: str = "mock",
    model: str = DEFAULT_LLM_MODEL,
    public_key: str | None = None,
    secret_key: str | None = None,
    host: str | None = None,
    openai_api_key: str | None = None,
    openai_base_url: str | None = None,
    max_items: int | None = None,
    dry_run: bool = False,
) -> EvalRunSummary:
    eval_items = load_eval_dataset(dataset_path)
    if max_items is not None:
        eval_items = eval_items[:max_items]
    generator = _make_answer_generator(
        provider=provider,
        model=model,
        openai_api_key=openai_api_key,
        openai_base_url=openai_base_url,
    )
    if dry_run:
        return _run_eval_locally(
            eval_items=eval_items,
            ontology_root=ontology_root,
            area=area,
            version=version,
            experiment_name=experiment_name,
            run_name=run_name or f"{slugify(experiment_name)}-dry-run",
            mode=mode,
            generator=generator,
        )

    client = _get_langfuse_client(public_key=public_key, secret_key=secret_key, host=host)
    data = client.get_dataset(dataset_name).items if dataset_name else [item.model_dump(mode="json") for item in eval_items]
    task = _build_task(
        ontology_root=ontology_root,
        area=area,
        version=version,
        mode=mode,
        generator=generator,
    )
    result = client.run_experiment(
        name=experiment_name,
        run_name=run_name,
        data=data,
        task=task,
        evaluators=[_langfuse_item_evaluator],
        run_evaluators=[_langfuse_run_evaluator],
        metadata={
            "framework": "mor",
            "mode": mode,
            "provider": generator.provider_name,
            "model": generator.model,
            "area": area or "",
            "version": version or "",
        },
    )
    client.flush()
    return _experiment_result_to_summary(
        result=result,
        mode=mode,
        provider=generator.provider_name,
        model=generator.model,
    )


def _run_eval_locally(
    *,
    eval_items: list[EvalDatasetItem],
    ontology_root: str | Path,
    area: str | None,
    version: str | None,
    experiment_name: str,
    run_name: str,
    mode: str,
    generator: _BaseAnswerGenerator,
) -> EvalRunSummary:
    task = _build_task(
        ontology_root=ontology_root,
        area=area,
        version=version,
        mode=mode,
        generator=generator,
    )
    item_results: list[EvalItemResult] = []
    for item in eval_items:
        output = EvalTaskOutput.model_validate(task(item=item.model_dump(mode="json")))
        evaluations = _score_output(
            input_value=item.input,
            output_value=output.model_dump(mode="json"),
            expected_output=item.expected_output,
            metadata=item.metadata,
        )
        item_results.append(
            EvalItemResult(
                item_id=item.id,
                output=output,
                evaluations=evaluations,
            )
        )
    run_evaluations = _aggregate_item_scores(item_results)
    return EvalRunSummary(
        experiment_name=experiment_name,
        run_name=run_name,
        mode=mode,
        provider=generator.provider_name,
        model=generator.model,
        item_results=item_results,
        run_evaluations=run_evaluations,
    )


def _build_task(
    *,
    ontology_root: str | Path,
    area: str | None,
    version: str | None,
    mode: str,
    generator: _BaseAnswerGenerator,
):
    runtime_cache: dict[tuple[str | None, str | None], OntologyRuntime] = {}

    def task(*, item: Any, **_: Any) -> dict[str, object]:
        normalized_item = _coerce_experiment_item(item)
        query = str(normalized_item.input.get("query", "")).strip()
        if not query:
            raise ValueError("Evaluation item input must include a non-empty 'query'.")
        intent = str(normalized_item.input.get("intent", "architecture_explanation"))
        runtime_area = str(
            normalized_item.input.get("area")
            or normalized_item.metadata.get("area")
            or area
            or ""
        ).strip() or None
        runtime_version = str(
            normalized_item.input.get("version")
            or normalized_item.metadata.get("version")
            or version
            or ""
        ).strip() or None
        cache_key = (runtime_area, runtime_version)
        runtime = runtime_cache.get(cache_key)
        if runtime is None:
            runtime = OntologyRuntime(ontology_root, area=runtime_area, version=runtime_version)
            runtime_cache[cache_key] = runtime

        if mode == "ontology_assisted":
            expansion = runtime.expand(query)
            scaffold = runtime.scaffold(intent=intent, query=query)
            matched_concepts = [item.canonical for item in expansion.matched_concepts]
            expanded_terms = expansion.expanded_terms
            scaffold_sections = [section.id for section in scaffold.sections]
            prompt = _build_ontology_prompt(
                query=query,
                runtime=runtime,
                expansion=expansion.model_dump(mode="json"),
                scaffold=scaffold.model_dump(mode="json"),
            )
        else:
            matched_concepts = _baseline_concepts(runtime, query)
            expanded_terms = matched_concepts[:]
            scaffold_sections = list(DEFAULT_INTENT_SECTIONS.get(intent, ("definition", "mechanism", "tradeoffs")))
            prompt = _build_baseline_prompt(query=query, sections=scaffold_sections)

        answer = generator.generate(
            prompt=prompt,
            query=query,
            sections=scaffold_sections,
            concepts=matched_concepts,
        )
        return EvalTaskOutput(
            query=query,
            answer=answer,
            mode="ontology_assisted" if mode == "ontology_assisted" else "baseline",
            provider=generator.provider_name,
            model=generator.model,
            area=runtime_area,
            version=runtime_version,
            matched_concepts=matched_concepts,
            expanded_terms=expanded_terms,
            scaffold_sections=scaffold_sections,
            prompt_preview=prompt[:500],
        ).model_dump(mode="json")

    return task


def _langfuse_item_evaluator(
    *,
    input: Any,
    output: Any,
    expected_output: Any,
    metadata: dict[str, Any] | None,
    **_: Any,
) -> list[Any]:
    return [_to_langfuse_evaluation(score) for score in _score_output(input, output, expected_output, metadata)]


def _langfuse_run_evaluator(*, item_results: list[Any], **_: Any) -> list[Any]:
    normalized_results: list[EvalItemResult] = []
    for item_result in item_results:
        item_id = _extract_item_id(getattr(item_result, "item", {}))
        output = EvalTaskOutput.model_validate(getattr(item_result, "output", {}))
        evaluations = [_coerce_eval_score(evaluation) for evaluation in getattr(item_result, "evaluations", [])]
        normalized_results.append(EvalItemResult(item_id=item_id, output=output, evaluations=evaluations))
    return [_to_langfuse_evaluation(score) for score in _aggregate_item_scores(normalized_results)]


def _score_output(
    input_value: Any,
    output_value: Any,
    expected_output: Any,
    metadata: dict[str, Any] | None,
) -> list[EvalScore]:
    _ = input_value, metadata
    output = EvalTaskOutput.model_validate(output_value)
    expected = dict(expected_output or {})
    expected_concepts = [str(item) for item in expected.get("expected_concepts", [])]
    expected_sections = [slugify(str(item)) for item in expected.get("expected_sections", [])]
    expected_terms = [str(item) for item in expected.get("expected_terms", [])]
    answer_text = normalize_term(output.answer)
    matched_concepts = [normalize_term(item) for item in output.matched_concepts]
    expanded_terms = [normalize_term(item) for item in output.expanded_terms]
    answer_sections = _extract_answer_sections(output.answer) or output.scaffold_sections
    normalized_answer_sections = [slugify(section) for section in answer_sections]

    concept_success = _coverage_score(expected_concepts, output.matched_concepts)
    ontology_coverage = _coverage_score(expected_terms, unique_preserve(output.expanded_terms + output.matched_concepts))
    answer_completeness = _coverage_score(expected_sections, normalized_answer_sections)
    terminology_consistency = _text_coverage_score(expected_terms, answer_text)
    answer_concept_mentions = _text_coverage_score(expected_concepts, answer_text)

    return [
        EvalScore(
            name="concept_resolution_success",
            value=concept_success,
            comment=f"Matched {len(_overlap(expected_concepts, output.matched_concepts))} of {len(expected_concepts) or 1} expected concepts.",
        ),
        EvalScore(
            name="ontology_coverage",
            value=ontology_coverage,
            comment="Measured how well ontology-assisted terms cover the expected domain terminology.",
        ),
        EvalScore(
            name="answer_completeness",
            value=answer_completeness,
            comment="Measured expected section coverage from answer headings or scaffold sections.",
        ),
        EvalScore(
            name="terminology_consistency",
            value=terminology_consistency,
            comment="Measured expected terminology usage in the generated answer text.",
        ),
        EvalScore(
            name="answer_concept_mentions",
            value=answer_concept_mentions,
            comment="Measured expected concept mentions in the generated answer text.",
        ),
    ]


def _aggregate_item_scores(item_results: list[EvalItemResult]) -> list[EvalScore]:
    numeric_scores: dict[str, list[float]] = {}
    for item_result in item_results:
        for evaluation in item_result.evaluations:
            if isinstance(evaluation.value, bool):
                numeric_scores.setdefault(evaluation.name, []).append(float(evaluation.value))
            elif isinstance(evaluation.value, (int, float)):
                numeric_scores.setdefault(evaluation.name, []).append(float(evaluation.value))
    aggregated = [
        EvalScore(
            name=f"avg_{name}",
            value=round(mean(values), 4),
            comment=f"Averaged across {len(values)} evaluated items.",
        )
        for name, values in sorted(numeric_scores.items())
        if values
    ]
    aggregated.append(
        EvalScore(
            name="processed_items",
            value=len(item_results),
            comment="Number of dataset items processed by the run.",
        )
    )
    return aggregated


def _make_answer_generator(
    *,
    provider: str,
    model: str,
    openai_api_key: str | None = None,
    openai_base_url: str | None = None,
) -> _BaseAnswerGenerator:
    if provider == "mock":
        return _MockAnswerGenerator(model=model)
    if provider == "openai":
        return _OpenAIAnswerGenerator(
            model=model,
            api_key=openai_api_key,
            base_url=openai_base_url,
        )
    raise ValueError(f"Unsupported eval provider '{provider}'. Use 'mock' or 'openai'.")


def _get_langfuse_client(
    *,
    public_key: str | None = None,
    secret_key: str | None = None,
    host: str | None = None,
) -> Any:
    if sys.version_info >= (3, 14):
        raise RuntimeError(
            "Langfuse SDK is currently incompatible with Python 3.14 in this environment. "
            "Run Langfuse-backed commands under Python 3.13/3.12, or use --dry-run locally."
        )
    try:
        from langfuse import Langfuse
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "Langfuse SDK is not available or failed to import. Install eval extras with: "
            "pip install -e '.[eval]'"
        ) from exc
    return Langfuse(public_key=public_key, secret_key=secret_key, host=host)


def _build_baseline_prompt(*, query: str, sections: list[str]) -> str:
    headings = "\n".join(f"- {_titleize(section)}" for section in sections)
    return (
        "You are answering a paint manufacturing ontology evaluation query.\n"
        "Respond in concise markdown and use these headings exactly:\n"
        f"{headings}\n\n"
        f"User query: {query}\n"
        "Focus on clear entity relationships and operational meaning."
    )


def _build_ontology_prompt(
    *,
    query: str,
    runtime: OntologyRuntime,
    expansion: dict[str, Any],
    scaffold: dict[str, Any],
) -> str:
    concept_lines: list[str] = []
    for evidence in expansion.get("matched_concepts", []):
        concept = runtime.get_concept(evidence["concept_id"])
        if concept:
            concept_lines.append(f"- {concept.canonical}: {concept.definition}")
    section_titles = [SECTION_TITLES.get(section["id"], _titleize(section["id"])) for section in scaffold.get("sections", [])]
    return (
        "You are answering with ontology guidance from MOR.\n"
        "Use the canonical ontology terminology when relevant and follow the requested markdown headings exactly.\n\n"
        f"User query: {query}\n\n"
        "Matched ontology concepts:\n"
        f"{chr(10).join(concept_lines) if concept_lines else '- None'}\n\n"
        "Expanded terms:\n"
        f"- {', '.join(expansion.get('expanded_terms', [])) or 'None'}\n\n"
        "Required answer headings:\n"
        f"- {', '.join(section_titles) or 'Definition, Mechanism, Tradeoffs'}"
    )


def _baseline_concepts(runtime: OntologyRuntime, query: str) -> list[str]:
    normalized_query = normalize_term(query)
    matched: list[str] = []
    for concept in runtime.model.concepts.values():
        labels = [concept.canonical, *concept.aliases]
        if any(normalize_term(label) and normalize_term(label) in normalized_query for label in labels):
            matched.append(concept.canonical)
    if matched:
        return unique_preserve(matched)

    query_tokens = set(tokenize(query))
    overlap_matches: list[tuple[int, str]] = []
    for concept in runtime.model.concepts.values():
        overlap = query_tokens & set(tokenize(concept.canonical))
        if overlap:
            overlap_matches.append((len(overlap), concept.canonical))
    overlap_matches.sort(key=lambda item: (-item[0], item[1]))
    return unique_preserve([canonical for _, canonical in overlap_matches[:5]])


def _experiment_result_to_summary(*, result: Any, mode: str, provider: str, model: str) -> EvalRunSummary:
    item_results: list[EvalItemResult] = []
    for item_result in result.item_results:
        item_results.append(
            EvalItemResult(
                item_id=_extract_item_id(item_result.item),
                output=EvalTaskOutput.model_validate(item_result.output),
                evaluations=[_coerce_eval_score(evaluation) for evaluation in item_result.evaluations],
            )
        )
    run_evaluations = [_coerce_eval_score(evaluation) for evaluation in result.run_evaluations]
    return EvalRunSummary(
        experiment_name=result.name,
        run_name=result.run_name,
        mode="ontology_assisted" if mode == "ontology_assisted" else "baseline",
        provider=provider,
        model=model,
        item_results=item_results,
        run_evaluations=run_evaluations,
        dataset_run_id=result.dataset_run_id,
        dataset_run_url=result.dataset_run_url,
    )


def _coerce_experiment_item(item: Any) -> EvalDatasetItem:
    if isinstance(item, EvalDatasetItem):
        return item
    if isinstance(item, dict):
        if {"input", "expected_output", "metadata"} & set(item):
            item_id = str(item.get("id") or _extract_item_id(item))
            return EvalDatasetItem(
                id=item_id,
                input=dict(item.get("input") or {}),
                expected_output=dict(item.get("expected_output") or {}),
                metadata=dict(item.get("metadata") or {}),
            )
    item_id = _extract_item_id(item)
    return EvalDatasetItem(
        id=item_id,
        input=dict(getattr(item, "input", {}) or {}),
        expected_output=dict(getattr(item, "expected_output", {}) or {}),
        metadata=dict(getattr(item, "metadata", {}) or {}),
    )


def _extract_item_id(item: Any) -> str:
    if isinstance(item, dict):
        if item.get("id"):
            return str(item["id"])
        query = str((item.get("input") or {}).get("query", "")).strip()
        return slugify(query or "eval-item")
    item_id = getattr(item, "id", None)
    if item_id:
        return str(item_id)
    query = str(getattr(item, "input", {}).get("query", "")).strip()
    return slugify(query or "eval-item")


def _coerce_eval_score(evaluation: Any) -> EvalScore:
    if isinstance(evaluation, EvalScore):
        return evaluation
    if isinstance(evaluation, dict):
        return EvalScore(
            name=str(evaluation.get("name", "")),
            value=evaluation.get("value"),
            comment=evaluation.get("comment"),
            metadata=dict(evaluation.get("metadata") or {}),
        )
    return EvalScore(
        name=str(getattr(evaluation, "name")),
        value=getattr(evaluation, "value"),
        comment=getattr(evaluation, "comment", None),
        metadata=dict(getattr(evaluation, "metadata", {}) or {}),
    )


def _to_langfuse_evaluation(score: EvalScore) -> Any:
    try:
        from langfuse import Evaluation
    except Exception:  # pragma: no cover
        return score.model_dump(mode="json")
    return Evaluation(
        name=score.name,
        value=score.value,
        comment=score.comment,
        metadata=score.metadata,
    )


def _coverage_score(expected: list[str], actual: list[str]) -> float:
    if not expected:
        return 1.0
    return round(len(_overlap(expected, actual)) / len({normalize_term(item) for item in expected}), 4)


def _text_coverage_score(expected: list[str], normalized_text: str) -> float:
    if not expected:
        return 1.0
    matches = {
        normalize_term(item)
        for item in expected
        if normalize_term(item) and normalize_term(item) in normalized_text
    }
    return round(len(matches) / len({normalize_term(item) for item in expected}), 4)


def _overlap(expected: list[str], actual: list[str]) -> set[str]:
    expected_set = {normalize_term(item) for item in expected if normalize_term(item)}
    actual_set = {normalize_term(item) for item in actual if normalize_term(item)}
    return expected_set & actual_set


def _extract_answer_sections(answer: str) -> list[str]:
    headings = [_heading_to_section_id(match.group(1)) for match in _HEADING_RE.finditer(answer)]
    return [heading for heading in headings if heading]


def _heading_to_section_id(value: str) -> str:
    return slugify(value.replace(":", " ").strip())


def _titleize(value: str) -> str:
    return value.replace("-", " ").title()


def _extract_response_text(response: Any) -> str:
    output = getattr(response, "output", []) or []
    chunks: list[str] = []
    for item in output:
        for content in getattr(item, "content", []) or []:
            text = getattr(content, "text", None)
            if text:
                chunks.append(text)
    if chunks:
        return "\n".join(chunks).strip()
    raise RuntimeError("OpenAI response did not contain text output.")


def _input_schema() -> dict[str, object]:
    return {
        "type": "object",
        "required": ["query"],
        "properties": {
            "query": {"type": "string"},
            "intent": {"type": "string"},
            "area": {"type": "string"},
            "version": {"type": "string"},
        },
        "additionalProperties": True,
    }


def _expected_output_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "expected_concepts": {"type": "array", "items": {"type": "string"}},
            "expected_sections": {"type": "array", "items": {"type": "string"}},
            "expected_terms": {"type": "array", "items": {"type": "string"}},
            "reference_answer": {"type": "string"},
        },
        "additionalProperties": True,
    }
