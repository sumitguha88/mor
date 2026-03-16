"""Graph payload builders for the ontology explorer."""

from __future__ import annotations

from collections import Counter
from html import escape
from typing import TYPE_CHECKING

from mor.models import Concept, GraphEdge, GraphNode, GraphPayload

if TYPE_CHECKING:
    from mor.runtime import OntologyRuntime


def build_graph_payload(
    runtime: OntologyRuntime,
    include_related: bool = True,
    include_parents: bool = True,
    include_not_same_as: bool = True,
) -> GraphPayload:
    concepts = runtime.model.concepts
    inbound_parents = Counter()
    node_degree = Counter()
    relation_edges: list[GraphEdge] = []
    seen_edges: set[tuple[str, str, str]] = set()

    for concept in concepts.values():
        if include_related:
            for relationship in concept.relationships:
                related_id = relationship.target_id
                if related_id is None:
                    continue
                _append_edge(
                    relation_edges,
                    seen_edges,
                    node_degree,
                    concept.id,
                    related_id,
                    relation=relationship.relationship_type,
                    title=(
                        f"{concept.canonical} {relationship.relationship_type} "
                        f"{concepts[related_id].canonical}"
                        + (" (inferred)" if relationship.inferred else "")
                    ),
                    inferred=relationship.inferred,
                )
        if include_parents:
            for parent_id in concept.parent_ids:
                inbound_parents[parent_id] += 1
                _append_edge(
                    relation_edges,
                    seen_edges,
                    node_degree,
                    concept.id,
                    parent_id,
                    relation="parent",
                    title=f"{concept.canonical} parent is {concepts[parent_id].canonical}",
                    arrows="to",
                )
        if include_not_same_as:
            for other_id in concept.not_same_as_ids:
                pair_key = tuple(sorted((concept.id, other_id)))
                if (pair_key[0], pair_key[1], "not_same_as") in seen_edges:
                    continue
                _append_edge(
                    relation_edges,
                    seen_edges,
                    node_degree,
                    pair_key[0],
                    pair_key[1],
                    relation="not_same_as",
                    title=f"{concepts[pair_key[0]].canonical} is not the same as {concepts[pair_key[1]].canonical}",
                    dashes=True,
                )

    nodes = [
        GraphNode(
            id=concept.id,
            label=concept.canonical,
            group=_node_group(concept.id, concepts, inbound_parents),
            title=_concept_tooltip(concept),
            properties={
                "id": concept.id,
                "canonical": concept.canonical,
                "aliases": concept.aliases,
                "definition": concept.definition,
                "relationships": [
                    {
                        "type": relationship.relationship_type,
                        "concept": relationship.target,
                        "concept_id": relationship.target_id,
                        "inferred": relationship.inferred,
                    }
                    for relationship in concept.relationships
                ],
                "inferred_relationships": [
                    {
                        "type": relationship.relationship_type,
                        "concept": relationship.target,
                        "concept_id": relationship.target_id,
                        "inferred": True,
                    }
                    for relationship in concept.inferred_relationships
                ],
                "related": concept.related,
                "related_ids": concept.related_ids,
                "parents": concept.parents,
                "parent_ids": concept.parent_ids,
                "not_same_as": concept.not_same_as,
                "not_same_as_ids": concept.not_same_as_ids,
                "query_hints": concept.query_hints,
                "answer_requirements": concept.answer_requirements,
                "source_path": str(concept.source_path),
                "relationship_count": node_degree[concept.id],
            },
            value=max(1.0, float(node_degree[concept.id])),
        )
        for concept in concepts.values()
    ]

    return GraphPayload(
        area_id=runtime.model.area_id,
        version=runtime.model.version,
        nodes=sorted(nodes, key=lambda item: item.label),
        edges=sorted(relation_edges, key=lambda item: (item.relation, item.source, item.target)),
    )


def _append_edge(
    edges: list[GraphEdge],
    seen_edges: set[tuple[str, str, str]],
    node_degree: Counter[str],
    source: str,
    target: str,
    relation: str,
    title: str,
    arrows: str | None = None,
    dashes: bool = False,
    inferred: bool = False,
) -> None:
    key = (source, target, relation)
    if key in seen_edges:
        return
    seen_edges.add(key)
    node_degree[source] += 1
    node_degree[target] += 1
    edges.append(
        GraphEdge(
            source=source,
            target=target,
            relation=relation,
            title=title,
            arrows=arrows,
            dashes=dashes,
            inferred=inferred,
        )
    )


def _node_group(concept_id: str, concepts: dict[str, Concept], inbound_parents: Counter[str]) -> str:
    concept = concepts[concept_id]
    parent_count = len(concept.parent_ids)
    related_count = len(concept.relationships)
    if parent_count == 0:
        return "root"
    if related_count == 0 and inbound_parents[concept_id] == 0:
        return "leaf"
    if inbound_parents[concept_id] > 0 or related_count >= 4:
        return "hub"
    return "concept"


def _concept_tooltip(concept: Concept) -> str:
    sections = [
        ("Canonical", concept.canonical),
        ("Aliases", ", ".join(concept.aliases) or "-"),
        ("Definition", concept.definition),
        (
            "Relationships",
            ", ".join(
                f"{relationship.relationship_type} -> {relationship.target}"
                for relationship in concept.relationships
            )
            or "-",
        ),
        (
            "Inferred Relationships",
            ", ".join(
                f"{relationship.relationship_type} -> {relationship.target}"
                for relationship in concept.inferred_relationships
            )
            or "-",
        ),
        ("Parents", ", ".join(concept.parents) or "-"),
        ("NotSameAs", ", ".join(concept.not_same_as) or "-"),
        ("QueryHints", ", ".join(concept.query_hints) or "-"),
        ("AnswerRequirements", ", ".join(concept.answer_requirements) or "-"),
    ]
    lines = [f"<b>{escape(title)}</b><br>{escape(value)}" for title, value in sections]
    return "<br><br>".join(lines)
