from pathlib import Path

import pytest

from mor.mcp import MORServer, MCPError


ONTOLOGY_ROOT = Path(__file__).resolve().parents[1] / "ontology"


def test_mcp_initialize_and_capabilities() -> None:
    server = MORServer(ONTOLOGY_ROOT)

    response = server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})

    assert response is not None
    result = response["result"]
    assert result["serverInfo"]["name"] == "mor"
    assert result["capabilities"]["resources"]["templates"] is True
    assert result["capabilities"]["completions"] == {}
    assert "resolve_term" in result["instructions"]
    assert result["selection"]["bundle_id"] == "paint@V1"


def test_mcp_tools_list_contains_required_v1_surface() -> None:
    server = MORServer(ONTOLOGY_ROOT)

    payload = server.list_tools()
    tool_names = {tool["name"] for tool in payload["tools"]}

    assert {
        "resolve_term",
        "get_concept",
        "get_related_concepts",
        "list_concepts",
        "expand_query",
        "explain_query_resolution",
        "compute_query_coverage",
        "validate_ontology",
        "build_answer_scaffold",
        "list_bundles",
        "get_bundle",
        "get_runtime_stats",
    }.issubset(tool_names)


def test_mcp_resolve_term_tool_returns_structured_content() -> None:
    server = MORServer(ONTOLOGY_ROOT)

    result = server.call_tool("resolve_term", {"term": "latex paint"})

    assert result["structuredContent"]["canonical"] == "emulsion paint"
    assert result["structuredContent"]["matches"][0]["match_type"] == "alias"
    assert any(item["type"] == "resource_link" for item in result["content"])


def test_mcp_resources_cover_concept_links_and_source() -> None:
    server = MORServer(ONTOLOGY_ROOT)

    concept = server.read_resource("ontology://concept/emulsion-paint")
    links = server.read_resource("ontology://concept/emulsion-paint/links")
    source = server.read_resource("ontology://concept/emulsion-paint/source")

    assert concept["mimeType"] == "application/json"
    assert '"canonical": "emulsion paint"' in concept["text"]
    assert links["mimeType"] == "application/json"
    assert '"relationship_type": "type_of"' in links["text"]
    assert source["mimeType"] == "text/markdown"
    assert "# Concept: Emulsion Paint" in source["text"]


def test_mcp_prompt_payloads_are_grounded_in_runtime_data() -> None:
    server = MORServer(ONTOLOGY_ROOT)

    prompt = server.get_prompt("ontology_guided_answer", {"query": "compare latex paint and gloss"})
    legacy_prompt = server.get_prompt(
        "ontology_guided_architecture_answer",
        {"query": "compare latex paint and gloss"},
    )

    assert prompt["name"] == "ontology_guided_answer"
    assert "resolution" in prompt["messages"][1]["content"]["text"]
    assert legacy_prompt["name"] == "ontology_guided_architecture_answer"


def test_mcp_pagination_for_resources_tools_prompts_and_tools() -> None:
    server = MORServer(ONTOLOGY_ROOT)

    resources_page = server.list_resources(limit=2)
    tools_page = server.list_tools(limit=3)
    prompts_page = server.list_prompts(limit=2)
    concepts_page = server.call_tool("list_concepts", {"limit": 5})
    bundles_page = server.call_tool("list_bundles", {"limit": 1})

    assert len(resources_page["resources"]) == 2
    assert resources_page["nextCursor"] == "2"
    assert len(tools_page["tools"]) == 3
    assert tools_page["nextCursor"] == "3"
    assert len(prompts_page["prompts"]) == 2
    assert prompts_page["nextCursor"] == "2"
    assert len(concepts_page["structuredContent"]["concepts"]) == 5
    assert concepts_page["structuredContent"]["nextCursor"] == "5"
    assert len(bundles_page["structuredContent"]["bundles"]) == 1


def test_mcp_completions_support_concepts_bundles_and_intents() -> None:
    server = MORServer(ONTOLOGY_ROOT)

    concept_completion = server.complete(
        {
            "ref": {"type": "tool", "name": "get_concept"},
            "argument": {"name": "concept_id_or_term", "value": "emul"},
        }
    )
    intent_completion = server.complete(
        {
            "ref": {"type": "tool", "name": "build_answer_scaffold"},
            "argument": {"name": "intent", "value": "arch"},
        }
    )

    assert "emulsion paint" in concept_completion["completion"]["values"]
    assert "architecture_explanation" in intent_completion["completion"]["values"]


def test_mcp_bad_params_and_unknown_resource_raise_specific_errors() -> None:
    server = MORServer(ONTOLOGY_ROOT)

    with pytest.raises(MCPError) as invalid_params:
        server.call_tool("resolve_term", {})
    with pytest.raises(MCPError) as unknown_resource:
        server.read_resource("ontology://concept/unknown")

    assert invalid_params.value.code == -32602
    assert unknown_resource.value.code == -32001


def test_mcp_explain_query_resolution_and_coverage_shapes() -> None:
    server = MORServer(ONTOLOGY_ROOT)

    explanation = server.call_tool(
        "explain_query_resolution",
        {"query": "compare latex paint viscosity and gloss"},
    )
    coverage = server.call_tool(
        "compute_query_coverage",
        {"query": "compare latex paint viscosity and gloss"},
    )

    explanation_payload = explanation["structuredContent"]
    coverage_payload = coverage["structuredContent"]

    assert explanation_payload["alias_matches"][0]["concept"]["canonical"] == "emulsion paint"
    assert "compare" in explanation_payload["unmatched_terms"]
    assert "notes" in explanation_payload
    assert coverage_payload["coverage_score"] > 0
    assert coverage_payload["covered_concepts"]
    assert "compare" in coverage_payload["unresolved_terms"]
