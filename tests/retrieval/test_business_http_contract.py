"""Lock the public business API independently of its internal module layout."""
import copy
import json
from pathlib import Path
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from kdb.services.retrieval import app as service


CONTRACT_PATH = Path(__file__).resolve().parents[1] / "fixtures/business_retrieval_contract.json"
assert CONTRACT_PATH.stat().st_size < 1024 * 1024
CONTRACT = json.loads(CONTRACT_PATH.read_text())


def test_openapi_matches_business_contract():
    assert service.app.openapi() == CONTRACT["openapi"]


@pytest.mark.parametrize(
    "case", CONTRACT["models"],
    ids=[f"{index}:{case['model']}" for index, case in enumerate(CONTRACT["models"])],
)
def test_request_models_match_business_contract(case):
    model = getattr(service, case["model"])
    expected = case["expected"]
    if expected["valid"]:
        result = model.model_validate(copy.deepcopy(case["input"]))
        assert result.model_dump(mode="json", by_alias=True) == expected["payload"]
    else:
        with pytest.raises(ValidationError) as caught:
            model.model_validate(copy.deepcopy(case["input"]))
        errors = [{"loc": list(item["loc"]), "type": item["type"]}
                  for item in caught.value.errors()]
        assert errors == expected["errors"]


def test_search_preserves_business_wire_format(monkeypatch):
    case = CONTRACT["search_wire"]
    search = AsyncMock(return_value=(copy.deepcopy(case["backend_results"]), 1))
    monkeypatch.setattr(service, "query_remote_service", search)
    response = TestClient(service.app).post("/search", json=case["request"])
    assert response.status_code == 200
    assert response.json() == case["response"]
    search.assert_awaited_once_with(
        text="unit query", index_names="test_index", condition_dicts=None,
        size=100, search_type="qa", data_type="text", use_synonyms=False,
    )
