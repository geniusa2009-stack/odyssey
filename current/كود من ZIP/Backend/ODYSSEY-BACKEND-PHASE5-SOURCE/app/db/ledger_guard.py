"""Database-level append-only guard for the decision ledger (``mission_decisions``).

Defence in depth: the ORM already refuses UPDATE/DELETE of ledger rows; these triggers make the
database itself refuse them, so raw SQL or another client cannot rewrite history either.

* UPDATE is always rejected.
* DELETE is rejected unless the transaction has explicitly opted in (PostgreSQL only) with
  ``SET LOCAL odyssey.allow_ledger_delete = 'on'``. This exists solely for deliberate
  data-retention / erasure procedures (see docs/DATABASE.md); application code never sets it.
* SQLite (local development only) rejects both, with no override.

The Alembic migration ``0001`` contains a frozen copy of this SQL; keep them in sync.
"""

from __future__ import annotations

from sqlalchemy import DDL, Table, event

POSTGRES_FUNCTION = """
CREATE OR REPLACE FUNCTION odyssey_ledger_append_only() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE'
       AND coalesce(current_setting('odyssey.allow_ledger_delete', true), '') = 'on' THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'mission_decisions is append-only (% rejected)', TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql
"""

POSTGRES_TRIGGER = """
CREATE TRIGGER trg_mission_decisions_append_only
BEFORE UPDATE OR DELETE ON mission_decisions
FOR EACH ROW EXECUTE FUNCTION odyssey_ledger_append_only()
"""

SQLITE_TRIGGERS = (
    """
    CREATE TRIGGER trg_mission_decisions_no_update BEFORE UPDATE ON mission_decisions
    BEGIN SELECT RAISE(ABORT, 'mission_decisions is append-only (UPDATE rejected)'); END
    """,
    """
    CREATE TRIGGER trg_mission_decisions_no_delete BEFORE DELETE ON mission_decisions
    BEGIN SELECT RAISE(ABORT, 'mission_decisions is append-only (DELETE rejected)'); END
    """,
)


def _ddl(statement: str, dialect: str) -> DDL:
    return DDL(statement).execute_if(dialect=dialect)  # type: ignore[no-untyped-call]


def install(table: Table) -> None:
    """Attach the triggers to ``table`` for ``metadata.create_all`` (dev/test schemas)."""
    event.listen(table, "after_create", _ddl(POSTGRES_FUNCTION, "postgresql"))
    event.listen(table, "after_create", _ddl(POSTGRES_TRIGGER, "postgresql"))
    for statement in SQLITE_TRIGGERS:
        event.listen(table, "after_create", _ddl(statement, "sqlite"))
