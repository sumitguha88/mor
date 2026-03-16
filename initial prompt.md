You are a senior open-source software architect.

Design and implement an open-source framework called:

Markdown Ontology Runtime (MOR)

The framework provides a markdown-based ontology layer that improves reliability of AI agents and RAG systems.

The goal is to create a lightweight semantic layer between user queries and AI models.

The ontology is authored in structured markdown files stored in Git.

The system parses these files into a runtime semantic model used for:

- term resolution
- query expansion
- concept linking
- answer scaffolding
- reasoning explainability

The framework must be production quality and open-source friendly.

================================

PRIMARY FEATURES

1. Markdown ontology authoring
2. Ontology parser
3. Internal semantic model
4. Ontology validator
5. Term resolver
6. Query expansion engine
7. Answer scaffold generator
8. CLI tools
9. REST API
10. MCP server
11. Evaluation harness

================================

ARCHITECTURE

Markdown files
   ↓
Parser
   ↓
Internal Model
   ↓
Validator
   ↓
Runtime Services
   ↓
CLI / API / MCP

================================

MARKDOWN FORMAT

Concept files follow a strict schema.

Example:

# Concept: Eventual Consistency

## Canonical
eventual consistency

## Aliases
- async consistency
- eventual state convergence

## Definition
A consistency model in distributed systems where replicas converge to the same state if no new updates occur.

## Related
- distributed systems
- CAP theorem
- replication
- quorum reads

## NotSameAs
- strong consistency

## QueryHints
- boost: replication
- boost: quorum

## AnswerRequirements
- mechanism
- tradeoffs
- comparison with strong consistency

================================

VALIDATOR REQUIREMENTS

Validator must detect:

- missing sections
- invalid markdown structure
- broken references
- alias conflicts
- circular hierarchies
- orphan concepts

Output structured validation reports.

================================

RESOLVER

Resolver must:

- map aliases to canonical concepts
- support case-insensitive matching
- detect ambiguous terms
- provide alternative matches

Example:

resolve("async consistency")
→ eventual consistency

================================

QUERY EXPANSION

Expand queries using ontology relations.

Example:

query:
distributed cache consistency

expanded:
cache invalidation
eventual consistency
replication
distributed systems

================================

ANSWER SCAFFOLD

Ontology defines answer structure.

Example:

intent: architecture_explanation

sections:
- definition
- mechanism
- tradeoffs
- comparison

================================

CLI

Commands:

mor init
mor init-concept <name>
mor validate
mor resolve <term>
mor expand "<query>"
mor scaffold --intent architecture_explanation
mor stats
mor benchmark

================================

REST API

Use FastAPI.

Endpoints:

GET /concepts
GET /concepts/{id}
POST /resolve
POST /expand
POST /validate
POST /scaffold
GET /stats

================================

MCP SERVER

Expose ontology via:

Resources
ontology://concept/{id}
ontology://index

Tools
resolve_term
expand_query
validate_ontology
build_answer_scaffold

Prompts
ontology_guided_architecture_answer
concept_comparison

================================

EVALUATION HARNESS

Implement a benchmark framework that compares:

baseline
vs
ontology-assisted

Metrics:

concept resolution success
ontology coverage
answer completeness
terminology consistency

================================

REPOSITORY STRUCTURE

project/
 docs/
 ontology/
 src/mor/
 tests/
 examples/

================================

IMPLEMENTATION

Language: Python

Libraries:

FastAPI
Pydantic
Typer
pytest