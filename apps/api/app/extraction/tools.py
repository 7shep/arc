"""Agent CLIs Arc can drive to extract a course graph.

Arc never talks to a model itself. It spawns an agent CLI the user already has installed and
signed in, and points it at Arc's own MCP server. That keeps model choice, and the cost of using
one, with the person running Arc.

Every command here is a template the user can edit in the workspace settings, because agent CLIs
change their flags often. `{prompt}` and `{mcp_config}` are substituted at run time.
"""

import shutil
from dataclasses import dataclass

MCP_SERVER_NAME = "arc"
ARC_TOOLS = (
    "get_document_metadata",
    "get_document_chunks",
    "create_candidate_node",
    "create_candidate_relationship",
    "attach_source_evidence",
)
CLAUDE_ALLOWED_TOOLS = " ".join(f"mcp__{MCP_SERVER_NAME}__{tool}" for tool in ARC_TOOLS)


@dataclass(frozen=True)
class AgentTool:
    id: str
    name: str
    executable: str
    command: str
    verified: bool
    docs_url: str


#: Known agent CLIs. `verified` marks the templates exercised against the real CLI; the others are
#: best-effort starting points the user can correct in settings without a code change.
AGENT_TOOLS: tuple[AgentTool, ...] = (
    AgentTool(
        id="claude",
        name="Claude Code",
        executable="claude",
        command=(
            'claude -p "{prompt}" --strict-mcp-config --mcp-config "{mcp_config}" '
            f'--allowed-tools {CLAUDE_ALLOWED_TOOLS} --permission-mode acceptEdits'
        ),
        verified=True,
        docs_url="https://docs.claude.com/en/docs/claude-code/cli-reference",
    ),
    AgentTool(
        id="codex",
        name="OpenAI Codex",
        executable="codex",
        command=(
            'codex exec --skip-git-repo-check '
            '-c mcp_servers.arc.command="{mcp_command}" "{prompt}"'
        ),
        verified=False,
        docs_url="https://developers.openai.com/codex/cli",
    ),
    AgentTool(
        id="gemini",
        name="Gemini CLI",
        executable="gemini",
        command='gemini --prompt "{prompt}"',
        verified=False,
        docs_url="https://github.com/google-gemini/gemini-cli",
    ),
    AgentTool(
        id="opencode",
        name="OpenCode",
        executable="opencode",
        command='opencode run "{prompt}"',
        verified=False,
        docs_url="https://opencode.ai/docs",
    ),
    AgentTool(
        id="cursor-agent",
        name="Cursor Agent",
        executable="cursor-agent",
        command='cursor-agent -p "{prompt}"',
        verified=False,
        docs_url="https://cursor.com/docs/cli",
    ),
)

AGENT_TOOLS_BY_ID = {tool.id: tool for tool in AGENT_TOOLS}


def find_executable(executable: str) -> str | None:
    return shutil.which(executable)


def detect_tools() -> list[dict[str, object]]:
    """Report every known agent CLI and where it was found on this machine."""
    return [
        {
            "id": tool.id,
            "name": tool.name,
            "executable": tool.executable,
            "path": find_executable(tool.executable),
            "available": find_executable(tool.executable) is not None,
            "default_command": tool.command,
            "verified": tool.verified,
            "docs_url": tool.docs_url,
        }
        for tool in AGENT_TOOLS
    ]


def default_tool_id() -> str | None:
    """The first installed agent CLI, in registry order."""
    for tool in AGENT_TOOLS:
        if find_executable(tool.executable):
            return tool.id
    return None
