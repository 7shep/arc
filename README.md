# Arc

Arc is a multi-agent academic knowledge system in its foundation stage. Students can create course workspaces, upload and process source material, and inspect a structured course graph. Knowledge extraction and agents are not implemented yet.

## Current MVP

- Create and list courses
- Upload `.pdf`, `.md`, `.txt`, and `.docx` sources to local storage
- Process uploaded sources into ordered, source-aware document chunks
- Store source metadata and processing state in PostgreSQL
- Query a SQL-backed course graph through an abstract graph service
- Author, archive, search, and traverse graph records with source-document evidence
- Expose reviewable, source-backed graph extraction tools over MCP
- Review, approve, reject, edit, and merge proposed graph records before they join the graph
- Explore course metrics, recent uploads, sources, and an interactive graph
- Build the course graph automatically on upload by running an agent CLI the user already has
- Choose that agent, or edit its command, in workspace settings
- Track per-source progress, failure reasons, and the graph records each source produced
- Seed a demonstrable MATH221 Vector Calculus graph

## Architecture

```mermaid
flowchart LR
    Web[Next.js workspace] --> API[FastAPI REST API]
    API --> Courses[Course module]
    API --> Documents[Document module]
    Documents --> Storage[StorageProvider]
    Storage --> Local[Local filesystem]
    API --> Graph[CourseGraph interface]
    Graph --> SQL[SQL graph implementation]
    Courses --> PG[(PostgreSQL)]
    Documents --> PG
    SQL --> PG
    Documents --> Ingestion[Document ingestion]
    Ingestion --> Storage
    Ingestion --> PG
    Agents[Future agents] -.-> Graph
```

The repository is a pnpm monorepo. `apps/web` owns presentation and browser interactions, `apps/api` owns domain and persistence behavior, and `packages/shared` contains dependency-free TypeScript contracts.

## Local setup

Prerequisites: Node.js 22+, pnpm 11+, Python 3.12+, Docker with Compose.

1. Review `.env.example`. The documented local commands work with application defaults; export any values you want to override in your shell.
2. Start PostgreSQL:

   ```bash
   docker compose up -d postgres
   ```

3. Create and seed the API:

   ```bash
   cd apps/api
   python -m venv .venv
   # Windows: .venv\Scripts\activate
   # macOS/Linux: source .venv/bin/activate
   python -m pip install -e ".[dev]"
   python -m app.migrate   # only needed for a database created before the review workflow
   python -m app.seed
   uvicorn app.main:app --reload --port 8000
   ```

4. In a second terminal, start the web application:

   ```bash
   pnpm install
   pnpm dev
   ```

