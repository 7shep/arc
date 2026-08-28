"""Run a user's agent CLI against Arc's MCP server to extract one document's graph."""

import json
import os
import shlex
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.extraction.tools import MCP_SERVER_NAME

EXTRACTION_TIMEOUT_SECONDS = 900
OUTPUT_LIMIT = 2_000

PROMPT = (
    "You are building a course knowledge graph for Arc. Use only the Arc MCP tools. "
    "Read every chunk of document {document_id} in course {course_id} with get_document_chunks, "
    "paging until no chunks remain. For each distinct concept, definition, formula, example, or "
    "assignment the document teaches, call create_candidate_node with the exact course_id and "
    "document_id, a source_location taken from the chunk, a verbatim excerpt that supports it, "
    "and an honest confidence between 0 and 1. Then call create_candidate_relationship to connect "
    "them, preferring REQUIRES for prerequisites, DEFINED_IN and TAUGHT_IN for where something is "
    "introduced, and RELATED_TO otherwise. Reuse an existing node instead of inventing a near "
    "duplicate. Never invent content that is not in the excerpts. Do not write files or run other "
    "commands. Reply with a one line summary when you are finished."
)


class ExtractionUnavailable(RuntimeError):
    """The configured agent CLI is missing or not configured."""


class ExtractionFailed(RuntimeError):
    """The agent CLI ran but did not finish successfully."""


@dataclass(frozen=True)
class ExtractionResult:
    command: str
    output: str


def split_command(command: str) -> list[str]:
    """Split a command template into argv.

    Windows needs `posix=False` so backslashes in paths survive, but that keeps the surrounding
    quotes on each token. subprocess re-quotes arguments itself, so strip them back off or the
    agent receives a quoted path and rejects it.
    """
    tokens = shlex.split(command, posix=os.name != "nt")
    if os.name != "nt":
        return tokens
    return [
        token[1:-1] if len(token) > 1 and token[0] == token[-1] == '"' else token
        for token in tokens
    ]


def mcp_server_command() -> str:
    """Path to the arc-mcp entry point in the interpreter running Arc."""
    script = Path(sys.executable).parent / ("arc-mcp.exe" if os.name == "nt" else "arc-mcp")
    return str(script) if script.exists() else f"{sys.executable} -m app.mcp.server"


def build_mcp_config(directory: Path) -> Path:
    """Write an MCP config that exposes only Arc, with auto approval switched on."""
    command, *arguments = split_command(mcp_server_command())
    settings = get_settings()
    config = {
        "mcpServers": {
            MCP_SERVER_NAME: {
                "command": command,
                "args": arguments,
                "env": {
                    "DATABASE_URL": settings.database_url,
                    "UPLOAD_DIR": str(settings.upload_dir),
                    "ARC_AUTO_APPROVE": "1",
                },
            }
        }
    }
    path = directory / "arc-mcp.json"
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return path


def render_command(template: str, *, course_id: str, document_id: str, mcp_config: Path) -> str:
    prompt = PROMPT.format(course_id=course_id, document_id=document_id)
    return template.format(
        prompt=prompt.replace('"', "'"),
        mcp_config=str(mcp_config).replace("\\", "/"),
        mcp_command=mcp_server_command().replace("\\", "/"),
        course_id=course_id,
        document_id=document_id,
    )


Runner = Callable[[list[str], Path], subprocess.CompletedProcess[str]]


def _run(argv: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=EXTRACTION_TIMEOUT_SECONDS,
        check=False,
    )


def run_extraction(
    *,
    command_template: str,
    course_id: str,
    document_id: str,
    runner: Runner = _run,
) -> ExtractionResult:
    """Spawn the configured agent CLI and wait for it to finish.

    Raises `ExtractionUnavailable` when the CLI is not installed, and `ExtractionFailed` when it
    exits non-zero or times out. Either way the caller keeps the document's chunks.
    """
    if not command_template.strip():
        raise ExtractionUnavailable("No extraction command is configured")
    with tempfile.TemporaryDirectory(prefix="arc-extraction-") as directory:
        working_directory = Path(directory)
        config = build_mcp_config(working_directory)
        command = render_command(
            command_template,
            course_id=course_id,
            document_id=document_id,
            mcp_config=config,
        )
        argv = split_command(command)
        if not argv:
            raise ExtractionUnavailable("No extraction command is configured")
        if shutil_which(argv[0]) is None:
            raise ExtractionUnavailable(
                f"{argv[0]} is not installed or not on PATH for the Arc API process"
            )
        try:
            completed = runner(argv, working_directory)
        except subprocess.TimeoutExpired as error:
            raise ExtractionFailed(
                f"{argv[0]} did not finish within {EXTRACTION_TIMEOUT_SECONDS} seconds"
            ) from error
        except OSError as error:
            raise ExtractionUnavailable(f"{argv[0]} could not be started: {error}") from error
        output = ((completed.stdout or "") + (completed.stderr or "")).strip()
        if completed.returncode != 0:
            raise ExtractionFailed(
                f"{argv[0]} exited with code {completed.returncode}: {output[-OUTPUT_LIMIT:]}"
                or f"{argv[0]} exited with code {completed.returncode}"
            )
        return ExtractionResult(command=command, output=output[-OUTPUT_LIMIT:])


def shutil_which(executable: str) -> str | None:
    """Indirection kept separate so tests can spawn a fake command."""
    from shutil import which

    quoted = executable.strip('"')
    return which(quoted) or (quoted if Path(quoted).exists() else None)
