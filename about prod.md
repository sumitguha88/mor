Markdown Ontology Runtime (MOR)

A markdown-first semantic layer for AI agents and RAG systems.

Markdown Ontology Runtime (MOR) allows developers to define domain knowledge, terminology, and reasoning constraints using simple markdown files and expose that knowledge to AI systems through APIs and agent protocols.

It provides a version-controlled semantic layer between AI systems and their data sources, enabling consistent terminology, structured reasoning, and explainable outputs.

Why This Exists

Modern AI systems often struggle with domain reasoning.

Common problems include:

inconsistent terminology

hallucinated concepts

incomplete answers

inconsistent explanations

hard-to-debug agent behavior

For example, an AI assistant answering software architecture questions might:

confuse eventual consistency with strong consistency

misapply CAP theorem

give incomplete explanations about cache invalidation

Most systems try to fix this with prompts or retrieval pipelines.

But prompts are:

hard to version

hard to validate

not reusable

not composable

Markdown Ontology Runtime introduces a persistent semantic layer that defines domain concepts explicitly.

Core Idea

Define domain knowledge in simple markdown.

Example:

# Concept: Eventual Consistency

## Canonical
eventual consistency

## Aliases
- async consistency
- eventual state convergence

## Definition
A consistency model where replicas converge to the same state if no new updates occur.

## Related
- distributed systems
- CAP theorem
- replication
- quorum reads

## NotSameAs
- strong consistency

MOR parses this into a runtime semantic model accessible to AI systems.

Core Capabilities
Markdown Ontology Authoring

Define domain concepts in structured markdown files.

Benefits:

human readable

git versioned

easy to review in pull requests

simple templates

No complex ontology tools required.

Ontology Runtime

The runtime compiles markdown files into an in-memory semantic graph.

Capabilities:

term resolution

alias normalization

concept linking

relation traversal

ontology-guided query expansion

Example:

ontology.resolve("async consistency")
→ eventual consistency
Query Expansion

Ontology relationships help expand queries.

Example:

Query:
how does eventual consistency work

Expanded:
eventual consistency
replication
distributed systems
CAP theorem
quorum reads

This improves retrieval relevance.

Answer Scaffolding

Ontology concepts define required answer structure.

Example scaffold:

Topic: Eventual Consistency

Required sections:
- definition
- mechanism
- tradeoffs
- comparison with strong consistency

Agents can use this to produce consistent answers.

Explainable AI Behavior

MOR provides reasoning traces showing how ontology influenced the result.

Example:

Query: distributed cache consistency

Resolved Concepts:
- cache invalidation
- distributed systems

Expanded Terms:
- TTL
- write-through caching
- eventual consistency

Developers can debug AI behavior easily.

RAG Integration

MOR integrates naturally with retrieval pipelines.

Example architecture:

User Query
   ↓
Ontology Expansion
   ↓
Retriever
   ↓
LLM
   ↓
Ontology Scaffold

Adapters will be provided for:

LangChain

LlamaIndex

custom RAG pipelines

Agent Integration (MCP)

MOR exposes ontology knowledge using Model Context Protocol (MCP).

Agents can access:

Resources
ontology://concept/eventual-consistency
ontology://index/concepts
Tools
resolve_term
expand_query
validate_ontology
build_answer_scaffold
Prompts
ontology_guided_architecture_answer
concept_comparison
Validation Engine

The validator ensures ontology correctness.

Checks include:

missing sections

broken references

alias conflicts

circular hierarchies

orphan concepts

Example:

Validation Report

Errors: 1
Warnings: 2

Error:
Concept "eventual consistency" missing Definition
Evaluation Framework

Measure the impact of ontology-guided reasoning.

Example:

Baseline answer completeness: 58%
Ontology-assisted: 77%

Improvement: +19%

Metrics include:

concept resolution success

terminology consistency

answer completeness

ontology coverage

CLI

MOR includes a CLI for authoring and inspection.

Examples:

mor init
mor init-concept eventual-consistency
mor validate
mor resolve "async consistency"
mor expand "distributed cache consistency"
mor scaffold --intent architecture_explanation
Repository Structure
markdown-ontology-runtime/
  docs/
  ontology/
    concepts/
    bundles/
  src/mor/
    parser/
    model/
    validator/
    resolver/
    runtime/
    api/
    mcp/
    cli/
    evaluator/
  tests/
  examples/
Example Use Cases
AI Architecture Assistants

Help AI assistants reason about distributed systems correctly.

Developer Documentation Agents

Ensure consistent explanations across documentation.

Domain-Specific RAG Systems

Improve search and reasoning in technical knowledge bases.

Agent Memory Layer

Use ontology as a structured knowledge layer for agents.