# Arc contributor guide

## Mission and scope

Arc is a course knowledge system. The current repository is the foundation: courses, source uploads, graph records, and a workspace UI. Do not add LLM providers, embeddings, autonomous agents, authentication, billing, mastery tracking, or a dedicated graph database unless a task explicitly expands scope.

## Architecture boundaries

- `apps/web`: Next.js UI. Keep API access in `src/lib/api.ts` and interactive browser behavior in focused client components.
- `apps/api`: FastAPI application. Route modules validate HTTP input and delegate persistence or domain work.
- `apps/api/app/courses`: course HTTP and persistence concerns.
- `apps/api/app/documents`: document metadata and upload orchestration.
- `apps/api/app/storage`: storage provider contract and local implementation. Never write uploads directly from a route.
- `apps/api/app/graph`: graph domain types, interface, SQL-backed implementation, and routes. Call the graph abstraction instead of coupling callers to SQL tables.
- `apps/api/app/review`: candidate review workflow. Promote candidates through `CourseGraph`; never query graph tables here.
- `apps/api/app/ingestion` and `apps/api/app/agents`: reserved boundaries. Do not add fake implementations.
- `packages/shared`: dependency-free shared TypeScript contracts.

## Working rules

- Preserve the API prefix and endpoint shapes documented in `README.md`.
- Use UTC-aware timestamps at application boundaries.
- Validate uploaded extension, MIME type, filename, and configured size limit.
- Store only generated filenames and relative storage paths; never trust a client path.
- Keep migrations/schema changes reflected in models, seed data, tests, and docs.
- A change to an existing table needs an idempotent SQL file in `apps/api/migrations`; tests
  bootstrap SQLite from metadata and will not catch a missing migration.
- Keep UI copy direct and functional. Use the existing neutral palette and emerald accent; avoid decorative gradients, glass effects, and nested cards.
- Include loading, empty, and error behavior for new user-visible data flows.
- Do not commit `.env`, uploaded course files, database volumes, caches, or build artifacts.

## Verification

From the repository root:

```bash
pnpm install
pnpm lint
pnpm typecheck
pnpm test
pnpm build

cd apps/api
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check .
```

For API changes, add or update tests under `apps/api/tests`. For component changes, add or update Vitest tests beside the component. For UI changes, verify the empty, loading, failure, and populated states at mobile and desktop widths.