Open [http://localhost:3000](http://localhost:3000). API documentation is available at [http://localhost:8000/docs](http://localhost:8000/docs).

## Environment variables

| Variable | Purpose | Default |
| --- | --- | --- |
| `DATABASE_URL` | SQLAlchemy database connection | Local Arc PostgreSQL |
| `UPLOAD_DIR` | Local source storage root | `./uploads` |
| `MAX_UPLOAD_SIZE_MB` | Per-file upload limit | `25` |
| `WEB_ORIGIN` | Allowed browser origin for CORS | `http://localhost:3000` |
| `ARC_AUTO_EXTRACT` | Run the extraction agent after an upload | `1` |
| `NEXT_PUBLIC_API_URL` | API URL used by the frontend | `http://localhost:8000` |

Run checks from the repository root:

```bash
pnpm lint
pnpm typecheck
pnpm test
pnpm build
cd apps/api
python -m pytest
python -m ruff check .
```

The API tests use SQLite by default. To run the same suite against the Compose PostgreSQL
service, set `ARC_TEST_DATABASE_URL` for the test process:

```bash
cd apps/api
ARC_TEST_DATABASE_URL=postgresql+psycopg://arc:arc@localhost:5432/arc python -m pytest
```

## Automatic graph building

```text
upload document → chunk it → Arc spawns your agent CLI → the agent reads chunks over MCP →
nodes and relationships with evidence → course graph → graph view
```

Uploading a source is the only step a user takes. Arc chunks the file in the background, then runs
an AI coding agent **you already have installed and signed in** — Claude Code, Codex, Gemini CLI,
OpenCode, or Cursor Agent — against its own MCP server. Arc holds no API key and no model
credentials; the model usage is billed to whoever runs Arc, through their existing subscription.

Pick the agent, or edit the command Arc runs, at `/settings`. Arc detects which CLIs are on `PATH`
and substitutes `{prompt}` and `{mcp_config}` into the command template.

Extraction writes straight into the course graph. A concept the agent has already recorded is
reused rather than duplicated, so re-reading a source or covering the same topic across several
lectures folds into one node with evidence from every document. Every node and relationship keeps
the excerpt, page or section, and document it came from.

If no agent is installed, or the agent fails, the document keeps its chunks and the source row
explains why with a retry. Nothing invented ever enters the graph.

The candidate review API remains for callers that want a human gate; set `ARC_AUTO_APPROVE` off for
an MCP client and its writes wait for review instead.

- `POST /courses/{course_id}/documents/{document_id}/process`
- `POST /courses/{course_id}/documents/{document_id}/extract` to retry graph building
- `GET|PUT /settings/extraction` to detect and choose the agent CLI
- `GET /courses/{course_id}/documents/{document_id}/chunks`
- `GET /courses/{course_id}/documents/{document_id}/graph` for the records a source produced

## Graph API

Graph persistence is available only through `CourseGraph`; route modules do not query graph
tables. Active graph records can be authored and retrieved with these course-scoped endpoints:

- `POST /courses/{course_id}/graph/nodes`
- `GET|PATCH|DELETE /courses/{course_id}/graph/nodes/{node_id}`
- `GET /courses/{course_id}/graph/nodes/search?q={query}`
- `GET /courses/{course_id}/graph/nodes/{node_id}/neighbors`
- `POST /courses/{course_id}/graph/relationships`
- `GET|PATCH|DELETE /courses/{course_id}/graph/relationships/{relationship_id}`
- `GET /courses/{course_id}/graph` for visualization data

### Candidate review

Automatic extraction approves as it writes. The review API below is what remains for MCP clients
run with `ARC_AUTO_APPROVE` unset, whose records are invisible to graph visualization, counts,
search, and traversal until approved. Review statuses are
`PENDING`, `APPROVED`, `REJECTED`, `EDITED`, and `MERGED`.

- `GET /courses/{course_id}/graph/review/candidates?documentId={document_id}`
- `GET /courses/{course_id}/graph/review/candidates/nodes/{node_id}`
- `GET /courses/{course_id}/graph/review/candidates/relationships/{relationship_id}`
- `POST /courses/{course_id}/graph/review/candidates/nodes/{node_id}/approve|reject|merge`
- `PATCH /courses/{course_id}/graph/review/candidates/nodes/{node_id}`
- `POST /courses/{course_id}/graph/review/candidates/relationships/{id}/approve|reject|merge`
- `PATCH /courses/{course_id}/graph/review/candidates/relationships/{relationship_id}`
- `POST /courses/{course_id}/graph/review/candidates/approve` for bulk approval

Editing a candidate records an `EDITED` status and keeps it in the queue. Rejecting archives the
candidate and any candidate relationship that depends on it, and never changes approved data.
Merging folds a candidate into an approved record, moving evidence, extraction metadata, and
relationships onto it without creating duplicates.

`DELETE` archives a graph record instead of physically deleting it. Archiving a node also
archives its incident relationships. Node and relationship source evidence uses
`sourceDocumentId` and `sourceLocation`; the document must belong to the same course.

## Current limitations

- Local storage is development-only and document processing runs synchronously.
- The initial schema bootstrap uses SQLAlchemy metadata. Changes to existing tables ship as
  idempotent SQL files in `apps/api/migrations`, applied with `python -m app.migrate` (also run by
  `python -m app.seed`). Adopt Alembic before collaborative deployments.
- There is no authentication, authorization, object storage, background work, search, or agent runtime.

## Planned components

1. Background document processing workers and production object storage
2. Knowledge extraction that writes through `CourseGraph`
3. An agent router with tutor, assignment, and reviewer agents that query the shared graph

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the architectural rationale and [AGENTS.md](AGENTS.md) for contributor guidance.

The external extraction tool names and their input/output schemas are documented in
[docs/MCP_TOOLS.md](docs/MCP_TOOLS.md).
