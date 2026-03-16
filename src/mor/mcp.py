"""Minimal MCP-compatible stdio server for MOR."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from mor.constants import MCP_SERVER_INFO
from mor.runtime import OntologyRuntime


class MORServer:
    def __init__(
        self,
        ontology_root: str | Path = "ontology",
        area: str | None = None,
        version: str | None = None,
    ) -> None:
        self.runtime = OntologyRuntime(ontology_root, area=area, version=version)

    def list_resources(self) -> list[dict[str, str]]:
        return [
            {
                "uri": "ontology://index",
                "name": "Ontology Index",
                "description": "List of ontology concepts.",
            },
            {
                "uri": "ontology://concept/{id}",
                "name": "Ontology Concept",
                "description": "A single ontology concept by id.",
            },
        ]

    def read_resource(self, uri: str) -> dict[str, Any]:
        if uri == "ontology://index":
            data = [item.model_dump(mode="json") for item in self.runtime.list_concepts()]
            return {"uri": uri, "mimeType": "application/json", "text": json.dumps(data, indent=2)}
        if uri.startswith("ontology://concept/"):
            concept_id = uri.rsplit("/", 1)[-1]
            concept = self.runtime.get_concept(concept_id)
            if concept is None:
                raise ValueError(f"Unknown concept '{concept_id}'.")
            return {
                "uri": uri,
                "mimeType": "application/json",
                "text": json.dumps(concept.model_dump(mode="json"), indent=2),
            }
        raise ValueError(f"Unknown resource '{uri}'.")

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "resolve_term",
                "description": "Resolve a term to its canonical ontology concept.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"term": {"type": "string"}},
                    "required": ["term"],
                },
            },
            {
                "name": "expand_query",
                "description": "Expand a query using ontology relations and hints.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            },
            {
                "name": "validate_ontology",
                "description": "Validate ontology markdown files.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "build_answer_scaffold",
                "description": "Generate an answer scaffold from an intent and optional query.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "intent": {"type": "string"},
                        "query": {"type": "string"},
                    },
                    "required": ["intent"],
                },
            },
        ]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "resolve_term":
            return self.runtime.resolve(arguments["term"]).model_dump(mode="json")
        if name == "expand_query":
            return self.runtime.expand(arguments["query"]).model_dump(mode="json")
        if name == "validate_ontology":
            return self.runtime.validate(reload=True).model_dump(mode="json")
        if name == "build_answer_scaffold":
            return self.runtime.scaffold(
                intent=arguments["intent"],
                query=arguments.get("query"),
            ).model_dump(mode="json")
        raise ValueError(f"Unknown tool '{name}'.")

    def list_prompts(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "ontology_guided_architecture_answer",
                "description": "Answer an architecture question using ontology-guided scaffolding.",
                "arguments": [{"name": "query", "required": True}],
            },
            {
                "name": "concept_comparison",
                "description": "Compare two ontology concepts using canonical terminology.",
                "arguments": [
                    {"name": "concept_a", "required": True},
                    {"name": "concept_b", "required": True},
                ],
            },
        ]

    def get_prompt(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "ontology_guided_architecture_answer":
            scaffold = self.runtime.scaffold(
                intent="architecture_explanation",
                query=arguments["query"],
            )
            return {
                "name": name,
                "messages": [
                    {
                        "role": "system",
                        "content": {
                            "type": "text",
                            "text": "Use the ontology scaffold and canonical terminology to answer the query.",
                        },
                    },
                    {
                        "role": "user",
                        "content": {
                            "type": "text",
                            "text": json.dumps(scaffold.model_dump(mode="json"), indent=2),
                        },
                    },
                ],
            }
        if name == "concept_comparison":
            concept_a = self.runtime.resolve(arguments["concept_a"])
            concept_b = self.runtime.resolve(arguments["concept_b"])
            return {
                "name": name,
                "messages": [
                    {
                        "role": "system",
                        "content": {
                            "type": "text",
                            "text": "Compare the two concepts using canonical ontology terminology and explicit tradeoffs.",
                        },
                    },
                    {
                        "role": "user",
                        "content": {
                            "type": "text",
                            "text": json.dumps(
                                {
                                    "concept_a": concept_a.model_dump(mode="json"),
                                    "concept_b": concept_b.model_dump(mode="json"),
                                },
                                indent=2,
                            ),
                        },
                    },
                ],
            }
        raise ValueError(f"Unknown prompt '{name}'.")

    def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        method = request.get("method")
        params = request.get("params", {})
        if method == "initialize":
            result = {"serverInfo": MCP_SERVER_INFO, "capabilities": {"resources": {}, "tools": {}, "prompts": {}}}
        elif method == "resources/list":
            result = {"resources": self.list_resources()}
        elif method == "resources/read":
            result = {"contents": [self.read_resource(params["uri"])]}
        elif method == "tools/list":
            result = {"tools": self.list_tools()}
        elif method == "tools/call":
            tool_result = self.call_tool(params["name"], params.get("arguments", {}))
            result = {"content": [{"type": "text", "text": json.dumps(tool_result, indent=2)}]}
        elif method == "prompts/list":
            result = {"prompts": self.list_prompts()}
        elif method == "prompts/get":
            result = self.get_prompt(params["name"], params.get("arguments", {}))
        else:
            raise ValueError(f"Unsupported method '{method}'.")
        return {"jsonrpc": "2.0", "id": request.get("id"), "result": result}

    def serve_stdio(self) -> None:
        for raw_line in sys.stdin:
            line = raw_line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
                response = self.handle_request(request)
            except Exception as exc:  # noqa: BLE001
                response = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32000, "message": str(exc)},
                }
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
