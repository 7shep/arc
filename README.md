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
- Explore course metrics, recent uploads, sources, and an interactive graph
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
| `NEXT_PUBLIC_API_URL` | API URL used by the frontend | `http://localhost:8000` |

Run checks from the repository root:

```bash
pnpm lint
pnpm typecheck
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

`DELETE` archives a graph record instead of physically deleting it. Archiving a node also
archives its incident relationships. Node and relationship source evidence uses
`sourceDocumentId` and `sourceLocation`; the document must belong to the same course.

## Current limitations

- Local storage is development-only and document processing runs synchronously.
- The initial schema bootstrap uses SQLAlchemy metadata; add Alembic before collaborative deployments.
- There is no authentication, authorization, object storage, background work, search, or agent runtime.

## Planned components

1. Background document processing workers and production object storage
2. Knowledge extraction that writes through `CourseGraph`
3. An agent router with tutor, assignment, and reviewer agents that query the shared graph

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the architectural rationale and [AGENTS.md](AGENTS.md) for contributor guidance.

The external extraction tool names and their input/output schemas are documented in
[docs/MCP_TOOLS.md](docs/MCP_TOOLS.md).
