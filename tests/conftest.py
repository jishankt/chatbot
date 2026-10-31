import pytest
from app.api.routes import clear_db_auth_failures


@pytest.fixture(autouse=True)
def clean_localhost_lockout():
    yield
    clear_db_auth_failures("127.0.0.1")
