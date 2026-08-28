-- Graph review workflow schema.
--
-- Brings a database created before the review workflow up to the current models: the PENDING,
-- EDITED, and MERGED review statuses, the review bookkeeping columns, and approved-only
-- uniqueness so several candidates may propose the same knowledge until a reviewer decides.
--
-- Every statement is idempotent, so re-running the migration is safe.

-- @autocommit
-- New enum labels must be committed before rows can use them.
ALTER TYPE reviewstatus ADD VALUE IF NOT EXISTS 'PENDING';
ALTER TYPE reviewstatus ADD VALUE IF NOT EXISTS 'EDITED';
ALTER TYPE reviewstatus ADD VALUE IF NOT EXISTS 'MERGED';

-- @transaction
ALTER TABLE graph_nodes ADD COLUMN IF NOT EXISTS review_note text;
ALTER TABLE graph_nodes ADD COLUMN IF NOT EXISTS reviewed_at timestamptz;
ALTER TABLE graph_nodes ADD COLUMN IF NOT EXISTS merged_into_node_id varchar(36);

ALTER TABLE graph_edges ADD COLUMN IF NOT EXISTS review_note text;
ALTER TABLE graph_edges ADD COLUMN IF NOT EXISTS reviewed_at timestamptz;
ALTER TABLE graph_edges ADD COLUMN IF NOT EXISTS merged_into_edge_id varchar(36);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'graph_nodes_merged_into_node_id_fkey') THEN
        ALTER TABLE graph_nodes
            ADD CONSTRAINT graph_nodes_merged_into_node_id_fkey
            FOREIGN KEY (merged_into_node_id) REFERENCES graph_nodes(id) ON DELETE SET NULL;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'graph_edges_merged_into_edge_id_fkey') THEN
        ALTER TABLE graph_edges
            ADD CONSTRAINT graph_edges_merged_into_edge_id_fkey
            FOREIGN KEY (merged_into_edge_id) REFERENCES graph_edges(id) ON DELETE SET NULL;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_graph_node_confidence') THEN
        ALTER TABLE graph_nodes
            ADD CONSTRAINT ck_graph_node_confidence
            CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_graph_edge_confidence') THEN
        ALTER TABLE graph_edges
            ADD CONSTRAINT ck_graph_edge_confidence
            CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1));
    END IF;
END
$$;

UPDATE graph_nodes SET review_status = 'PENDING' WHERE review_status = 'CANDIDATE';
UPDATE graph_edges SET review_status = 'PENDING' WHERE review_status = 'CANDIDATE';

-- Uniqueness now applies to approved records only.
ALTER TABLE graph_nodes DROP CONSTRAINT IF EXISTS uq_course_node_label;
ALTER TABLE graph_edges DROP CONSTRAINT IF EXISTS uq_course_graph_edge;

CREATE UNIQUE INDEX IF NOT EXISTS uq_course_node_label
    ON graph_nodes (course_id, label)
    WHERE review_status = 'APPROVED' AND archived_at IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_course_graph_edge
    ON graph_edges (course_id, source_node_id, target_node_id, type)
    WHERE review_status = 'APPROVED' AND archived_at IS NULL;

CREATE INDEX IF NOT EXISTS ix_graph_nodes_review_status ON graph_nodes (review_status);
CREATE INDEX IF NOT EXISTS ix_graph_edges_review_status ON graph_edges (review_status);
