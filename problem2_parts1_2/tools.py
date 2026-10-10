from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class ToolError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class ToolSpec:
    name: str
    description: str
    read_only: bool
    parameters: dict
    required: tuple = field(default_factory=tuple)
    is_action: bool = False


TOOL_SPECS = (
    ToolSpec(
        name="read_ticket",
        description="Read the current case state as a plain record.",
        read_only=True,
        parameters={"case_id": "string"},
        required=("case_id",),
    ),
    ToolSpec(
        name="search_evidence",
        description="Search documentation, past issues and release notes for evidence.",
        read_only=True,
        parameters={"query": "string", "top_k": "integer"},
        required=("query",),
    ),
    ToolSpec(
        name="propose_action",
        description="Prepare a ticket change for the maintainer to approve or reject.",
        read_only=False,
        parameters={"case_id": "string", "action": "string", "payload": "object", "rationale": "string"},
        required=("case_id", "action", "payload"),
    ),
    ToolSpec(
        name="apply_action",
        description="Execute an approved proposal against the ticket interceptor.",
        read_only=False,
        parameters={"case_id": "string", "proposal_id": "string", "approval_token": "string"},
        required=("case_id", "proposal_id", "approval_token"),
        is_action=True,
    ),
)

SPECS_BY_NAME = {spec.name: spec for spec in TOOL_SPECS}


def describe_tools() -> list[dict]:
    return [
        {
            "name": spec.name,
            "description": spec.description,
            "read_only": spec.read_only,
            "parameters": spec.parameters,
            "required": list(spec.required),
            "is_action": spec.is_action,
        }
        for spec in TOOL_SPECS
    ]


def validate_args(tool: str, args: Any) -> dict:
    if tool not in SPECS_BY_NAME:
        raise ToolError("unknown_tool", f"no tool named {tool!r}")
    if not isinstance(args, dict):
        raise ToolError("bad_arguments", f"arguments for {tool} must be an object")
    spec = SPECS_BY_NAME[tool]
    for name in spec.required:
        if args.get(name) in (None, "", [], {}):
            raise ToolError("missing_argument", f"{tool} requires {name!r}")
    return dict(args)
