import pytest


@pytest.fixture(autouse=True)
def clean_reports():
    """Overrides the root autouse fixture so planner tests never connect to Postgres."""
    yield
