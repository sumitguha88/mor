# Markdown Ontology Runtime (MOR)

**Git-native ontology runtime for LLMs, agents, and RAG systems.**

MOR adds a semantic layer between raw user language and your prompts, retrieval pipeline, tool execution, answer scaffolding, MCP publishing, and evaluation.  
Instead of asking the model to infer domain meaning from text alone, MOR lets you define concepts, aliases, relationships, and answer structure explicitly in versioned markdown.

## TL;DR

- MOR is a lightweight semantic runtime for LLM applications.
- It resolves terms, expands queries, links concepts, and scaffolds answers using ontology definitions stored in markdown.
- The repository ships with a `paint` ontology as a working example, but MOR is designed for any domain.
- You can use MOR through the CLI, API, explorer, and MCP-style interfaces.

<table>
  <tr>
    <td valign="top" width="50%">
      <img src="docs/images/ontology-explorer.png" alt="MOR Ontology Explorer" width="100%" />
    </td>
    <td valign="top" width="50%">
      <img src="docs/images/mcp%20explorer.png" alt="MOR MCP Explorer" width="100%" />
    </td>
  </tr>
</table>

## Try MOR 

```bash
git clone https://github.com/sumitguha88/mor
cd mor
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev,ui,eval]'
```

The bundled `paint` ontology is there to make the framework easy to try. You can model manufacturing, supply chain, healthcare, finance, compliance, or any other domain using the same structure.

Validate the ontology:

```bash
mor validate --ontology-root ontology --area paint --version V1
```

Example output:

```json
{
  "valid": true,
  "errors": 0,
  "warnings": 0,
  "issues": []
}
```

Resolve a term:

```bash
mor resolve "latex paint" --ontology-root ontology --area paint --version V1
```

Example output:

```json
{
  "term": "latex paint",
  "matched": true,
  "ambiguous": false,
  "concept_id": "emulsion-paint",
  "canonical": "emulsion paint"
}
```

Expand a query:

```bash
mor expand "epoxy coating formula and raw materials" --ontology-root ontology --area paint --version V1
```

Example output:

```json
{
  "query": "epoxy coating formula and raw materials",
  "expanded_terms": [
    "paint formula",
    "raw material",
    "resin",
    "solvent",
    "additive"
  ],
  "explanation": "Expanded query using direct matches, ontology relations, and query hints."
}
```

Generate an answer scaffold:

```bash
mor scaffold \
  --intent architecture_explanation \
  --query "Explain how paint formula connects product and raw material" \
  --ontology-root ontology \
  --area paint \
  --version V1
```

Example output:

```json
{
  "intent": "architecture_explanation",
  "sections": [
    {"id": "definition", "title": "Definition"},
    {"id": "mechanism", "title": "Mechanism"},
    {"id": "tradeoffs", "title": "Tradeoffs"},
    {"id": "comparison", "title": "Comparison"}
  ]
}
```

### Contributor setup

```bash
git clone https://github.com/sumitguha88/mor
cd mor
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev,ui,eval]'
pytest
```

Launch the explorer:

```bash
mor-explorer
```

Run the API:

```bash
uvicorn mor.api:app --reload
```

## What MOR Changes

### Without MOR

A prompt-only or vector-only system sees terms like:

- `latex paint`
- `water-based`
- `emulsion`
- `primer`
- `drying time`

It can retrieve related documents, but it still has to guess:

- whether terms are equivalent
- which concepts are canonical
- how concepts relate
- which linked concepts matter for expansion
- what a complete answer should include

### With MOR

The runtime can make these semantics explicit:

- resolve `latex paint` -> `emulsion paint`
- expand `drying time` through linked concepts like `solvent`, `resin`, and `additive`
- distinguish `paint type` from `paint category`
- follow typed links like `defined_by`, `contains`, and `supplies`
- scaffold answers using ontology-driven sections

That means less semantic drift, less prompt guesswork, and better explainability.

## Why MOR

MOR helps when text similarity alone is not enough.

It gives you:

- **Canonical concepts** so aliases and synonyms map to the same thing
- **Typed relationships** so the runtime knows `contains`, `defined_by`, `supplied_by`, and `part_of`
- **Controlled expansion** so related terms come from ontology logic, not just vector proximity
- **Structured answers** so the model has a better plan before it writes
- **Explainability** so you can inspect how a query was interpreted
- **Git-native governance** so the domain model is versioned and reviewable

