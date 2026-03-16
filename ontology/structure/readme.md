# Structure Overview

The files in this folder define ontology authoring structures for MOR.

A structure file is a JSON contract that tells MOR:

- what section headings are valid
- which sections are required
- which sections are optional
- which sections are text blocks
- which sections are list-based
- how semantic concepts like canonical term, relationships, notes, and constraints map to markdown headings
- which relationship types have configured inverse forms

This allows ontology versions to evolve their markdown schema without changing the repository layout.

# How its used

Each ontology version folder can contain its own [ontology.json](/Users/sumitguha/Development/mor/ontology/paint-manufacturing/V1/ontology.json) metadata file.

That version metadata includes a `structure` field, for example:

```json
{
  "structure": "markdown-concept-v2"
}
```

MOR uses that value to locate the corresponding structure definition in [ontology/structure](/Users/sumitguha/Development/mor/ontology/structure).

This means:

- `V1` can use one markdown structure
- `V2` can use a different structure
- future versions can introduce richer or narrower schemas without breaking older ontologies

At the moment, `markdown-concept-v2` exists as a structure definition only. Parser and validator support for its additional sections will be added when the `V3` paint ontology is introduced.

Structure files can also define an `inverse_relationships` map. MOR uses that map to infer reverse semantic links at runtime, so authors can store only one canonical relationship direction in markdown.

# V2 details

The [markdown-concept-v2.json](/Users/sumitguha/Development/mor/ontology/structure/markdown-concept-v2.json) structure extends the current concept format with additional metadata sections.

Required fields:

- `Canonical`: the primary normalized label for the concept. This is the main term MOR should treat as the authoritative name.
- `Type`: the category of concept, such as `entity`, `process`, `material`, `document`, `event`, or `metric`.
- `Aliases`: alternate labels that should resolve to the same concept during lookup.
- `Definition`: the core explanation of what the concept means in business or domain terms.
- `Related`: typed links from this concept to other concepts, for example `uses_material`, `part_of`, `supplied_by`, or `produces`.
- `NotSameAs`: concepts that may sound similar but must be treated as distinct.
- `QueryHints`: query expansion or retrieval hints that help MOR connect user language to the concept.
- `AnswerRequirements`: answer elements that should be covered when this concept is used in scaffolding, such as `definition`, `mechanism`, `comparison`, or `tradeoffs`.

Optional fields:

- `Parents`: broader parent concepts used for hierarchy and graph traversal.
- `Attributes`: important properties or characteristics of the concept.
- `ExampleQueries`: sample user questions that should map to this concept.
- `Tags`: lightweight labels for grouping, filtering, and topic organization.
- `Synonyms`: domain-equivalent terms that may be useful for semantic interpretation or downstream reasoning.
- `Notes`: freeform author notes, implementation guidance, or domain nuance.
- `Constraints`: limits, rules, conditions, or assumptions that apply to the concept.

Field guidance:

- `Canonical` should be stable and singular where possible.
- `Type` should come from a small controlled vocabulary inside a domain so authors stay consistent.
- `Aliases` are best for direct lookup variants such as abbreviations, alternate phrasing, or user language.
- `Definition` should describe meaning, not just restate the label.
- `Related` should be typed whenever possible so the graph carries semantics, not just loose connectivity.
- `NotSameAs` is especially useful where two concepts are often confused in operations, analytics, or business conversations.
- `QueryHints` should contain retrieval-oriented phrases, not long explanations.
- `AnswerRequirements` should describe what an answer must include, not the final answer text itself.
- `Attributes` should be short and property-like.
- `ExampleQueries` should be realistic questions users or analysts would actually ask.
- `Tags` should stay lightweight and broad.
- `Synonyms` can overlap with aliases, but they are intended more for semantic equivalence than direct matching policy.
- `Notes` can include nuance that should not be treated as the formal definition.
- `Constraints` should capture business rules, operational boundaries, validation conditions, or dependencies.

The intent of `V2` is to support richer domain modeling while keeping the ontology authorable in markdown.

`V2` also supports structure-level inverse mappings such as:

- `supplies` <-> `supplied_by`
- `ships_to` <-> `receives_from`
- `contains` <-> `contained_in`
- `manufactures` <-> `manufactured_on`
- `stores` <-> `stored_in`
