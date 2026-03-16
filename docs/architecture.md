# MOR Architecture

MOR implements a thin semantic runtime between user input and model execution.

```text
Markdown files
   -> Parser
   -> Internal Model
   -> Validator
   -> Runtime Services
   -> CLI / REST API / MCP
```

## Core layers

1. Parser
   Converts strict concept markdown into typed draft documents and captures structural issues.
2. Internal model
   Produces normalized concept objects, lookup indices, graph edges, and intent-aware answer requirements.
3. Validator
   Detects schema gaps, alias collisions, circular hierarchies, broken references, and orphans.
4. Runtime services
   Exposes resolution, expansion, scaffolding, metrics, and evaluation over the validated ontology.
5. Interfaces
   CLI, FastAPI, and MCP surfaces all reuse the same runtime service layer.

## Design goals

- Git-friendly authoring
- Deterministic parsing and validation
- Explainable runtime outputs
- Low dependency surface
- Open-source extensibility

