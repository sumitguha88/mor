"""MCP stdio server for MOR."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from mor.constants import MCP_SERVER_INFO, MCP_SERVER_INSTRUCTIONS, SCAFFOLD_INTENTS
from mor.models import (
    BundleDetails,
    BundleSummary,
    Concept,
    ConceptLink,
    ExpandResponse,
    QueryCoverageResponse,
    QueryResolutionExplanation,
    ResolveResponse,
    ScaffoldResponse,
    StatsResponse,
    ValidationReport,
)
from mor.runtime import OntologyRuntime
from mor.utils import json_dumps, normalize_term

JSONRPC_VERSION = "2.0"
DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100
DEFAULT_PROTOCOL_VERSION = "2024-11-05"

ERROR_UNKNOWN_RESOURCE = -32001
ERROR_UNKNOWN_TOOL = -32002
ERROR_UNKNOWN_PROMPT = -32003
ERROR_UNKNOWN_COMPLETION = -32004


class MCPError(Exception):
    """Structured JSON-RPC error."""

    def __init__(self, code: int, message: str, data: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data or {}


class ToolArgsModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PromptArgsModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ResolveTermArgs(ToolArgsModel):
    term: str = Field(min_length=1, description="User term or phrase to resolve.")


class GetConceptArgs(ToolArgsModel):
    concept_id_or_term: str = Field(
        min_length=1,
        description="Concept id or canonical/alias term to fetch.",
    )


class GetRelatedConceptsArgs(ToolArgsModel):
    concept_id_or_term: str = Field(
        min_length=1,
        description="Concept id or canonical/alias term to inspect.",
    )
    relationship_type: str | None = Field(
        default=None,
        description="Optional relationship type filter.",
    )
    include_inferred: bool = Field(
        default=True,
        description="Include inferred inverse relationships when present.",
    )
    include_incoming: bool = Field(
        default=True,
        description="Include incoming neighborhood links from other concepts.",
    )


class ListConceptsArgs(ToolArgsModel):
    type: str | None = Field(
        default=None,
        description="Optional concept type or parent/category label filter.",
    )
    bundle: str | None = Field(default=None, description="Optional bundle id in '<area>@<version>' form.")
    area: str | None = Field(default=None, description="Optional ontology area id.")
    version: str | None = Field(default=None, description="Optional ontology version id such as V1.")
    tag: str | None = Field(default=None, description="Optional bundle tag filter.")
    cursor: str | None = Field(default=None, description="Opaque pagination cursor from a prior response.")
    limit: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="Page size.")


class ExpandQueryArgs(ToolArgsModel):
    query: str = Field(min_length=1, description="Natural-language query to expand.")
    max_concepts: int = Field(default=5, ge=1, le=20, description="Maximum concepts to expand from.")
    max_terms: int = Field(default=12, ge=1, le=50, description="Maximum expanded terms to return.")


class ExplainQueryResolutionArgs(ToolArgsModel):
    query: str = Field(min_length=1, description="Natural-language query to interpret.")
    max_expanded_concepts: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum expansion concepts to include in the reasoning trace.",
    )


class ComputeQueryCoverageArgs(ToolArgsModel):
    query: str = Field(min_length=1, description="Natural-language query to score for ontology coverage.")


class ValidateOntologyArgs(ToolArgsModel):
    reload: bool = Field(default=True, description="Reload ontology files before validation.")


class BuildAnswerScaffoldArgs(ToolArgsModel):
    intent: str = Field(description="Scaffold intent identifier.")
    query: str | None = Field(default=None, description="Optional user query to resolve before scaffolding.")
    concept_ids: list[str] = Field(
        default_factory=list,
        description="Optional explicit concept ids to scaffold around.",
    )
    include_evidence_slots: bool = Field(default=False, description="Include evidence slots per scaffold section.")
    include_constraints: bool = Field(default=False, description="Include answer constraints.")
    include_relationship_paths: bool = Field(
        default=False,
        description="Include ontology relationship paths between selected concepts.",
    )


class ListBundlesArgs(ToolArgsModel):
    cursor: str | None = Field(default=None, description="Opaque pagination cursor from a prior response.")
    limit: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="Page size.")


class GetBundleArgs(ToolArgsModel):
    bundle_id: str = Field(min_length=1, description="Bundle id in '<area>@<version>' form.")


class EmptyToolArgs(ToolArgsModel):
    pass


class OntologyGuidedAnswerPromptArgs(PromptArgsModel):
    query: str = Field(min_length=1, description="User query to answer with ontology guidance.")
    intent: str = Field(
        default="architecture_explanation",
        description="Scaffold intent identifier to shape the answer.",
    )
    concept_ids: list[str] = Field(
        default_factory=list,
        description="Optional explicit concept ids to force into the prompt.",
    )


class RelationshipPathExplanationPromptArgs(PromptArgsModel):
    source_concept: str = Field(min_length=1, description="Source concept id or term.")
    target_concept: str = Field(min_length=1, description="Target concept id or term.")


class ValidationFixSuggestionPromptArgs(PromptArgsModel):
    reload: bool = Field(default=True, description="Reload ontology before generating suggestions.")
    focus_concept_id: str | None = Field(default=None, description="Optional concept id to focus on.")


class ConceptComparisonPromptArgs(PromptArgsModel):
    concept_a: str = Field(min_length=1, description="First concept id or term.")
    concept_b: str = Field(min_length=1, description="Second concept id or term.")


class LegacyArchitecturePromptArgs(PromptArgsModel):
    query: str = Field(min_length=1, description="User query to answer with ontology guidance.")


@dataclass(slots=True)
class ToolDefinition:
    name: str
    description: str
    arg_model: type[ToolArgsModel]
    handler: Any
    annotations: dict[str, Any] = field(default_factory=lambda: {"readOnlyHint": True})
    completion_fields: dict[str, str] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.arg_model.model_json_schema(),
        }
        if self.annotations:
            payload["annotations"] = self.annotations
        return payload


@dataclass(slots=True)
class PromptDefinition:
    name: str
    description: str
    arg_model: type[PromptArgsModel]
    handler: Any
    completion_fields: dict[str, str] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "arguments": [
                {
                    "name": name,
                    "required": field_info.is_required(),
                    "description": field_info.description or "",
                }
                for name, field_info in self.arg_model.model_fields.items()
            ],
        }


@dataclass(slots=True)
class ToolResponse:
    structured: dict[str, Any]
    text: str
    resource_links: list[dict[str, Any]] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return {
            "content": [{"type": "text", "text": self.text}, *self.resource_links],
            "structuredContent": self.structured,
        }


class MORServer:
    """Registry-based stdio MCP server for MOR."""

    def __init__(
        self,
        ontology_root: str | Path = "ontology",
        area: str | None = None,
        version: str | None = None,
    ) -> None:
        self.runtime = OntologyRuntime(ontology_root, area=area, version=version)
        self.instructions = MCP_SERVER_INSTRUCTIONS
        self.tools: dict[str, ToolDefinition] = {}
        self.prompts: dict[str, PromptDefinition] = {}
        self.method_handlers = {
            "initialize": self._handle_initialize,
            "ping": self._handle_ping,
            "resources/list": self._handle_resources_list,
            "resources/templates/list": self._handle_resource_templates_list,
            "resources/read": self._handle_resources_read,
            "tools/list": self._handle_tools_list,
            "tools/call": self._handle_tools_call,
            "prompts/list": self._handle_prompts_list,
            "prompts/get": self._handle_prompts_get,
            "completion/complete": self._handle_completion_complete,
            "completions/complete": self._handle_completion_complete,
            "shutdown": self._handle_ping,
        }
        self.notification_methods = {"notifications/initialized"}
        self._register_tools()
        self._register_prompts()

    def list_resources(self, cursor: str | None = None, limit: int = DEFAULT_PAGE_SIZE) -> dict[str, Any]:
        resources = [
            {
                "uri": "ontology://index",
                "name": "Ontology Index",
                "description": "All concept summaries in the active MOR ontology bundle.",
                "mimeType": "application/json",
            },
            {
                "uri": "ontology://metadata",
                "name": "Ontology Metadata",
                "description": "Selected ontology area, version, structure, and bundle metadata.",
                "mimeType": "application/json",
            },
            {
                "uri": "ontology://stats",
                "name": "Runtime Stats",
                "description": "Runtime concept counts, validation summary, and bundle stats.",
                "mimeType": "application/json",
            },
            {
                "uri": "ontology://validation/latest",
                "name": "Latest Validation Report",
                "description": "Most recent validation report for the active ontology bundle.",
                "mimeType": "application/json",
            },
        ]
        metadata = self.runtime.metadata()
        if metadata.area_id:
            resources.append(
                {
                    "uri": f"ontology://area/{metadata.area_id}",
                    "name": f"Area {metadata.area_id}",
                    "description": "Metadata for the selected ontology area.",
                    "mimeType": "application/json",
                }
            )
        if metadata.version:
            resources.append(
                {
                    "uri": f"ontology://version/{metadata.version}",
                    "name": f"Version {metadata.version}",
                    "description": "Metadata for the selected ontology version within the active area context.",
                    "mimeType": "application/json",
                }
            )
        if metadata.bundle_id:
            resources.append(
                {
                    "uri": f"ontology://bundle/{metadata.bundle_id}",
                    "name": f"Bundle {metadata.bundle_id}",
                    "description": "Bundle metadata plus member concept summaries.",
                    "mimeType": "application/json",
                }
            )
        page = _paginate(resources, cursor=cursor, limit=limit)
        return {"resources": page["items"], "nextCursor": page["next_cursor"]}

    def list_resource_templates(self, cursor: str | None = None, limit: int = DEFAULT_PAGE_SIZE) -> dict[str, Any]:
        templates = [
            {
                "uriTemplate": "ontology://concept/{id}",
                "name": "Concept",
                "description": "Fetch a concept payload by id.",
                "mimeType": "application/json",
            },
            {
                "uriTemplate": "ontology://concept/{id}/links",
                "name": "Concept Links",
                "description": "Fetch the typed ontology neighborhood for a concept.",
                "mimeType": "application/json",
            },
            {
                "uriTemplate": "ontology://concept/{id}/source",
                "name": "Concept Source",
                "description": "Read the underlying markdown source for a concept.",
                "mimeType": "text/markdown",
            },
            {
                "uriTemplate": "ontology://bundle/{id}",
                "name": "Bundle",
                "description": "Fetch bundle metadata and concept membership.",
                "mimeType": "application/json",
            },
            {
                "uriTemplate": "ontology://area/{area}",
                "name": "Area",
                "description": "Fetch ontology area metadata by area id.",
                "mimeType": "application/json",
            },
            {
                "uriTemplate": "ontology://version/{version}",
                "name": "Version",
                "description": "Fetch ontology version metadata within the active area context.",
                "mimeType": "application/json",
            },
        ]
        page = _paginate(templates, cursor=cursor, limit=limit)
        return {"resourceTemplates": page["items"], "nextCursor": page["next_cursor"]}

    def read_resource(self, uri: str) -> dict[str, Any]:
        if uri == "ontology://index":
            return self._json_resource(uri, self.runtime.list_concepts())
        if uri == "ontology://metadata":
            return self._json_resource(uri, self.runtime.metadata())
        if uri == "ontology://stats":
            return self._json_resource(uri, self.runtime.stats())
        if uri == "ontology://validation/latest":
            return self._json_resource(uri, self.runtime.validate(reload=False))
        if uri.startswith("ontology://concept/"):
            return self._read_concept_resource(uri)
        if uri.startswith("ontology://bundle/"):
            bundle_id = uri.removeprefix("ontology://bundle/")
            bundle = self.runtime.get_bundle(bundle_id)
            if bundle is None:
                raise MCPError(
                    ERROR_UNKNOWN_RESOURCE,
                    f"Unknown resource '{uri}'.",
                    {"resourceType": "bundle", "bundleId": bundle_id},
                )
            return self._json_resource(uri, bundle)
        if uri.startswith("ontology://area/"):
            area_id = uri.removeprefix("ontology://area/")
            area_summary = next(
                (item for item in self.runtime.list_areas() if item.metadata.id == area_id),
                None,
            )
            if area_summary is None:
                raise MCPError(
                    ERROR_UNKNOWN_RESOURCE,
                    f"Unknown resource '{uri}'.",
                    {"resourceType": "area", "areaId": area_id},
                )
            return self._json_resource(uri, area_summary)
        if uri.startswith("ontology://version/"):
            version_id = uri.removeprefix("ontology://version/")
            bundle = self._resolve_bundle_for_version(version_id)
            return self._json_resource(uri, bundle.version_metadata)
        raise MCPError(
            ERROR_UNKNOWN_RESOURCE,
            f"Unknown resource '{uri}'.",
            {"resourceType": "unknown", "uri": uri},
        )

    def list_tools(self, cursor: str | None = None, limit: int = DEFAULT_PAGE_SIZE) -> dict[str, Any]:
        page = _paginate(
            [tool.to_payload() for tool in self.tools.values()],
            cursor=cursor,
            limit=limit,
        )
        return {"tools": page["items"], "nextCursor": page["next_cursor"]}

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        definition = self.tools.get(name)
        if definition is None:
            raise MCPError(
                ERROR_UNKNOWN_TOOL,
                f"Unknown tool '{name}'.",
                {"tool": name, "availableTools": sorted(self.tools)},
            )
        try:
            parsed_arguments = definition.arg_model.model_validate(arguments)
        except ValidationError as exc:
            raise MCPError(
                -32602,
                f"Invalid params for tool '{name}'.",
                {"tool": name, "errors": exc.errors()},
            ) from exc
        response: ToolResponse = definition.handler(parsed_arguments)
        return response.to_payload()

    def list_prompts(self, cursor: str | None = None, limit: int = DEFAULT_PAGE_SIZE) -> dict[str, Any]:
        page = _paginate(
            [prompt.to_payload() for prompt in self.prompts.values()],
            cursor=cursor,
            limit=limit,
        )
        return {"prompts": page["items"], "nextCursor": page["next_cursor"]}

    def get_prompt(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        definition = self.prompts.get(name)
        if definition is None:
            raise MCPError(
                ERROR_UNKNOWN_PROMPT,
                f"Unknown prompt '{name}'.",
                {"prompt": name, "availablePrompts": sorted(self.prompts)},
            )
        try:
            parsed_arguments = definition.arg_model.model_validate(arguments)
        except ValidationError as exc:
            raise MCPError(
                -32602,
                f"Invalid params for prompt '{name}'.",
                {"prompt": name, "errors": exc.errors()},
            ) from exc
        return definition.handler(parsed_arguments)

    def complete(self, params: dict[str, Any]) -> dict[str, Any]:
        ref = params.get("ref", {})
        argument = params.get("argument", {})
        if not isinstance(ref, dict) or not isinstance(argument, dict):
            raise MCPError(-32602, "Invalid completion params.", {"params": params})
        name = str(ref.get("name") or "")
        ref_type = str(ref.get("type") or "tool")
        argument_name = str(argument.get("name") or "")
        prefix = str(argument.get("value") or "")
        completion_type = self._completion_type_for(ref_type=ref_type, name=name, argument_name=argument_name)
        if completion_type is None:
            raise MCPError(
                ERROR_UNKNOWN_COMPLETION,
                "No completion source is registered for the requested reference.",
                {"ref": ref, "argument": argument},
            )
        values = self._completion_values(completion_type, prefix)
        return {
            "completion": {
                "values": values,
                "hasMore": False,
            }
        }

    def handle_request(self, request: dict[str, Any]) -> dict[str, Any] | None:
        request_id = request.get("id")
        method = request.get("method")
        if not isinstance(method, str):
            raise MCPError(-32600, "Invalid Request.", {"request": request})
        if method in self.notification_methods and request_id is None:
            return None
        handler = self.method_handlers.get(method)
        if handler is None:
            raise MCPError(-32601, f"Method not found: {method}.", {"method": method})
        result = handler(request.get("params", {}))
        if request_id is None:
            return None
        return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result}

    def serve_stdio(self) -> None:
        for raw_line in sys.stdin:
            line = raw_line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
                if not isinstance(request, dict):
                    raise MCPError(-32600, "Invalid Request.", {"request": request})
                response = self.handle_request(request)
            except json.JSONDecodeError as exc:
                response = self._error_response(None, MCPError(-32700, "Parse error.", {"details": str(exc)}))
            except MCPError as exc:
                response = self._error_response(self._safe_request_id(line), exc)
            except Exception as exc:  # noqa: BLE001
                response = self._error_response(None, MCPError(-32603, "Internal error.", {"details": str(exc)}))
            if response is None:
                continue
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()

    def _handle_initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        protocol_version = str(params.get("protocolVersion") or DEFAULT_PROTOCOL_VERSION)
        return {
            "protocolVersion": protocol_version,
            "serverInfo": MCP_SERVER_INFO,
            "capabilities": {
                "resources": {"listChanged": False, "subscribe": False, "templates": True},
                "tools": {"listChanged": False},
                "prompts": {"listChanged": False},
                "completions": {},
            },
            "instructions": self.instructions,
            "selection": self.runtime.metadata().model_dump(mode="json"),
        }

    def _handle_ping(self, params: dict[str, Any]) -> dict[str, Any]:
        del params
        return {}

    def _handle_resources_list(self, params: dict[str, Any]) -> dict[str, Any]:
        limit = _page_limit(params.get("limit"))
        cursor = _optional_string(params.get("cursor"))
        return self.list_resources(cursor=cursor, limit=limit)

    def _handle_resource_templates_list(self, params: dict[str, Any]) -> dict[str, Any]:
        limit = _page_limit(params.get("limit"))
        cursor = _optional_string(params.get("cursor"))
        return self.list_resource_templates(cursor=cursor, limit=limit)

    def _handle_resources_read(self, params: dict[str, Any]) -> dict[str, Any]:
        uri = params.get("uri")
        if not isinstance(uri, str) or not uri:
            raise MCPError(-32602, "resources/read requires a non-empty 'uri'.", {"params": params})
        return {"contents": [self.read_resource(uri)]}

    def _handle_tools_list(self, params: dict[str, Any]) -> dict[str, Any]:
        limit = _page_limit(params.get("limit"))
        cursor = _optional_string(params.get("cursor"))
        return self.list_tools(cursor=cursor, limit=limit)

    def _handle_tools_call(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        if not isinstance(name, str) or not name:
            raise MCPError(-32602, "tools/call requires a non-empty 'name'.", {"params": params})
        arguments = params.get("arguments", {})
        if not isinstance(arguments, dict):
            raise MCPError(-32602, "tools/call 'arguments' must be an object.", {"params": params})
        return self.call_tool(name, arguments)

    def _handle_prompts_list(self, params: dict[str, Any]) -> dict[str, Any]:
        limit = _page_limit(params.get("limit"))
        cursor = _optional_string(params.get("cursor"))
        return self.list_prompts(cursor=cursor, limit=limit)

    def _handle_prompts_get(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        if not isinstance(name, str) or not name:
            raise MCPError(-32602, "prompts/get requires a non-empty 'name'.", {"params": params})
        arguments = params.get("arguments", {})
        if not isinstance(arguments, dict):
            raise MCPError(-32602, "prompts/get 'arguments' must be an object.", {"params": params})
        return self.get_prompt(name, arguments)

    def _handle_completion_complete(self, params: dict[str, Any]) -> dict[str, Any]:
        return self.complete(params)

    def _register_tools(self) -> None:
        self._add_tool(
            ToolDefinition(
                name="resolve_term",
                description="Resolve a user term to a canonical ontology concept, including confidence and alternatives.",
                arg_model=ResolveTermArgs,
                handler=self._tool_resolve_term,
                completion_fields={"term": "concept_terms"},
            )
        )
        self._add_tool(
            ToolDefinition(
                name="get_concept",
                description="Fetch a concept by id or canonical term for ontology-guided reasoning.",
                arg_model=GetConceptArgs,
                handler=self._tool_get_concept,
                completion_fields={"concept_id_or_term": "concept_ids"},
            )
        )
        self._add_tool(
            ToolDefinition(
                name="get_related_concepts",
                description="Inspect a concept neighborhood with typed outgoing and incoming ontology links.",
                arg_model=GetRelatedConceptsArgs,
                handler=self._tool_get_related_concepts,
                completion_fields={"concept_id_or_term": "concept_ids"},
            )
        )
        self._add_tool(
            ToolDefinition(
                name="list_concepts",
                description="List concepts with optional bundle, area, version, tag, and type filters.",
                arg_model=ListConceptsArgs,
                handler=self._tool_list_concepts,
                completion_fields={
                    "bundle": "bundle_ids",
                    "area": "area_ids",
                    "version": "version_ids",
                    "tag": "bundle_tags",
                    "type": "concept_terms",
                },
            )
        )
        self._add_tool(
            ToolDefinition(
                name="expand_query",
                description="Expand a query using ontology matches, related concepts, and query hints.",
                arg_model=ExpandQueryArgs,
                handler=self._tool_expand_query,
            )
        )
        self._add_tool(
            ToolDefinition(
                name="explain_query_resolution",
                description="Explain how MOR interpreted a query, including matches, ambiguity, paths, and suppressed terms.",
                arg_model=ExplainQueryResolutionArgs,
                handler=self._tool_explain_query_resolution,
            )
        )
        self._add_tool(
            ToolDefinition(
                name="compute_query_coverage",
                description="Compute ontology coverage for a query and identify unresolved terms.",
                arg_model=ComputeQueryCoverageArgs,
                handler=self._tool_compute_query_coverage,
            )
        )
        self._add_tool(
            ToolDefinition(
                name="validate_ontology",
                description="Validate ontology source files and return a structured validation report.",
                arg_model=ValidateOntologyArgs,
                handler=self._tool_validate_ontology,
            )
        )
        self._add_tool(
            ToolDefinition(
                name="build_answer_scaffold",
                description="Build an ontology-guided answer scaffold from an intent, query, and optional concept ids.",
                arg_model=BuildAnswerScaffoldArgs,
                handler=self._tool_build_answer_scaffold,
                completion_fields={
                    "concept_ids": "concept_ids",
                    "intent": "scaffold_intents",
                },
            )
        )
        self._add_tool(
            ToolDefinition(
                name="list_bundles",
                description="List ontology bundles available from the MOR registry.",
                arg_model=ListBundlesArgs,
                handler=self._tool_list_bundles,
            )
        )
        self._add_tool(
            ToolDefinition(
                name="get_bundle",
                description="Fetch ontology bundle metadata and member concepts.",
                arg_model=GetBundleArgs,
                handler=self._tool_get_bundle,
                completion_fields={"bundle_id": "bundle_ids"},
            )
        )
        self._add_tool(
            ToolDefinition(
                name="get_runtime_stats",
                description="Return runtime stats such as concept counts, aliases, bundles, and validation summary.",
                arg_model=EmptyToolArgs,
                handler=self._tool_get_runtime_stats,
            )
        )

    def _register_prompts(self) -> None:
        self._add_prompt(
            PromptDefinition(
                name="ontology_guided_answer",
                description="Generate an ontology-guided answer prompt using canonical concepts, expansion, and scaffolding.",
                arg_model=OntologyGuidedAnswerPromptArgs,
                handler=self._prompt_ontology_guided_answer,
                completion_fields={"intent": "scaffold_intents", "concept_ids": "concept_ids"},
            )
        )
        self._add_prompt(
            PromptDefinition(
                name="relationship_path_explanation",
                description="Explain the semantic path connecting two ontology concepts.",
                arg_model=RelationshipPathExplanationPromptArgs,
                handler=self._prompt_relationship_path_explanation,
                completion_fields={"source_concept": "concept_ids", "target_concept": "concept_ids"},
            )
        )
        self._add_prompt(
            PromptDefinition(
                name="validation_fix_suggestion",
                description="Turn a validation report into concrete ontology authoring guidance.",
                arg_model=ValidationFixSuggestionPromptArgs,
                handler=self._prompt_validation_fix_suggestion,
                completion_fields={"focus_concept_id": "concept_ids"},
            )
        )
        self._add_prompt(
            PromptDefinition(
                name="concept_comparison",
                description="Compare two ontology concepts using canonical terminology and explicit semantic boundaries.",
                arg_model=ConceptComparisonPromptArgs,
                handler=self._prompt_concept_comparison,
                completion_fields={"concept_a": "concept_ids", "concept_b": "concept_ids"},
            )
        )
        self._add_prompt(
            PromptDefinition(
                name="ontology_guided_architecture_answer",
                description="Deprecated alias for ontology_guided_answer using architecture_explanation intent.",
                arg_model=LegacyArchitecturePromptArgs,
                handler=self._prompt_legacy_architecture_answer,
            )
        )

    def _add_tool(self, definition: ToolDefinition) -> None:
        self.tools[definition.name] = definition

    def _add_prompt(self, definition: PromptDefinition) -> None:
        self.prompts[definition.name] = definition

    def _tool_resolve_term(self, args: ResolveTermArgs) -> ToolResponse:
        result = self.runtime.resolve(args.term)
        links = []
        if result.concept_id:
            links.append(_concept_resource_link(result.concept_id))
        return ToolResponse(
            structured=_as_json_object(result),
            text=_resolve_summary(result),
            resource_links=links,
        )

    def _tool_get_concept(self, args: GetConceptArgs) -> ToolResponse:
        concept = self.runtime.get_concept_by_term(args.concept_id_or_term)
        if concept is None:
            raise MCPError(
                -32602,
                f"Unknown concept '{args.concept_id_or_term}'.",
                {"concept": args.concept_id_or_term},
            )
        return ToolResponse(
            structured=_as_json_object(concept),
            text=f"Loaded concept '{concept.canonical}' with {len(concept.all_relationships)} relationships.",
            resource_links=[
                _concept_resource_link(concept.id),
                _resource_link(f"ontology://concept/{concept.id}/links", "Concept Links"),
                _resource_link(
                    f"ontology://concept/{concept.id}/source",
                    "Concept Source",
                    mime_type="text/markdown",
                ),
            ],
        )

    def _tool_get_related_concepts(self, args: GetRelatedConceptsArgs) -> ToolResponse:
        concept = self.runtime.get_concept_by_term(args.concept_id_or_term)
        if concept is None:
            raise MCPError(
                -32602,
                f"Unknown concept '{args.concept_id_or_term}'.",
                {"concept": args.concept_id_or_term},
            )
        links = self.runtime.get_related_concepts(
            args.concept_id_or_term,
            relationship_type=args.relationship_type,
            include_inferred=args.include_inferred,
            include_incoming=args.include_incoming,
        )
        return ToolResponse(
            structured={
                "concept": _as_json_object(concept),
                "links": _as_json_list(links),
            },
            text=f"Found {len(links)} ontology links for '{concept.canonical}'.",
            resource_links=[
                _concept_resource_link(concept.id),
                _resource_link(f"ontology://concept/{concept.id}/links", "Concept Links"),
            ],
        )

    def _tool_list_concepts(self, args: ListConceptsArgs) -> ToolResponse:
        concepts = self.runtime.list_concepts_filtered(
            concept_type=args.type,
            bundle=args.bundle,
            area=args.area,
            version=args.version,
            tag=args.tag,
        )
        page = _paginate(_as_json_list(concepts), cursor=args.cursor, limit=args.limit)
        filter_bits = [value for value in [args.bundle, args.area, args.version, args.tag, args.type] if value]
        label = ", ".join(filter_bits) if filter_bits else "active bundle"
        return ToolResponse(
            structured={"concepts": page["items"], "nextCursor": page["next_cursor"]},
            text=f"Listed {len(page['items'])} concepts from {label}.",
        )

    def _tool_expand_query(self, args: ExpandQueryArgs) -> ToolResponse:
        result = self.runtime.expand(args.query, max_concepts=args.max_concepts, max_terms=args.max_terms)
        return ToolResponse(
            structured=_as_json_object(result),
            text=(
                f"Expanded query into {len(result.expanded_terms)} terms across "
                f"{len(result.matched_concepts)} matched concepts."
            ),
            resource_links=[_concept_resource_link(item.concept_id) for item in result.matched_concepts[:3]],
        )

    def _tool_explain_query_resolution(self, args: ExplainQueryResolutionArgs) -> ToolResponse:
        result = self.runtime.explain_query_resolution(
            args.query,
            max_expanded_concepts=args.max_expanded_concepts,
        )
        links = [
            _concept_resource_link(item.concept.concept_id)
            for item in [*result.canonical_matches, *result.alias_matches][:3]
        ]
        return ToolResponse(
            structured=_as_json_object(result),
            text=(
                f"Explained query resolution with {len(result.canonical_matches)} canonical matches, "
                f"{len(result.alias_matches)} alias matches, and {len(result.unmatched_terms)} unmatched terms."
            ),
            resource_links=links,
        )

    def _tool_compute_query_coverage(self, args: ComputeQueryCoverageArgs) -> ToolResponse:
        result = self.runtime.compute_query_coverage(args.query)
        links = [_concept_resource_link(item["concept"]["concept_id"]) for item in _as_json_object(result)["covered_concepts"][:3]]
        return ToolResponse(
            structured=_as_json_object(result),
            text=f"Coverage score is {result.coverage_score:.2f} across {len(result.covered_concepts)} covered concepts.",
            resource_links=links,
        )

    def _tool_validate_ontology(self, args: ValidateOntologyArgs) -> ToolResponse:
        result = self.runtime.validate(reload=args.reload)
        return ToolResponse(
            structured=_as_json_object(result),
            text=f"Validation completed with {result.errors} errors and {result.warnings} warnings.",
            resource_links=[_resource_link("ontology://validation/latest", "Latest Validation Report")],
        )

    def _tool_build_answer_scaffold(self, args: BuildAnswerScaffoldArgs) -> ToolResponse:
        result = self.runtime.scaffold(
            intent=args.intent,
            query=args.query,
            concept_ids=args.concept_ids or None,
            include_evidence_slots=args.include_evidence_slots,
            include_constraints=args.include_constraints,
            include_relationship_paths=args.include_relationship_paths,
        )
        concept_links = [
            _concept_resource_link(concept.id)
            for concept in self.runtime.model.concepts.values()
            if concept.canonical in result.concepts
        ]
        return ToolResponse(
            structured=_as_json_object(result),
            text=f"Built a scaffold with {len(result.sections)} sections for intent '{args.intent}'.",
            resource_links=concept_links[:4],
        )

    def _tool_list_bundles(self, args: ListBundlesArgs) -> ToolResponse:
        bundles = self.runtime.list_bundles()
        page = _paginate(_as_json_list(bundles), cursor=args.cursor, limit=args.limit)
        return ToolResponse(
            structured={"bundles": page["items"], "nextCursor": page["next_cursor"]},
            text=f"Listed {len(page['items'])} ontology bundles.",
        )

    def _tool_get_bundle(self, args: GetBundleArgs) -> ToolResponse:
        result = self.runtime.get_bundle(args.bundle_id)
        if result is None:
            raise MCPError(-32602, f"Unknown bundle '{args.bundle_id}'.", {"bundleId": args.bundle_id})
        return ToolResponse(
            structured=_as_json_object(result),
            text=f"Loaded bundle '{result.summary.id}' with {len(result.concepts)} concepts.",
            resource_links=[_resource_link(f"ontology://bundle/{result.summary.id}", "Bundle Resource")],
        )

    def _tool_get_runtime_stats(self, args: EmptyToolArgs) -> ToolResponse:
        del args
        result = self.runtime.stats()
        return ToolResponse(
            structured=_as_json_object(result),
            text=f"Runtime contains {result.concept_count} concepts across {result.bundle_count} bundles.",
            resource_links=[_resource_link("ontology://stats", "Runtime Stats")],
        )

    def _prompt_ontology_guided_answer(self, args: OntologyGuidedAnswerPromptArgs) -> dict[str, Any]:
        expansion = self.runtime.expand(args.query)
        resolution = self.runtime.explain_query_resolution(args.query)
        scaffold = self.runtime.scaffold(
            intent=args.intent,
            query=args.query,
            concept_ids=args.concept_ids or None,
            include_evidence_slots=True,
            include_constraints=True,
            include_relationship_paths=True,
        )
        return {
            "name": "ontology_guided_answer",
            "description": "Ontology-guided answer synthesis payload.",
            "messages": [
                {
                    "role": "system",
                    "content": {
                        "type": "text",
                        "text": (
                            "Answer using MOR canonical terminology. Use the resolution trace, coverage, "
                            "and scaffold to explain the domain clearly. If coverage is partial, say so."
                        ),
                    },
                },
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": json_dumps(
                            {
                                "query": args.query,
                                "intent": args.intent,
                                "resolution": _as_json_object(resolution),
                                "expansion": _as_json_object(expansion),
                                "scaffold": _as_json_object(scaffold),
                            }
                        ),
                    },
                },
            ],
        }

    def _prompt_relationship_path_explanation(self, args: RelationshipPathExplanationPromptArgs) -> dict[str, Any]:
        source = self.runtime.get_concept_by_term(args.source_concept)
        target = self.runtime.get_concept_by_term(args.target_concept)
        if source is None or target is None:
            raise MCPError(
                -32602,
                "Both source_concept and target_concept must resolve to ontology concepts.",
                {"source": args.source_concept, "target": args.target_concept},
            )
        paths = self.runtime.scaffold(
            intent="concept_comparison",
            concept_ids=[source.id, target.id],
            include_relationship_paths=True,
        ).relationship_paths
        return {
            "name": "relationship_path_explanation",
            "description": "Relationship path explanation payload.",
            "messages": [
                {
                    "role": "system",
                    "content": {
                        "type": "text",
                        "text": "Explain the semantic connection between the concepts using explicit MOR relationship paths.",
                    },
                },
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": json_dumps(
                            {
                                "source": _as_json_object(source),
                                "target": _as_json_object(target),
                                "relationship_paths": _as_json_list(paths),
                            }
                        ),
                    },
                },
            ],
        }

    def _prompt_validation_fix_suggestion(self, args: ValidationFixSuggestionPromptArgs) -> dict[str, Any]:
        report = self.runtime.validate(reload=args.reload)
        issues = report.issues
        if args.focus_concept_id:
            issues = [issue for issue in issues if issue.concept_id == args.focus_concept_id]
        return {
            "name": "validation_fix_suggestion",
            "description": "Validation-driven ontology authoring guidance payload.",
            "messages": [
                {
                    "role": "system",
                    "content": {
                        "type": "text",
                        "text": (
                            "Turn this validation report into specific authoring actions. "
                            "Prioritize structural fixes, canonical naming, and relationship hygiene."
                        ),
                    },
                },
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": json_dumps(
                            {
                                "focus_concept_id": args.focus_concept_id,
                                "report": _as_json_object(ValidationReport(
                                    valid=report.valid,
                                    errors=report.errors,
                                    warnings=report.warnings,
                                    issues=issues,
                                )),
                            }
                        ),
                    },
                },
            ],
        }

    def _prompt_concept_comparison(self, args: ConceptComparisonPromptArgs) -> dict[str, Any]:
        concept_a = self.runtime.get_concept_by_term(args.concept_a)
        concept_b = self.runtime.get_concept_by_term(args.concept_b)
        if concept_a is None or concept_b is None:
            raise MCPError(
                -32602,
                "Both concept_a and concept_b must resolve to ontology concepts.",
                {"concept_a": args.concept_a, "concept_b": args.concept_b},
            )
        scaffold = self.runtime.scaffold(
            intent="concept_comparison",
            concept_ids=[concept_a.id, concept_b.id],
            include_relationship_paths=True,
        )
        return {
            "name": "concept_comparison",
            "description": "Concept comparison payload.",
            "messages": [
                {
                    "role": "system",
                    "content": {
                        "type": "text",
                        "text": "Compare the concepts using canonical terminology, boundaries, and tradeoffs.",
                    },
                },
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": json_dumps(
                            {
                                "concept_a": _as_json_object(concept_a),
                                "concept_b": _as_json_object(concept_b),
                                "scaffold": _as_json_object(scaffold),
                            }
                        ),
                    },
                },
            ],
        }

    def _prompt_legacy_architecture_answer(self, args: LegacyArchitecturePromptArgs) -> dict[str, Any]:
        payload = self._prompt_ontology_guided_answer(
            OntologyGuidedAnswerPromptArgs(query=args.query, intent="architecture_explanation")
        )
        payload["name"] = "ontology_guided_architecture_answer"
        return payload

    def _read_concept_resource(self, uri: str) -> dict[str, Any]:
        remainder = uri.removeprefix("ontology://concept/")
        if remainder.endswith("/links"):
            concept_id = remainder.removesuffix("/links")
            concept = self.runtime.get_concept(concept_id)
            if concept is None:
                raise MCPError(
                    ERROR_UNKNOWN_RESOURCE,
                    f"Unknown resource '{uri}'.",
                    {"resourceType": "concept_links", "conceptId": concept_id},
                )
            payload = {
                "concept": _as_json_object(concept),
                "links": _as_json_list(self.runtime.get_related_concepts(concept_id)),
            }
            return {
                "uri": uri,
                "mimeType": "application/json",
                "text": json_dumps(payload),
            }
        if remainder.endswith("/source"):
            concept_id = remainder.removesuffix("/source")
            source = self.runtime.concept_source(concept_id)
            if source is None:
                raise MCPError(
                    ERROR_UNKNOWN_RESOURCE,
                    f"Unknown resource '{uri}'.",
                    {"resourceType": "concept_source", "conceptId": concept_id},
                )
            return {"uri": uri, "mimeType": "text/markdown", "text": source}
        concept_id = remainder
        concept = self.runtime.get_concept(concept_id)
        if concept is None:
            raise MCPError(
                ERROR_UNKNOWN_RESOURCE,
                f"Unknown resource '{uri}'.",
                {"resourceType": "concept", "conceptId": concept_id},
            )
        return self._json_resource(uri, concept)

    def _resolve_bundle_for_version(self, version_id: str) -> BundleDetails:
        bundles = [bundle for bundle in self.runtime.list_bundles() if bundle.version == version_id.upper()]
        if not bundles:
            raise MCPError(
                ERROR_UNKNOWN_RESOURCE,
                f"Unknown resource 'ontology://version/{version_id}'.",
                {"resourceType": "version", "version": version_id},
            )
        selected_bundle = next(
            (
                bundle
                for bundle in bundles
                if bundle.area_id == self.runtime.metadata().area_id
            ),
            bundles[0],
        )
        result = self.runtime.get_bundle(selected_bundle.id)
        if result is None or result.version_metadata is None:
            raise MCPError(
                ERROR_UNKNOWN_RESOURCE,
                f"Unknown resource 'ontology://version/{version_id}'.",
                {"resourceType": "version", "version": version_id},
            )
        return result

    def _completion_type_for(self, *, ref_type: str, name: str, argument_name: str) -> str | None:
        if ref_type in {"tool", "ref/tool"}:
            definition = self.tools.get(name)
            if definition:
                return definition.completion_fields.get(argument_name)
        if ref_type in {"prompt", "ref/prompt"}:
            definition = self.prompts.get(name)
            if definition:
                return definition.completion_fields.get(argument_name)
        return None

    def _completion_values(self, completion_type: str, prefix: str) -> list[str]:
        lowered_prefix = normalize_term(prefix)
        values: list[str]
        if completion_type == "concept_ids":
            values = sorted(
                {
                    concept.id
                    for concept in self.runtime.model.concepts.values()
                }
                | {
                    concept.canonical
                    for concept in self.runtime.model.concepts.values()
                }
            )
        elif completion_type == "concept_terms":
            values = sorted(
                {
                    concept.canonical
                    for concept in self.runtime.model.concepts.values()
                }
                | {
                    alias
                    for concept in self.runtime.model.concepts.values()
                    for alias in concept.aliases
                }
            )
        elif completion_type == "bundle_ids":
            values = [bundle.id for bundle in self.runtime.list_bundles()]
        elif completion_type == "area_ids":
            values = [area.metadata.id for area in self.runtime.list_areas()]
        elif completion_type == "version_ids":
            values = sorted({bundle.version for bundle in self.runtime.list_bundles()})
        elif completion_type == "bundle_tags":
            values = sorted({tag for bundle in self.runtime.list_bundles() for tag in bundle.tags})
        elif completion_type == "scaffold_intents":
            values = list(SCAFFOLD_INTENTS)
        else:
            values = []
        if not lowered_prefix:
            return values[:25]
        return [value for value in values if normalize_term(value).startswith(lowered_prefix)][:25]

    def _json_resource(self, uri: str, payload: BaseModel | dict[str, Any] | list[Any]) -> dict[str, Any]:
        return {
            "uri": uri,
            "mimeType": "application/json",
            "text": json_dumps(_jsonify(payload)),
        }

    def _error_response(self, request_id: Any, error: MCPError) -> dict[str, Any]:
        return {
            "jsonrpc": JSONRPC_VERSION,
            "id": request_id,
            "error": {
                "code": error.code,
                "message": error.message,
                "data": error.data,
            },
        }

    def _safe_request_id(self, raw_request: str) -> Any:
        try:
            payload = json.loads(raw_request)
        except json.JSONDecodeError:
            return None
        if isinstance(payload, dict):
            return payload.get("id")
        return None


def _as_json_object(model: BaseModel | dict[str, Any]) -> dict[str, Any]:
    result = _jsonify(model)
    if isinstance(result, dict):
        return result
    raise TypeError("Expected a JSON object.")


def _as_json_list(items: list[BaseModel] | list[dict[str, Any]] | list[Any]) -> list[Any]:
    return [_jsonify(item) for item in items]


def _jsonify(value: BaseModel | dict[str, Any] | list[Any] | Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_jsonify(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonify(item) for key, item in value.items()}
    return value


def _paginate(items: list[Any], *, cursor: str | None, limit: int) -> dict[str, Any]:
    start = _decode_cursor(cursor)
    end = start + limit
    next_cursor = str(end) if end < len(items) else None
    return {"items": items[start:end], "next_cursor": next_cursor}


def _decode_cursor(cursor: str | None) -> int:
    if cursor in {None, ""}:
        return 0
    if not str(cursor).isdigit():
        raise MCPError(-32602, "Invalid pagination cursor.", {"cursor": cursor})
    return int(str(cursor))


def _page_limit(value: Any) -> int:
    if value is None:
        return DEFAULT_PAGE_SIZE
    if not isinstance(value, int):
        raise MCPError(-32602, "Pagination limit must be an integer.", {"limit": value})
    if value < 1 or value > MAX_PAGE_SIZE:
        raise MCPError(
            -32602,
            f"Pagination limit must be between 1 and {MAX_PAGE_SIZE}.",
            {"limit": value},
        )
    return value


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise MCPError(-32602, "Expected a string value.", {"value": value})
    return value


def _resource_link(uri: str, name: str, mime_type: str = "application/json") -> dict[str, Any]:
    return {
        "type": "resource_link",
        "uri": uri,
        "name": name,
        "mimeType": mime_type,
    }


def _concept_resource_link(concept_id: str) -> dict[str, Any]:
    return _resource_link(f"ontology://concept/{concept_id}", f"Concept {concept_id}")


def _resolve_summary(result: ResolveResponse) -> str:
    if result.matched and result.canonical:
        primary = result.matches[0] if result.matches else None
        confidence = primary.confidence if primary else 1.0
        return f"Resolved '{result.term}' to '{result.canonical}' with confidence {confidence:.2f}."
    if result.ambiguous:
        return f"'{result.term}' is ambiguous across {len(result.matches)} ontology concepts."
    if result.alternatives:
        return f"No exact match for '{result.term}'. {len(result.alternatives)} alternatives were suggested."
    return f"No ontology match found for '{result.term}'."