## Architecture

```text
User Query
   ↓
MOR Runtime
   ├─ resolve terms
   ├─ inspect ontology links
   ├─ expand query
   └─ build answer scaffold
   ↓
LLM / RAG / Agent
```

Authoring flow:

```text
Markdown Concepts
   ↓
Structure-aware Parser
   ↓
Semantic Model
   ↓
Validator
   ↓
CLI / API / Explorer / MCP / Eval
```

## Key Features

### Authoring

- Markdown-native ontology authoring
- Versioned ontology structures
- Git-friendly domain modeling
- Typed relationships and hierarchy support
- Structure-aware validation

### Runtime

- Canonical term resolution
- Alias handling and ambiguity detection
- Query expansion through ontology links
- Answer scaffolding
- Related-concept traversal
- Query interpretation and coverage scoring

### Interfaces

- Typer CLI
- FastAPI service
- MCP V1 surface
- Streamlit ontology explorer

### Evaluation

- Validation reports
- Benchmark harness
- Baseline vs ontology-assisted comparisons
- Langfuse-oriented evaluation workflows

## Example Domain: Paint

The repository currently uses `paint` as the sample ontology because it is easy to understand and rich enough to demonstrate multi-hop domain reasoning.

It is only an example. The same runtime can be extended to any domain.

### Example Query

Suppose a user asks:

> Which raw materials most strongly affect drying time in water-based exterior primers?

This is not just a retrieval problem. It is a multi-hop semantic reasoning problem.

A vanilla RAG pipeline may retrieve documents mentioning:

- drying time
- primer
- water-based paint
- additives
- resins

But the model still has to infer:

- `Dry Time` is a performance attribute
- `Exterior Primer` is a paint product
- `Paint Product` is defined by `Paint Formula`
- `Paint Formula` contains `Raw Material`
- `Resin`, `Solvent`, and `Additive` are different material classes

MOR makes those links explicit.

### Term resolution

- `water-based` -> `water-based paint`
- `exterior primer` -> `primer`
- `raw materials` -> `raw material`

### Relationship-aware expansion

From `drying time`, MOR can expand toward linked concepts such as:

- `resin`
- `solvent`
- `additive`

### Better answer structure

Instead of a shallow answer like:

> Drying time in water-based primers is influenced by resins, solvents, and additives.

MOR can drive a more structured answer:

- **Resins (binders)** affect film formation
- **Solvents** affect evaporation rate
- **Additives** affect drying behavior and flow

This is the core difference: MOR makes domain semantics explicit before the LLM answers.

## Authoring

MOR ontologies are authored as markdown concept files.

Example:

```markdown
# Concept: Paint Product

## Canonical
paint product

## Type
entity

## Aliases
- finished coating product
- coating product

## Definition
A finished coating item defined by a paint formula, classified by type and usage category, manufactured through a process, and evaluated through performance attributes.

## Related
- type: defined_by
  concept: paint formula
- type: has_type
  concept: paint type
- type: categorized_as
  concept: paint category
- type: has_property
  concept: performance attribute
- type: contains
  concept: raw material

## Parents
- product

## QueryHints
- boost: coating
- boost: formula

## AnswerRequirements
- definition
- relationship to formula
- relationship to raw materials
- manufacturing context
```

Authoring gives you:

- explicit concepts
- aliases and synonyms
- typed links
- answer requirements
- versioned structure evolution

Structure versioning:

```text
ontology/
  structure/
    markdown-concept-v1.json
    markdown-concept-v2.json
  paint/
    V1/
      ontology.json
      *.md
```

You can add more ontology areas the same way. `paint` is just the starter example in this repository.

## Runtime

The runtime turns ontology definitions into behavior:

- resolve user terminology to canonical concepts
- expand queries through linked concepts
- inspect relationships and semantic paths
- scaffold structured answers
- expose the ontology through CLI, API, explorer, and MCP

## Runtime Surfaces

### CLI

```bash
mor validate
mor resolve "term"
mor expand "query"
mor scaffold --intent architecture_explanation
mor stats
mor benchmark
```

