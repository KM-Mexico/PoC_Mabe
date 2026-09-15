import os
os.environ["DATABASE_URL"] = "sqlite:////tmp/business_case_pytest.db"
os.environ["UPLOAD_DIRECTORY"] = "/tmp/business-case-pytest-uploads"
os.environ["USE_MOCKS"] = "true"
os.environ["AGENT_ENV"] = "test"

import shutil
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app


@pytest.fixture(autouse=True)
def clean_database():
    upload_directory = Path(os.environ["UPLOAD_DIRECTORY"])
    shutil.rmtree(upload_directory, ignore_errors=True)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    shutil.rmtree(upload_directory, ignore_errors=True)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
