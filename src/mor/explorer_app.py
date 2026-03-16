"""Streamlit ontology explorer application."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from mor.constants import MCP_SERVER_INFO, MCP_SERVER_INSTRUCTIONS, SCAFFOLD_INTENTS
from mor.registry import list_ontology_areas
from mor.runtime import OntologyRuntime
from mor.utils import json_dumps

GRAPH_HEIGHT = 720
ASSETS_DIR = Path(__file__).with_name("assets")


@lru_cache(maxsize=4)
def _asset_text(filename: str) -> str:
    return (ASSETS_DIR / filename).read_text(encoding="utf-8")


def _load_areas(root: str) -> list[dict[str, object]]:
    return [item.model_dump(mode="json") for item in list_ontology_areas(root)]


@st.cache_data(show_spinner=False)
def _load_runtime_snapshot(
    root: str,
    area: str | None,
    version: str | None,
    include_related: bool,
    include_parents: bool,
    include_not_same_as: bool,
) -> dict[str, object]:
    runtime = OntologyRuntime(root, area=area, version=version)
    graph = runtime.graph_payload(
        include_related=include_related,
        include_parents=include_parents,
        include_not_same_as=include_not_same_as,
    )
    return {
        "selection": runtime.selection.model_dump(mode="json") if runtime.selection else None,
        "stats": runtime.stats().model_dump(mode="json"),
        "concepts": [concept.model_dump(mode="json") for concept in runtime.model.concepts.values()],
        "graph": graph.model_dump(mode="json"),
    }


@st.cache_data(show_spinner=False)
def _load_mcp_surface(root: str, area: str | None, version: str | None) -> dict[str, object]:
    runtime = OntologyRuntime(root, area=area, version=version)
    bundle_id = runtime.bundle_id() or "current"
    concepts = runtime.list_concepts()
    resources = [
        {
            "uri": "ontology://index",
            "name": "Ontology Index",
            "description": "Top-level entry point for the selected ontology bundle.",
        },
        {
            "uri": f"ontology://bundle/{bundle_id}",
            "name": "Ontology Bundle",
            "description": "Bundle metadata, structure information, and concept summary for the selected area/version.",
        },
        *[
            {
                "uri": f"ontology://concept/{concept.id}",
                "name": concept.canonical,
                "description": f"Concept resource for {concept.canonical}.",
            }
            for concept in concepts
        ],
    ]
    tools = [
        {
            "name": "resolve_term",
            "description": "Resolve user terminology to a canonical ontology concept.",
            "inputSchema": {"type": "object", "properties": {"term": {"type": "string"}}, "required": ["term"]},
        },
        {
            "name": "expand_query",
            "description": "Expand a natural language query using ontology concepts and relationships.",
            "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        },
        {
            "name": "validate_ontology",
            "description": "Run validation for the selected ontology bundle.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "build_answer_scaffold",
            "description": "Create an ontology-guided answer scaffold for an intent and query.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "intent": {"type": "string"},
                    "query": {"type": "string"},
                },
                "required": ["intent"],
            },
        },
        {
            "name": "get_concept",
            "description": "Return the resolved ontology concept payload for an id or term.",
            "inputSchema": {"type": "object", "properties": {"concept": {"type": "string"}}, "required": ["concept"]},
        },
        {
            "name": "get_related_concepts",
            "description": "Return outgoing and incoming links for a concept.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "concept": {"type": "string"},
                    "relationship_type": {"type": "string"},
                },
                "required": ["concept"],
            },
        },
        {
            "name": "explain_query_resolution",
            "description": "Show how the runtime interpreted a query and which concepts were matched.",
            "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        },
        {
            "name": "compute_query_coverage",
            "description": "Estimate how well the ontology covers a natural language query.",
            "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        },
    ]
    prompts = [
        {
            "name": "ontology_guided_answer",
            "description": "Use MOR resolution, expansion, related concepts, and scaffold output before generating the final answer.",
            "arguments": [{"name": "query", "required": True}],
        },
        {
            "name": "concept_comparison",
            "description": "Compare two ontology concepts using canonical definitions, distinctions, and relationships.",
            "arguments": [{"name": "concept_a", "required": True}, {"name": "concept_b", "required": True}],
        },
    ]
    return {
        "server_info": MCP_SERVER_INFO,
        "instructions": MCP_SERVER_INSTRUCTIONS,
        "resources": resources,
        "tools": tools,
        "prompts": prompts,
    }


def run() -> None:
    st.set_page_config(page_title="MOR Ontology Explorer", layout="wide")
    st.title("Ontology Explorer")
    st.caption("Interactive graph view for MOR ontology areas and versions.")

    with st.sidebar:
        st.header("Ontology")
        ontology_root = st.text_input("Ontology Root", value="ontology")
        areas = _load_areas(ontology_root)
        if not areas:
            st.error(f"No ontology areas found under {ontology_root}")
            return

        area_options = [area["metadata"]["id"] for area in areas]
        default_area = next(
            (area["metadata"]["id"] for area in areas if area["metadata"].get("default")),
            area_options[0],
        )
        area_id = st.selectbox("Area", options=area_options, index=area_options.index(default_area))
        area_metadata = next(area["metadata"] for area in areas if area["metadata"]["id"] == area_id)
        versions = area_metadata.get("versions") or [area_metadata.get("default_version", "V1")]
        default_version = area_metadata.get("default_version", versions[0])
        version = st.selectbox("Version", options=versions, index=versions.index(default_version))

        st.header("Graph")
        include_related = st.checkbox("Related edges", value=True)
        include_parents = st.checkbox("Parent edges", value=True)
        include_not_same_as = st.checkbox("NotSameAs edges", value=True)
        show_labels = st.checkbox("Show node labels", value=True)
        show_edge_labels = st.checkbox("Show edge labels", value=False)
        layout_name = "cose"

    with st.spinner("Loading ontology graph from backend..."):
        snapshot = _load_runtime_snapshot(
            ontology_root,
            area_id,
            version,
            include_related,
            include_parents,
            include_not_same_as,
        )
    mcp_surface = _load_mcp_surface(ontology_root, area_id, version)
    runtime = OntologyRuntime(ontology_root, area=area_id, version=version)

    concepts = sorted(snapshot["concepts"], key=lambda item: item["canonical"])
    selection = snapshot["selection"] or {}
    stats = snapshot["stats"]
    metadata_text = area_metadata.get("description", "")

    st.subheader(f"{area_metadata['name']} · {selection.get('version', version)}")
    if metadata_text:
        st.write(metadata_text)

    metric_columns = st.columns(5)
    metric_columns[0].metric("Concepts", stats["concept_count"])
    metric_columns[1].metric("Aliases", stats["alias_count"])
    metric_columns[2].metric("Relations", stats["relation_count"])
    metric_columns[3].metric("Hierarchy Edges", stats["hierarchy_edge_count"])
    metric_columns[4].metric("Validation Issues", stats["validation_errors"] + stats["validation_warnings"])

    graph_tab, concepts_tab, data_tab, mcp_tab = st.tabs(["Graph", "Concepts", "Graph Data", "MCP"])
    with graph_tab:
        with st.spinner("Rendering graph..."):
            components.html(
                _graph_html(
                    snapshot["graph"],
                    show_labels=show_labels,
                    show_edge_labels=show_edge_labels,
                    layout_name=layout_name,
                ),
                height=GRAPH_HEIGHT,
                scrolling=False,
            )
        st.caption("Click any node in the graph to inspect its properties in the right-side panel.")

    with concepts_tab:
        selected_label = st.selectbox("Inspect Concept", [concept["canonical"] for concept in concepts])
        selected_concept = next(concept for concept in concepts if concept["canonical"] == selected_label)
        _render_concept_panel(selected_concept)

    with data_tab:
        st.code(json_dumps(snapshot["graph"]), language="json")

    with mcp_tab:
        _render_mcp_tab(runtime, mcp_surface)


def _graph_html(
    graph: dict[str, object],
    *,
    show_labels: bool,
    show_edge_labels: bool,
    layout_name: str,
) -> str:
    payload = {
        "nodes": [],
        "edges": [],
        "layoutName": layout_name,
        "showLabels": show_labels,
        "showEdgeLabels": show_edge_labels,
        "rootIds": [node["id"] for node in graph["nodes"] if node["group"] == "root"],
    }
    for node in graph["nodes"]:
        payload["nodes"].append(
            {
                "data": {
                    "id": node["id"],
                    "label": node["label"] if show_labels else "",
                    "canonical": node["label"],
                    "group": node["group"],
                    "definition": node["properties"]["definition"],
                    "aliases": node["properties"]["aliases"],
                    "relationships": node["properties"]["relationships"],
                    "inferred_relationships": node["properties"].get("inferred_relationships", []),
                    "related": node["properties"]["related"],
                    "parents": node["properties"]["parents"],
                    "not_same_as": node["properties"]["not_same_as"],
                    "query_hints": node["properties"]["query_hints"],
                    "answer_requirements": node["properties"]["answer_requirements"],
                    "source_path": node["properties"]["source_path"],
                    "concept_id": node["properties"]["id"],
                    "relationship_count": node["properties"].get("relationship_count", int(node.get("value", 1.0))),
                    "size": max(16, min(44, 16 + int(node.get("value", 1.0) * 1.8))),
                }
            }
        )
    for edge in graph["edges"]:
        payload["edges"].append(
            {
                "data": {
                    "id": f"{edge['source']}::{edge['relation']}::{edge['target']}",
                    "source": edge["source"],
                    "target": edge["target"],
                    "label": edge["relation"] if show_edge_labels else "",
                    "relation": edge["relation"],
                    "title": edge["title"],
                    "inferred": edge.get("inferred", False),
                }
            }
        )
    return f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <style>
      body {{
        margin: 0;
        font-family: "Avenir Next", "Segoe UI", sans-serif;
        background: linear-gradient(180deg, #f8fafc 0%, #eef2ff 100%);
        color: #0f172a;
      }}
      .wrap {{
        display: grid;
        grid-template-columns: minmax(0, 2.35fr) minmax(320px, 1fr);
        gap: 16px;
        padding: 8px;
        height: {GRAPH_HEIGHT - 18}px;
        box-sizing: border-box;
      }}
      .surface {{
        position: relative;
        border: 1px solid #cbd5e1;
        border-radius: 20px;
        background: rgba(255, 255, 255, 0.96);
        overflow: hidden;
      }}
      #cy {{
        width: 100%;
        height: 100%;
        display: block;
      }}
      .toolbar {{
        position: absolute;
        right: 14px;
        top: 14px;
        display: flex;
        gap: 8px;
        z-index: 5;
      }}
      .toolbar button {{
        width: 34px;
        height: 34px;
        border-radius: 999px;
        border: 1px solid #cbd5e1;
        background: rgba(255, 255, 255, 0.94);
        color: #334155;
        cursor: pointer;
        font-size: 18px;
      }}
      .toolbar select {{
        height: 34px;
        border-radius: 999px;
        border: 1px solid #cbd5e1;
        background: rgba(255,255,255,0.94);
        color: #334155;
        padding: 0 12px;
        font-size: 13px;
      }}
      .toolbar button:hover {{
        background: white;
      }}
      .panel {{
        overflow: auto;
        border: 1px solid #cbd5e1;
        border-radius: 20px;
        background: rgba(255, 255, 255, 0.96);
        padding: 18px;
      }}
      .eyebrow {{
        font-size: 12px;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: #64748b;
        margin-bottom: 8px;
      }}
      h2 {{
        margin: 0 0 8px 0;
        font-size: 22px;
        line-height: 1.15;
      }}
      .meta-row {{
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin-bottom: 14px;
      }}
      .meta {{
        display: inline-block;
        padding: 5px 10px;
        border-radius: 999px;
        background: #e2e8f0;
        font-size: 12px;
      }}
      .section {{
        margin-top: 14px;
        padding-top: 14px;
        border-top: 1px solid #e2e8f0;
      }}
      .section h3 {{
        margin: 0 0 8px 0;
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #475569;
      }}
      .body {{
        font-size: 14px;
        line-height: 1.55;
      }}
      ul {{
        margin: 0;
        padding-left: 18px;
      }}
      li {{
        margin: 0 0 6px 0;
      }}
      .empty {{
        color: #64748b;
        font-style: italic;
      }}
      .error {{
        border: 1px solid #fecaca;
        background: #fef2f2;
        color: #991b1b;
        border-radius: 18px;
        padding: 16px;
      }}
    </style>
  </head>
  <body>
    <div class="wrap">
      <div class="surface">
        <div class="toolbar">
          <select id="layout-select">
            <option value="cose">Force</option>
            <option value="concentric">Concentric</option>
            <option value="breadthfirst">Hierarchy</option>
            <option value="circle">Circle</option>
            <option value="grid">Grid</option>
          </select>
          <button id="zoom-in" type="button">+</button>
          <button id="zoom-out" type="button">-</button>
          <button id="reset" type="button">&#8634;</button>
        </div>
        <div id="cy"></div>
      </div>
      <div class="panel">
        <div class="eyebrow">Concept Inspector</div>
        <div id="details"></div>
      </div>
    </div>
    <script>{_asset_text("cytoscape.min.js")}</script>
    <script>
      const payload = {json.dumps(payload)};
      const details = document.getElementById("details");
      const cyRoot = document.getElementById("cy");
      const layoutSelect = document.getElementById("layout-select");
      layoutSelect.value = payload.layoutName;

      function renderList(items) {{
        if (!items || !items.length) {{
          return '<div class="empty">None</div>';
        }}
        return '<ul>' + items.map(item => `<li>${{item}}</li>`).join('') + '</ul>';
      }}

      function renderRelationships(items) {{
        if (!items || !items.length) {{
          return '<div class="empty">None</div>';
        }}
        return '<ul>' + items.map(item => `<li><strong>${{item.type}}</strong> <span>&rarr;</span> ${{item.concept}}${{item.inferred ? ' <em>(inferred)</em>' : ''}}</li>`).join('') + '</ul>';
      }}

      function renderText(value) {{
        if (!value) {{
          return '<div class="empty">None</div>';
        }}
        return `<div class="body">${{value}}</div>`;
      }}

      function renderWelcome() {{
        details.innerHTML = `
          <h2>Interactive Ontology Graph</h2>
          <div class="body">Click any node to inspect its properties in this panel. Use the zoom controls if labels overlap.</div>
        `;
      }}

      function renderConcept(node) {{
        const props = node.properties || {{}};
        details.innerHTML = `
          <h2>${{node.canonical}}</h2>
          <div class="meta-row">
            <span class="meta">${{props.id || ''}}</span>
            <span class="meta">${{node.group}}</span>
          </div>
          <div class="section"><h3>Definition</h3>${{renderText(props.definition)}}</div>
          <div class="section"><h3>Aliases</h3>${{renderList(props.aliases)}}</div>
          <div class="section"><h3>Relationships</h3>${{renderRelationships(props.relationships)}}</div>
          <div class="section"><h3>Inferred Relationships</h3>${{renderRelationships(props.inferred_relationships)}}</div>
          <div class="section"><h3>Parent Concepts</h3>${{renderList(props.parents)}}</div>
          <div class="section"><h3>Not Same As</h3>${{renderList(props.not_same_as)}}</div>
          <div class="section"><h3>Query Hints</h3>${{renderList(props.query_hints)}}</div>
          <div class="section"><h3>Answer Requirements</h3>${{renderList(props.answer_requirements)}}</div>
          <div class="section"><h3>Source File</h3><div class="body">${{props.source_path || ''}}</div></div>
        `;
      }}

      function renderError(message) {{
        details.innerHTML = `<div class="error"><h2>Graph Error</h2><div class="body">${{message}}</div></div>`;
      }}

      function focusNeighborhood(cy, node) {{
        cy.elements().addClass('muted');
        const neighborhood = node.closedNeighborhood();
        neighborhood.removeClass('muted');
        node.removeClass('muted');
        node.addClass('focused');
      }}

      function clearFocus(cy) {{
        cy.elements().removeClass('muted');
        cy.elements().removeClass('focused');
      }}

      try {{
        const cy = cytoscape({{
          container: cyRoot,
          elements: [...payload.nodes, ...payload.edges],
          style: [
            {{
              selector: 'node',
              style: {{
                'background-color': ele => nodeColor(ele.data('group')),
                'label': 'data(label)',
                'width': 'data(size)',
                'height': 'data(size)',
                'color': '#0f172a',
                'font-size': 11,
                'font-weight': 600,
                'text-wrap': 'wrap',
                'text-max-width': 96,
                'text-valign': 'bottom',
                'text-margin-y': 7,
                'text-outline-color': '#ffffff',
                'text-outline-width': 5,
                'border-width': 2,
                'border-color': '#ffffff',
                'transition-property': 'opacity, border-width, border-color',
                'transition-duration': '180ms',
              }}
            }},
            {{
              selector: 'edge',
              style: {{
                'curve-style': 'bezier',
                'width': 1.6,
                'label': 'data(label)',
                'font-size': 9,
                'color': '#475569',
                'text-background-color': 'rgba(255,255,255,0.9)',
                'text-background-opacity': 1,
                'text-background-padding': 2,
                'target-arrow-shape': ele => ele.data('relation') === 'parent' ? 'triangle' : 'none',
                'line-color': ele => edgeColor(ele.data('relation')),
                'target-arrow-color': ele => edgeColor(ele.data('relation')),
                'line-style': ele => ele.data('relation') === 'not_same_as' ? 'dashed' : (ele.data('inferred') ? 'dotted' : 'solid'),
                'opacity': 0.72,
                'arrow-scale': 0.9,
              }}
            }},
            {{
              selector: '.muted',
              style: {{
                'opacity': 0.16,
              }}
            }},
            {{
              selector: 'node.focused',
              style: {{
                'border-color': '#111827',
                'border-width': 4,
                'opacity': 1,
              }}
            }},
            {{
              selector: ':selected',
              style: {{
                'overlay-opacity': 0,
                'border-color': '#111827',
                'border-width': 4,
              }}
            }}
          ],
          wheelSensitivity: 0.18,
          minZoom: 0.35,
          maxZoom: 2.2,
          layout: layoutConfig(payload.layoutName),
        }});

        cy.on('tap', 'node', function(evt) {{
          const data = evt.target.data();
          clearFocus(cy);
          focusNeighborhood(cy, evt.target);
          renderConcept({{
            canonical: data.canonical,
            group: data.group,
            properties: data
          }});
        }});

        cy.on('tap', function(evt) {{
          if (evt.target === cy) {{
            clearFocus(cy);
            renderWelcome();
          }}
        }});

        layoutSelect.addEventListener('change', function(evt) {{
          cy.layout(layoutConfig(evt.target.value)).run();
        }});

        document.getElementById('zoom-in').addEventListener('click', () => cy.zoom({{
          level: cy.zoom() * 1.15,
          renderedPosition: {{ x: cy.width() / 2, y: cy.height() / 2 }}
        }}));
        document.getElementById('zoom-out').addEventListener('click', () => cy.zoom({{
          level: cy.zoom() / 1.15,
          renderedPosition: {{ x: cy.width() / 2, y: cy.height() / 2 }}
        }}));
        document.getElementById('reset').addEventListener('click', () => {{
          clearFocus(cy);
          cy.fit(undefined, 40);
          cy.layout(layoutConfig(layoutSelect.value)).run();
          renderWelcome();
        }});

        cy.ready(function() {{
          cy.fit(undefined, 56);
        }});

        renderWelcome();
      }} catch (error) {{
        renderError(error && error.stack ? error.stack : String(error));
      }}

      function layoutConfig(name) {{
        if (name === 'breadthfirst') {{
          return {{
            name: 'breadthfirst',
            directed: true,
            roots: payload.rootIds,
            padding: 72,
            spacingFactor: 2.1,
            avoidOverlap: true,
            nodeDimensionsIncludeLabels: true,
            animate: true
          }};
        }}
        if (name === 'concentric') {{
          return {{
            name: 'concentric',
            padding: 72,
            spacingFactor: 1.95,
            minNodeSpacing: 78,
            avoidOverlap: true,
            nodeDimensionsIncludeLabels: true,
            concentric: function(node) {{
              if (node.data('group') === 'root') return 4;
              if (node.data('group') === 'hub') return 3;
              if (node.data('group') === 'concept') return 2;
              return 1;
            }},
            levelWidth: function() {{
              return 1;
            }},
            animate: true
          }};
        }}
        if (name === 'circle') {{
          return {{
            name: 'circle',
            padding: 72,
            spacingFactor: 1.55,
            avoidOverlap: true,
            animate: true
          }};
        }}
        if (name === 'grid') {{
          return {{
            name: 'grid',
            padding: 72,
            avoidOverlap: true,
            condense: false,
            animate: true
          }};
        }}
        return {{
          name: 'cose',
          padding: 72,
          animate: true,
          fit: true,
          nodeDimensionsIncludeLabels: true,
          componentSpacing: 180,
          nodeRepulsion: 18000,
          idealEdgeLength: 180,
          edgeElasticity: 130,
          gravity: 0.08,
          nestingFactor: 0.9
        }};
      }}

      function nodeColor(group) {{
        if (group === 'root') return '#0f766e';
        if (group === 'hub') return '#1d4ed8';
        if (group === 'leaf') return '#7c3aed';
        return '#f59e0b';
      }}

      function edgeColor(relation) {{
        if (relation === 'parent') return '#2563eb';
        if (relation === 'not_same_as') return '#dc2626';
        return '#64748b';
      }}
    </script>
  </body>
</html>"""


