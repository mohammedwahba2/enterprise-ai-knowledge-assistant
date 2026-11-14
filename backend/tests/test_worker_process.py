"""The worker is a separate process: it must work with only the modules it imports itself."""

import subprocess
import sys
import textwrap


def test_worker_process_resolves_every_foreign_key_without_the_web_app() -> None:
    """Regression: the worker once failed on every document with `NoReferencedTableError`
    (documents.uploaded_by -> users) because it never imported the identity models. In-process tests
    always load the whole app, so this must run in a fresh interpreter."""
    code = textwrap.dedent(
        """
        import app.worker.tasks  # noqa: F401  (what the worker imports; nothing from the web app)
        from sqlalchemy.orm import configure_mappers
        from app.db.base import Base

        configure_mappers()
        assert {"users", "organizations", "documents", "chunks"} <= set(Base.metadata.tables)
        for table in Base.metadata.sorted_tables:  # resolves every foreign key
            for fk in table.foreign_keys:
                fk.column  # noqa: B018
        """
    )
    result = subprocess.run(  # noqa: S603  (fixed argv)
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=60, check=False
    )
    assert result.returncode == 0, result.stderr[-800:]
