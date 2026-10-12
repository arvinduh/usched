"""Tests for the catalog routes over the fixture catalog."""

import pathlib

import fastapi
import pytest
from fastapi import testclient

from server.src.data import catalog_db
from server.src.routes import catalog


def _client(path: pathlib.Path) -> testclient.TestClient:
  app = fastapi.FastAPI()
  app.include_router(catalog.router)
  app.state.catalog = catalog_db.CatalogDb(path)
  return testclient.TestClient(app)


@pytest.fixture(scope="module")
def client(catalog_path) -> testclient.TestClient:
  return _client(catalog_path)


def test_terms(client):
  terms = client.get("/api/terms").json()
  assert terms[0] == {
    "code": 20271,
    "season": "Spring",
    "year": 2027,
    "status": "Active",
    "has_courses": True,
  }


def test_course_search_and_detail(client):
  found = client.get("/api/terms/20271/courses", params={"q": "csci 104"})
  assert found.json()[0]["code"] == "CSCI-104L"
  course = client.get("/api/terms/20271/courses/csci-104l").json()
  assert course["units"] == {"min": 4.0, "max": 4.0}
  assert course["sections"][0]["meetings"][0]["days"]


def test_unknown_items_are_404(client):
  assert client.get("/api/terms/20253/courses/CSCI-104L").status_code == 404
  assert client.get("/api/programs/nope").status_code == 404


def test_query_bounds_are_validated(client):
  response = client.get("/api/terms/20271/courses", params={"limit": 0})
  assert response.status_code == 422


def test_sections_by_comma_separated_ids(client):
  sections = client.get(
    "/api/terms/20271/sections", params={"ids": "29905, 29912,"}
  ).json()
  assert sorted(s["id"] for s in sections) == ["29905", "29912"]


def test_programs_and_policy(client):
  degrees = client.get("/api/programs", params={"kind": "degree"}).json()
  assert [p["id"] for p in degrees] == ["computer-science-bs"]
  assert client.get("/api/programs/computer-science-bs").json()["requirements"]
  assert "CSCI" in client.get("/api/departments").json()
  assert client.get("/api/ge-categories").json()[0]["code"] == "GE-A"
  assert client.get("/api/ap-exams").json()


def test_missing_catalog_is_503_with_the_fix(tmp_path):
  response = _client(tmp_path / "none.db").get("/api/terms")
  assert response.status_code == 503
  assert "npm run catalog" in response.json()["detail"]


def test_ge_audit(client):
  progress = client.post(
    "/api/ge-audit",
    json={
      "completed": ["csci-104l"],
      "ap_credits": [{"exam_id": "AP_CALC_BC", "score": 5}],
    },
  ).json()
  by_code = {p["code"]: p for p in progress}
  assert by_code["GE-A"]["courses"] == ["csci-104l"]
  assert by_code["GE-F"]["exams"] == ["AP_CALC_BC"]


def test_program_audit(client):
  audit = client.post(
    "/api/terms/20271/programs/computer-science-bs/audit",
    json={"completed": ["CSCI-103L"]},
  ).json()
  assert audit["units"] == 4
  assert any(r["courses"] == ["CSCI-103L"] for r in audit["requirements"])
  fresh = client.post(
    "/api/terms/20271/programs/computer-science-bs/audit",
    json={"completed": []},
  ).json()
  assert "CSCI-104L" in fresh["locked"]