def _render_concept_panel(concept: dict[str, object]) -> None:
    st.markdown(f"#### {concept['canonical']}")
    st.caption(concept["id"])
    st.markdown("**Definition**")
    st.write(concept["definition"])
    _render_list_section("Aliases", concept["aliases"])
    _render_relationship_section("Relationships", concept["relationships"])
    _render_relationship_section("Inferred Relationships", concept.get("inferred_relationships", []))
    _render_list_section("Parent Concepts", concept["parents"])
    _render_list_section("Not Same As", concept["not_same_as"])
    _render_list_section("Query Hints", concept["query_hints"])
    _render_list_section("Answer Requirements", concept["answer_requirements"])
    st.markdown("**Source File**")
    st.code(concept["source_path"])


def _render_list_section(title: str, items: list[str]) -> None:
    st.markdown(f"**{title}**")
    if items:
        for item in items:
            st.markdown(f"- {item}")
    else:
        st.caption("None")


def _render_relationship_section(title: str, relationships: list[dict[str, object]]) -> None:
    st.markdown(f"**{title}**")
    if relationships:
        for relationship in relationships:
            relationship_type = relationship.get("type") or relationship.get("relationship_type") or "related"
            target = relationship.get("concept") or relationship.get("target") or ""
            suffix = " _(inferred)_" if relationship.get("inferred") else ""
            st.markdown(f"- `{relationship_type}` -> {target}{suffix}")
    else:
        st.caption("None")


