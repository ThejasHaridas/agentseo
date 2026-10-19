import os

# Must run before any `app` import creates the settings/engine, so tests never touch the dev database.
os.environ["AGENTRANK_DATABASE_URL"] = "sqlite:///./test_agentrank.db"

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def database():
    from app.db import Base, engine, init_db

    Base.metadata.drop_all(engine)
    init_db()
    yield
