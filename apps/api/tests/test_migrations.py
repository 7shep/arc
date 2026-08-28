import pytest
from sqlalchemy import inspect, text

from app.database import engine
from app.migrate import MIGRATIONS_DIR, _sections, migrate
from app.models import GraphEdge, GraphNode

postgres_only = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="SQL migrations target PostgreSQL",
)


def test_sections_split_autocommit_and_transaction_blocks() -> None:
    sections = _sections(
        "-- @autocommit\nALTER TYPE t ADD VALUE 'A';\n-- @transaction\nSELECT 1;\n"
    )
    assert [autocommit for autocommit, _ in sections] == [True, False]
    assert sections[0][1] == "ALTER TYPE t ADD VALUE 'A';"
    assert sections[1][1] == "SELECT 1;"


def test_leading_statements_default_to_a_transaction() -> None:
    assert _sections("SELECT 1;\n") == [(False, "SELECT 1;")]


def test_every_migration_file_is_readable_sql() -> None:
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    assert files, "expected at least one migration"
    for path in files:
        assert _sections(path.read_text(encoding="utf-8"))


def test_migrations_refuse_to_run_outside_postgresql() -> None:
    if engine.dialect.name == "postgresql":
        pytest.skip("running against PostgreSQL")
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        migrate(engine)


@postgres_only
def test_migrations_are_idempotent_against_the_current_schema() -> None:
    migrate(engine)
    assert migrate(engine) == []
    columns = {column["name"] for column in inspect(engine).get_columns(GraphNode.__tablename__)}
    assert {"review_note", "reviewed_at", "merged_into_node_id"} <= columns
    edge_columns = {
        column["name"] for column in inspect(engine).get_columns(GraphEdge.__tablename__)
    }
    assert {"review_note", "reviewed_at", "merged_into_edge_id"} <= edge_columns
    with engine.connect() as connection:
        labels = set(
            connection.scalars(
                text(
                    "SELECT enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
                    "WHERE t.typname = 'reviewstatus'"
                )
            ).all()
        )
    assert {"PENDING", "APPROVED", "REJECTED", "EDITED", "MERGED"} <= labels
