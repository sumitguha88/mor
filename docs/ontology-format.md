# Ontology Markdown Format

Each concept document must begin with a level-one concept header:

```markdown
# Concept: Example Concept
```

## Required sections

- `Canonical`
- `Aliases`
- `Definition`
- `Related`
- `NotSameAs`
- `QueryHints`
- `AnswerRequirements`

## Optional sections

- `Parents`

## Rules

- Use exactly one `# Concept:` header.
- Use `##` headings for sections.
- List sections must use `- item` bullets.
- `Definition` is freeform paragraph text.
- Canonical and alias matching is case-insensitive at runtime.
- References in `Related`, `Parents`, and `NotSameAs` should point to other concepts by canonical name or alias.

## Relationship format

`Related` is a typed relationship section. Each entry should specify both the relationship type and the target concept:

```markdown
## Related
- type: manufactures
  concept: paint product
- type: supplied_by
  concept: supplier
- type: uses_process
  concept: manufacturing process
```

Accepted keys for the target field are `concept`, `entity`, or `target`. Accepted keys for the relationship field are `type`, `relationship`, or `predicate`.

Legacy flat entries such as `- paint product` are still supported for backward compatibility and are interpreted as:

```markdown
- type: related
  concept: paint product
```

## Structure definition

Format definitions are stored as JSON under `ontology/structure/`. The current default format is `markdown-concept-v1.json` and declares:

- the concept header prefix
- required and optional sections
- list and text sections
- the semantic section names used for canonical term, aliases, definition, relationships, parents, and answer requirements
- accepted keys for typed relationship entries

## Repository layout

MOR supports versioned ontology areas:

```text
ontology/
  structure/
    markdown-concept-v1.json
  paint-manufacturing/
    V1/
      ontology.json
      pigment-dispersion.md
      ...
  marketing/
    V1/
      ontology.json
      campaign-management.md
      ...
```

The `ontology/structure/` folder holds configurable format definitions. Each version folder contains its own `ontology.json` with area metadata, version metadata, and a `structure` reference that points at one of those format files. This lets `V1`, `V2`, and later versions use different markdown shapes while living under the same area.

## Validation coverage

The validator reports:

- missing sections
- invalid markdown structure
- broken references
- alias conflicts
- circular hierarchies
- orphan concepts
