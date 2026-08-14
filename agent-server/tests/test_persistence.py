import asyncio
from pathlib import Path

from pydantic import ValidationError

from app.config import Settings
from app.db.models import RunRow, SecretVaultRow
from app.db.rls import set_local_tenant_context


def test_prod_requires_postgres_storage() -> None:
    try:
        Settings(app_env="prod", iam_mode="ruoyi", storage_mode="memory")
    except ValidationError as exc:
        assert "AGENT_STORAGE_MODE=postgres" in str(exc)
    else:
        raise AssertionError("production accepted memory storage")


def test_run_model_contains_thread_active_partial_index() -> None:
    indexes = {index.name: index for index in RunRow.__table__.indexes}
    assert "uq_platform_run_active_thread" in indexes
    assert indexes["uq_platform_run_active_thread"].unique is True
    assert [column.name for column in indexes["uq_platform_run_active_thread"].columns] == ["tenant_id", "thread_id"]


def test_rls_context_is_transaction_local() -> None:
    class FakeSession:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict]] = []

        async def execute(self, statement, params) -> None:
            self.calls.append((str(statement), params))

    async def run() -> None:
        session = FakeSession()
        await set_local_tenant_context(session, "tenant-a", "user-a")
        assert len(session.calls) == 2
        assert all("set_config" in statement for statement, _ in session.calls)
        assert session.calls[0][1] == {"tenant_id": "tenant-a"}
        assert session.calls[1][1] == {"user_id": "user-a"}

    asyncio.run(run())


def test_migration_enables_force_rls() -> None:
    migration = Path(__file__).parents[1] / "migrations" / "versions" / "0001_core.py"
    assert "FORCE ROW LEVEL SECURITY" in migration.read_text(encoding="utf-8")
    assert "current_setting('app.tenant_id', true)" in migration.read_text(encoding="utf-8")


def test_secret_vault_schema_never_exposes_plaintext_column() -> None:
    columns = {column.name for column in SecretVaultRow.__table__.columns}
    assert "encrypted_value" in columns
    assert "fingerprint" in columns
    assert not columns.intersection({"value", "plaintext", "api_key", "token", "password"})
    migration = Path(__file__).parents[1] / "migrations" / "versions" / "0016_secret_vault.py"
    source = migration.read_text(encoding="utf-8")
    assert "FORCE ROW LEVEL SECURITY" in source
    assert "current_setting('app.tenant_id', true)" in source
