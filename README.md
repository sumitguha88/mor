# Markdown Ontology Runtime

Markdown Ontology Runtime (MOR) is a lightweight semantic layer for AI agents and RAG systems. Ontologies are authored in structured markdown, versioned in Git, validated at build time, and loaded into a runtime model for resolution, query expansion, answer scaffolding, explainability, and evaluation.

## What MOR provides

- Markdown-native ontology authoring
- Strict parser and validator
- Internal semantic runtime model
- Term resolution and ambiguity detection
- Query expansion and concept linking
- Answer scaffold generation
- Typer-based CLI
- FastAPI REST API
- MCP-compatible stdio server
- Streamlit ontology explorer
- Benchmark harness for baseline vs ontology-assisted flows

## Repository layout

```text
docs/
examples/
ontology/
src/mor/
tests/
```

Ontology layout:

```text
ontology/
  structure/
    markdown-concept-v1.json
  paint-manufacturing/
    V1/
      ontology.json
    V2/
      ontology.json
  marketing/
    V1/
      ontology.json
```

Each version folder owns its own `ontology.json` and points at a structure definition under `ontology/structure/`. That lets different versions adopt different markdown formats later without changing the registry layout.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
mor validate
mor resolve "grind stage"
mor expand "how do we control viscosity in decorative paint production"
mor scaffold --intent architecture_explanation --query "explain pigment dispersion and let-down in paint manufacturing"
mor resolve "paid search" --area marketing --version V1
```

Launch the ontology explorer:

```bash
pip install -e '.[dev,ui]'
mor-explorer
```

Install the optional evaluation extras:

```bash
pip install -e '.[dev,eval]'
```

## Markdown concept format

```markdown
# Concept: Pigment Dispersion

## Canonical
pigment dispersion

## Aliases
- grind stage
- pigment grind

## Definition
The process of wetting, deagglomerating, and distributing pigments uniformly through part of the formulation so the coating develops stable color, hiding power, and downstream processability.

## Related
- type: part_of_domain
  concept: paint manufacturing
- type: uses_formulation
  concept: paint formulation
- type: includes_step
  concept: milling
- type: uses_material
  concept: resin binder
- type: uses_material
  concept: solvent system

## Parents
- paint manufacturing

## NotSameAs


## QueryHints
- boost: color development
- boost: deagglomeration

## AnswerRequirements
- definition
- mechanism
- tradeoffs
- comparison
```

`Parents` is optional but supported to model hierarchies and enable circular hierarchy validation.
`Related` should use nested entries with both a relationship `type` and a target `concept`. MOR still accepts legacy flat `- concept` entries and treats them as `type: related`, but typed relationships are the preferred format.

## CLI

```bash
mor init
mor init-concept "Cache Invalidation"
mor validate
mor resolve "grind stage"
mor expand "paint viscosity control"
mor scaffold --intent architecture_explanation
mor stats
mor benchmark
mor langfuse-upload-dataset --dataset-path examples/evals/paint-v2-eval.json
mor eval-llm --dataset-path examples/evals/paint-v2-eval.json --area paint-manufacturing --version V2 --provider mock --dry-run
```

## API

```bash
uvicorn mor.api:app --reload
```

Endpoints:

- `GET /concepts`
- `GET /concepts/{id}`
- `POST /resolve`
- `POST /expand`
- `POST /validate`
- `POST /scaffold`
- `GET /stats`

## MCP server

Run a stdio MCP-compatible server:

```bash
mor serve-mcp
```

Resources:

- `ontology://index`
- `ontology://concept/{id}`

Tools:

- `resolve_term`
- `expand_query`
- `validate_ontology`
- `build_answer_scaffold`

Prompts:

- `ontology_guided_architecture_answer`
- `concept_comparison`

## Ontology Explorer

The Streamlit ontology explorer renders ontology areas as interactive graphs with node hover summaries, click-to-inspect concept properties, area/version selection, and relation filtering.

```bash
mor-explorer
```

The app defaults to [ontology/](/Users/sumitguha/Development/mor/ontology), where you can switch between the paint manufacturing and marketing ontology areas.

## Evaluation harness

MOR ships with an evaluation harness that compares a baseline lexical approach against ontology-assisted runtime behavior across:

- concept resolution success
- ontology coverage
- answer completeness
- terminology consistency

Use the bundled sample cases:

```bash
mor benchmark
```

## Langfuse Evaluation

MOR also supports LLM answer evaluation with Langfuse-backed experiments and a local dry-run mode.

Sample dataset:

- [examples/evals/paint-v2-eval.json](/Users/sumitguha/Development/mor/examples/evals/paint-v2-eval.json)

Upload the sample dataset to Langfuse:

```bash
mor langfuse-upload-dataset \
  --dataset-path examples/evals/paint-v2-eval.json \
  --dataset-name mor-paint-v2-eval
```

Run a local dry-run without Langfuse:

```bash
mor eval-llm \
  --dataset-path examples/evals/paint-v2-eval.json \
  --ontology-root ontology \
  --area paint-manufacturing \
  --version V2 \
  --mode ontology_assisted \
  --provider mock \
  --dry-run
```

Run a live experiment with an OpenAI-compatible model:

```bash
mor eval-llm \
  --dataset-path examples/evals/paint-v2-eval.json \
  --ontology-root ontology \
  --area paint-manufacturing \
  --version V2 \
  --mode ontology_assisted \
  --provider openai \
  --model gpt-4.1-mini
```

Notes:

- Langfuse upload and live experiment commands require Langfuse credentials via options or environment variables.
- In this environment, the current Langfuse SDK is not import-safe on Python `3.14`, so live Langfuse commands should be run under Python `3.12` or `3.13`.
- The local `--dry-run` path works on Python `3.14` and uses the same dataset, prompts, and deterministic evaluators.

Default ontology area: [ontology/paint-manufacturing/](/Users/sumitguha/Development/mor/ontology/paint-manufacturing) with concept files in [ontology/paint-manufacturing/V1/](/Users/sumitguha/Development/mor/ontology/paint-manufacturing/V1).

Additional domain examples:

- Marketing metadata and versioned ontology under [ontology/marketing/](/Users/sumitguha/Development/mor/ontology/marketing)
- Marketing benchmark and usage notes under [examples/marketing/](/Users/sumitguha/Development/mor/examples/marketing)

See [docs/architecture.md](docs/architecture.md) and [docs/ontology-format.md](docs/ontology-format.md) for the design details.
