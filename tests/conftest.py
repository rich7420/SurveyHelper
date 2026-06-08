"""Test fixtures.

pytest-asyncio gives each test function its own event loop, but the asyncpg pool is
a module singleton that binds to the loop it was created on. Reset the cached pool
around every test so each test builds its pool on its own loop (leaked pools are
cleaned at process exit — fine for tests).
"""

import pytest

import surveyhelper.db as db


@pytest.fixture(autouse=True)
def _fresh_pool():
    db._pool = None
    yield
    db._pool = None