def _render_mcp_tab(runtime: OntologyRuntime, surface: dict[str, object]) -> None:
    resources = surface["resources"]
    tools = surface["tools"]
    prompts = surface["prompts"]
    server_info = surface["server_info"]

    st.markdown("#### MCP Surface")
    st.caption(
        "This tab presents the MCP-style surface exposed by the current ontology runtime, "
        "including resources, tools, prompts, and a playground to try them interactively."
    )
    info_columns = st.columns(4)
    info_columns[0].metric("Server", server_info.get("name", "mor"))
    info_columns[1].metric("Version", server_info.get("version", "unknown"))
    info_columns[2].metric("Resources", len(resources))
    info_columns[3].metric("Tools", len(tools))

    st.markdown("**Usage Guidance**")
    st.write(surface["instructions"])

    resource_col, tool_col = st.columns(2)
    with resource_col:
        st.markdown("**Resources**")
        for resource in resources[:12]:
            with st.container(border=True):
                st.markdown(f"`{resource['uri']}`")
                st.write(resource["name"])
                st.caption(resource["description"])
        if len(resources) > 12:
            st.caption(f"{len(resources) - 12} more concept resources available in this ontology.")

    with tool_col:
        st.markdown("**Tools**")
        for tool in tools:
            with st.container(border=True):
                st.markdown(f"`{tool['name']}`")
                st.write(tool["description"])
                st.code(json_dumps(tool["inputSchema"]), language="json")

    st.markdown("**Prompts**")
    for prompt in prompts:
        with st.container(border=True):
            st.markdown(f"`{prompt['name']}`")
            st.write(prompt["description"])
            st.code(json_dumps(prompt.get("arguments", [])), language="json")

    st.markdown("#### Try It")
    mode = st.radio("Mode", ["Tool Playground", "Resource Viewer"], horizontal=True)
    if mode == "Tool Playground":
        _render_mcp_tool_playground(runtime, tools)
    else:
        _render_mcp_resource_viewer(runtime)


