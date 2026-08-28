-- Automatic graph extraction.
--
-- Adds per-document extraction state and the single workspace settings row that records which
-- agent CLI Arc should spawn. Idempotent, so re-running is safe.

-- @transaction
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'extractionstatus') THEN
        CREATE TYPE extractionstatus AS ENUM (
            'NOT_STARTED', 'RUNNING', 'COMPLETED', 'FAILED', 'UNAVAILABLE'
        );
    END IF;
END
$$;

ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS extraction_status extractionstatus NOT NULL DEFAULT 'NOT_STARTED';
ALTER TABLE documents ADD COLUMN IF NOT EXISTS extraction_error text;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS extracted_at timestamptz;

CREATE INDEX IF NOT EXISTS ix_documents_extraction_status ON documents (extraction_status);

CREATE TABLE IF NOT EXISTS workspace_settings (
    id varchar(36) PRIMARY KEY,
    extraction_enabled boolean NOT NULL DEFAULT true,
    extraction_tool_id varchar(64),
    extraction_command text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