### REST API

- `GET /concepts`
- `GET /concepts/{id}`
- `POST /resolve`
- `POST /expand`
- `POST /validate`
- `POST /scaffold`
- `GET /stats`

### Explorer

Launch the interactive explorer:

```bash
mor-explorer
```

## MCP Surface

MOR exposes ontology semantics to agents and MCP-aware tooling.

### Resources

Current MCP V1 resources:

- `ontology://index`
- `ontology://bundle/{id}`
- `ontology://concept/{id}`

Planned resource additions:

- `ontology://metadata`
- `ontology://concept/{id}/links`
- `ontology://validation/latest`

### Tools

Current MCP V1 tools:

- `resolve_term`
- `get_concept`
- `get_related_concepts`
- `expand_query`
- `explain_query_resolution`
- `compute_query_coverage`
- `build_answer_scaffold`
- `validate_ontology`

### Prompts

Current MCP V1 prompts:

- `ontology_guided_answer`
- `concept_comparison`

Planned prompt additions:

- `relationship_path_explanation`

### Why this matters

For agents, MCP is where the ontology stops being passive documentation and becomes an active semantic service.

An agent can:

- resolve ambiguous terms before retrieval
- inspect concept links before tool selection
- check ontology coverage before answering
- build a structured answer plan before synthesis

## MOR vs Alternatives

| Capability | Prompt-only | Vector-only RAG | MOR |
|---|---|---|---|
| Canonical term resolution | No | Partial | Yes |
| Typed relationships | No | No | Yes |
| Explainable expansion | No | Partial | Yes |
| Git-native domain model | No | No | Yes |
| MCP exposure | No | No | Yes |
| Answer scaffolding | Prompt-dependent | Prompt-dependent | Yes |
| Semantic governance | Weak | Weak | Strong |

## Good Fit

Use MOR when:

- domain terms are ambiguous or overloaded
- synonyms and aliases matter
- relationships between entities matter
- retrieval needs governed expansion
- answer structure needs to be consistent
- ontology should live in Git and be reviewed like code
- your system needs explainability for query interpretation

Good examples:

- manufacturing
- supply chain
- healthcare operations
- legal and compliance
- internal enterprise copilots
- domain-heavy support workflows

## Probably Overkill

MOR may be unnecessary when:

- your use case is a simple FAQ
- document retrieval alone is sufficient
- the domain language is already clean and stable
- you do not need semantic governance
- you do not plan to maintain ontology content over time

## Explorer

The explorer makes the ontology visible and inspectable.

Use it to browse concepts, inspect relationships, validate graph shape, and understand how MOR sees your domain model.

## Evaluation

MOR includes evaluation workflows for measuring whether ontology assistance improves runtime behavior.

Evaluation support is still under active development. The current surface is useful for validation, benchmarking, and early ontology-assisted evaluation workflows, but it should still be treated as evolving.

What you can measure:

- concept resolution success
- ontology coverage
- answer completeness
- terminology consistency

Included support:

- validation reports
- benchmark harness
- baseline vs ontology-assisted comparisons
- Langfuse-oriented evaluation flows

Example:

```bash
mor benchmark
```

Dry-run LLM evaluation:

```bash
mor eval-llm \
  --dataset-path examples/evals/paint-v2-eval.json \
  --ontology-root ontology \
  --area paint \
  --version V1 \
  --mode ontology_assisted \
  --provider mock \
  --dry-run
```

## MCP Explorer

The MCP explorer view shows the published ontology surface in a way that is easy to inspect and demo.

It lets developers see what resources, tools, and prompts are available, and provides a simple interface to try ontology operations directly from the UI.

## Docs

- [Architecture](docs/architecture.md)
- [Ontology Format](docs/ontology-format.md)
- [Structure Guide](ontology/structure/readme.md)

## Contributing

Contributions are welcome, especially in:

- ontology authoring workflows
- validation rules
- runtime reasoning features
- MCP tooling
- evaluation workflows
- domain examples

## License

See [LICENSE](LICENSE).


### Repository description

Git-native ontology runtime for LLMs, agents, and RAG systems. Resolve terms, expand queries, scaffold answers, and expose ontology semantics through CLI, API, explorer, and MCP.