def _render_mcp_tool_playground(runtime: OntologyRuntime, tools: list[dict[str, object]]) -> None:
    tool_names = [tool["name"] for tool in tools]
    selected_tool = st.selectbox("Tool", tool_names, key="mcp_tool_name")

    with st.form("mcp_tool_form"):
        term = st.text_input("Term", value="water-based paint")
        query = st.text_area(
            "Query",
            value="Which raw materials most strongly affect drying time in water-based exterior primers?",
            height=96,
        )
        concept = st.text_input("Concept", value="paint product")
        relationship_type = st.text_input("Relationship Type", value="")
        intent = st.selectbox("Intent", list(SCAFFOLD_INTENTS), index=0)
        include_inferred = st.checkbox("Include inferred relationships", value=True)
        include_incoming = st.checkbox("Include incoming relationships", value=True)
        submitted = st.form_submit_button("Run")

    if not submitted:
        return

    result = _invoke_mcp_tool(
        runtime,
        selected_tool,
        term=term,
        query=query,
        concept=concept,
        relationship_type=relationship_type or None,
        intent=intent,
        include_inferred=include_inferred,
        include_incoming=include_incoming,
    )
    st.code(json_dumps(result), language="json")


def _render_mcp_resource_viewer(runtime: OntologyRuntime) -> None:
    concept_options = [concept.id for concept in runtime.list_concepts()]
    resource_mode = st.selectbox(
        "Resource",
        ["ontology://index", f"ontology://bundle/{runtime.bundle_id()}", "ontology://concept/{id}"],
        key="mcp_resource_mode",
    )
    if resource_mode == "ontology://index":
        data = {
            "metadata": runtime.metadata().model_dump(mode="json"),
            "bundles": [bundle.model_dump(mode="json") for bundle in runtime.list_bundles()],
        }
        st.code(json_dumps(data), language="json")
        return
    if resource_mode.startswith("ontology://bundle/"):
        bundle = runtime.get_bundle(runtime.bundle_id() or "")
        st.code(json_dumps(bundle.model_dump(mode="json") if bundle else {}), language="json")
        return

    concept_id = st.selectbox("Concept Resource", concept_options, key="mcp_resource_concept")
    concept = runtime.get_concept(concept_id)
    source = runtime.concept_source(concept_id)
    data = {
        "concept": concept.model_dump(mode="json") if concept else None,
        "source": source,
    }
    st.code(json_dumps(data), language="json")


