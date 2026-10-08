import re

import pytest
from fastapi.testclient import TestClient

from slim_lab_portal.config import Settings
from slim_lab_portal.db import Base, make_engine, make_session_factory
from slim_lab_portal.main import create_app
from slim_lab_portal.models import ROLE_CUSTOMER, ROLE_STAFF, User
from slim_lab_portal.security import hash_password

PASSWORD = "correct horse battery staple"


def make_settings(database_url: str, **overrides) -> Settings:
    values = dict(
        env="test",
        database_url=database_url,
        secret_key="test-secret",
        session_cookie_secure=False,
        session_max_age_seconds=3600,
        max_body_bytes=1024 * 1024,
    )
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
def engine(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db(engine):
    with make_session_factory(engine)() as session:
        yield session


@pytest.fixture
def app(engine):
    return create_app(make_settings(str(engine.url)), engine=engine)


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


@pytest.fixture
def staff_user(db):
    user = User(email="staff@lab.example", password_hash=hash_password(PASSWORD), role=ROLE_STAFF, initials="JM")
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def customer_user(db):
    user = User(email="jane@acme.example", password_hash=hash_password(PASSWORD), role=ROLE_CUSTOMER, customer_id=1)
    db.add(user)
    db.commit()
    return user


def csrf_from(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, "no csrf_token field in page"
    return match.group(1)


def login(client: TestClient, email: str, password: str = PASSWORD):
    token = csrf_from(client.get("/login").text)
    return client.post(
        "/login",
        data={"email": email, "password": password, "csrf_token": token, "next": "/"},
        follow_redirects=False,
    )
