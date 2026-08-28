"""Apply the SQL migrations in `apps/api/migrations` to the configured database.

The initial schema is still bootstrapped from SQLAlchemy metadata, so this runner exists to bring
databases created by an earlier bootstrap up to the current models. Each file is applied once and
recorded in `schema_migrations`; every file is written to be idempotent so a partially applied
migration can simply be run again.

A file may be split into sections with `-- @autocommit` and `-- @transaction` marker lines.
Autocommit sections exist for statements PostgreSQL refuses to run inside a transaction that also
uses their result, such as `ALTER TYPE ... ADD VALUE`. Sections default to running in a
transaction.

Usage: python -m app.migrate
"""

from pathlib import Path

from sqlalchemy import Engine, text

from app.database import engine

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
AUTOCOMMIT_MARKER = "-- @autocommit"
TRANSACTION_MARKER = "-- @transaction"


def _sections(sql: str) -> list[tuple[bool, str]]:
    """Split a migration into (autocommit, sql) sections in file order."""
    sections: list[tuple[bool, str]] = []
    autocommit = False
    buffer: list[str] = []

    def flush() -> None:
        body = "\n".join(buffer).strip()
        if body:
            sections.append((autocommit, body))
        buffer.clear()

    for line in sql.splitlines():
        marker = line.strip()
        if marker in (AUTOCOMMIT_MARKER, TRANSACTION_MARKER):
            flush()
            autocommit = marker == AUTOCOMMIT_MARKER
            continue
        buffer.append(line)
    flush()
    return sections


def _applied(engine: Engine) -> set[str]:
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "name VARCHAR(255) PRIMARY KEY, applied_at TIMESTAMP NOT NULL DEFAULT "
                "CURRENT_TIMESTAMP)"
            )
        )
        return set(connection.scalars(text("SELECT name FROM schema_migrations")).all())


def migrate(engine: Engine = engine, migrations_dir: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply every unapplied migration in order and return the names that ran."""
    if engine.dialect.name != "postgresql":
        raise RuntimeError(
            "SQL migrations target PostgreSQL; other databases bootstrap from model metadata"
        )
    applied = _applied(engine)
    ran: list[str] = []
    for path in sorted(migrations_dir.glob("*.sql")):
        if path.name in applied:
            continue
        for autocommit, body in _sections(path.read_text(encoding="utf-8")):
            if autocommit:
                with engine.connect().execution_options(
                    isolation_level="AUTOCOMMIT"
                ) as connection:
                    for statement in filter(None, (part.strip() for part in body.split(";"))):
                        connection.execute(text(statement))
            else:
                with engine.begin() as connection:
                    connection.execute(text(body))
        with engine.begin() as connection:
            connection.execute(
                text("INSERT INTO schema_migrations (name) VALUES (:name)"), {"name": path.name}
            )
        ran.append(path.name)
    return ran


def main() -> None:
    ran = migrate()
    print(f"Applied {len(ran)} migration(s): {', '.join(ran)}" if ran else "Database is current.")


if __name__ == "__main__":
    main()
