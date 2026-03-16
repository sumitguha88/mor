from pathlib import Path

from mor.mcp import MORServer


ONTOLOGY_ROOT = Path(__file__).resolve().parents[1] / "ontology"


def test_mcp_server_handlers() -> None:
    server = MORServer(ONTOLOGY_ROOT)

    tools = server.list_tools()
    assert any(tool["name"] == "resolve_term" for tool in tools)

    resource = server.read_resource("ontology://concept/pigment-dispersion")
    assert "pigment dispersion" in resource["text"]

    result = server.call_tool("resolve_term", {"term": "grind stage"})
    assert result["canonical"] == "pigment dispersion"

    prompt = server.get_prompt(
        "ontology_guided_architecture_answer",
        {"query": "paint viscosity control"},
    )
    assert prompt["name"] == "ontology_guided_architecture_answer"
    assert prompt["messages"]


def test_mcp_server_can_select_marketing_area() -> None:
    server = MORServer(ONTOLOGY_ROOT, area="marketing", version="V1")

    result = server.call_tool("resolve_term", {"term": "paid search"})

    assert result["canonical"] == "search advertising"