def _invoke_mcp_tool(
    runtime: OntologyRuntime,
    tool_name: str,
    *,
    term: str,
    query: str,
    concept: str,
    relationship_type: str | None,
    intent: str,
    include_inferred: bool,
    include_incoming: bool,
) -> dict[str, object]:
    if tool_name == "resolve_term":
        return runtime.resolve(term).model_dump(mode="json")
    if tool_name == "expand_query":
        return runtime.expand(query).model_dump(mode="json")
    if tool_name == "validate_ontology":
        return runtime.validate().model_dump(mode="json")
    if tool_name == "build_answer_scaffold":
        return runtime.scaffold(intent=intent, query=query).model_dump(mode="json")
    if tool_name == "get_concept":
        concept_obj = runtime.get_concept_by_term(concept)
        return concept_obj.model_dump(mode="json") if concept_obj else {"error": "Concept not found."}
    if tool_name == "get_related_concepts":
        return {
            "concept": concept,
            "links": [
                link.model_dump(mode="json")
                for link in runtime.get_related_concepts(
                    concept,
                    relationship_type=relationship_type,
                    include_inferred=include_inferred,
                    include_incoming=include_incoming,
                )
            ],
        }
    if tool_name == "explain_query_resolution":
        return runtime.explain_query_resolution(query).model_dump(mode="json")
    if tool_name == "compute_query_coverage":
        return runtime.compute_query_coverage(query).model_dump(mode="json")
    return {"error": f"Unsupported tool '{tool_name}'."}


def _node_title(properties: dict[str, object]) -> str:
    return json.dumps(properties)


if __name__ == "__main__":
    run()
