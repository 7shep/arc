# Arc graph extraction MCP tools

Arc exposes a stdio MCP server for external extraction assistants. Start it from the API virtual
environment with `arc-mcp` or `python -m app.mcp.server`. The server does not call an AI provider.
It accepts only evidence-backed graph candidates, stores them as `PENDING`, and provides no tool
that approves them.

All identifiers use UUID strings. Enum values are the uppercase values below. Unknown IDs and
objects belonging to another course are tool errors.

## Shared schemas

```json
{
  "SourceLocation": {
    "page": "integer >= 1, optional",
    "section": "non-empty string <= 500 chars, optional",
    "start_offset": "integer >= 0, optional",
    "end_offset": "integer >= 1, optional"
  },
  "rules": [
    "At least one location field is required.",
    "start_offset and end_offset must be supplied together.",
    "end_offset must be greater than start_offset."
  ],
  "GraphNodeType": [
    "CONCEPT", "LECTURE", "DOCUMENT", "EXAMPLE", "FORMULA", "ASSIGNMENT", "QUESTION"
  ],
  "GraphEdgeType": [
    "REQUIRES", "RELATED_TO", "TAUGHT_IN", "DEFINED_IN", "USED_IN", "EXAMPLE_OF",
    "APPEARS_IN"
  ],
  "confidence": "number from 0 through 1 inclusive"
}
```

An `Evidence` output has this shape:

```json
{
  "id": "uuid",
  "target_type": "node | relationship",
  "target_id": "uuid",
  "document_id": "uuid",
  "source_location": "SourceLocation",
  "excerpt": "string",
  "confidence": 0.82
}
```

## Tools

### `list_course_documents`

Input: `{ "course_id": "uuid", "include_processed": false }`. `include_processed` is optional and
defaults to `false`, so uploaded, processing, and failed documents are returned. Output:
`{ "documents": Document[] }`, where each document contains `id`, `course_id`,
`original_filename`, `document_type`, `mime_type`, `processing_status`, `processing_error`,
`created_at`, and `updated_at`.

### `get_document_metadata`

Input: `{ "course_id": "uuid", "document_id": "uuid" }`. Output: one `Document` object with the
fields listed above. The course and document must match.

### `get_document_chunks`

Input: `{ "course_id": "uuid", "document_id": "uuid", "offset": 0, "limit": 50 }`. `offset` is
optional and non-negative; `limit` is optional and must be 1–100. Output:

```json
{
  "chunks": [{
    "id": "uuid",
    "document_id": "uuid",
    "sequence": 0,
    "content": "source text",
    "source_location": {
      "source": "original filename",
      "start_offset": 0,
      "end_offset": 2000
    }
  }]
}
```

Existing extracted chunks are returned for every format. If no chunks exist, UTF-8 `.txt` and
`.md` files are split deterministically; binary formats require an ingestion service to have
created chunks first.

### `create_candidate_node`

Input fields: `course_id` (uuid), `node_type` (`GraphNodeType`), `label` (1–255 characters),
`document_id` (uuid), `source_location` (`SourceLocation`), `excerpt` (1–4000 characters),
`confidence` (0–1), plus optional `description` (up to 10000 characters) and `metadata` (object).
Output:

```json
{
  "id": "uuid",
  "course_id": "uuid",
  "node_type": "CONCEPT",
  "label": "Trees",
  "description": null,
  "review_status": "PENDING",
  "confidence": 0.82,
  "evidence": "Evidence"
}
```

### `create_candidate_relationship`

Input fields: `course_id`, `source_node_id`, `target_node_id`, and `document_id` (UUIDs),
`relationship_type` (`GraphEdgeType`), `source_location` (`SourceLocation`), `excerpt` (1–4000
characters), `confidence` (0–1), and optional `metadata` (object). Both nodes and the evidence
document must belong to the course; self-relationships are rejected. Output:

```json
{
  "id": "uuid",
  "course_id": "uuid",
  "source_node_id": "uuid",
  "target_node_id": "uuid",
  "relationship_type": "REQUIRES",
  "review_status": "PENDING",
  "confidence": 0.82,
  "evidence": "Evidence"
}
```

### `attach_source_evidence`

Input fields: `course_id`, `target_id`, and `document_id` (UUIDs), `target_type` (`node` or
`relationship`), `source_location` (`SourceLocation`), `excerpt` (1–4000 characters), and
`confidence` (0–1). Evidence can be attached only to a candidate in the same course. Output:
`Evidence`.

### `mark_document_processed`

Input: `{ "course_id": "uuid", "document_id": "uuid" }`. Output:
`{ "document_id": "uuid", "processing_status": "PROCESSED", "processing_error": null }`.

### `report_document_processing_failure`

Input: `{ "course_id": "uuid", "document_id": "uuid", "reason": "1–2000 chars" }`. Output:
`{ "document_id": "uuid", "processing_status": "FAILED", "processing_error": "reason" }`.

## Review and provenance guarantees

Candidate creation and its first evidence record are committed in one transaction. Every candidate
therefore has a course-scoped source document, validated location, excerpt, and confidence. Extra
evidence is stored as a separate provenance record. The MCP surface cannot set `APPROVED` or
`REJECTED`, and cannot attach evidence to an already reviewed record.
