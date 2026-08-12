import os
import shutil
from pathlib import Path

# Must be set before app.config / app.main are imported anywhere, since
# app.config raises at import time if MASTER_KEY is missing. conftest.py is
# imported by pytest before test modules, so this runs first.
os.environ.setdefault("MASTER_KEY", "mIN27fAPCnrASKIwM8I6Mac9LqKm3g0jYyt6xxW9Zyk=")
os.environ.setdefault("JWT_SECRET", "ci-test-secret")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_ci.db")
os.environ.setdefault("STORAGE_DIR", "./test_ci_storage")

import pytest


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_artifacts():
    yield
    for path in ["test_ci.db", "test_ci_storage"]:
        p = Path(path)
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        elif p.exists():
            p.unlink()
