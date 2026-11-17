import ast
import json
from pathlib import Path

from kdb.retrieval.ontology import schema
from kdb.retrieval.ontology.validation import validate_document

ROOT = Path(__file__).resolve().parents[3]


def test_schema_artifact_matches_models():
    assert schema.main(["--check"]) == 0
    artifact = json.loads(schema.schema_text())
    assert artifact["additionalProperties"] is False
    assert artifact["properties"]["schema_version"]["const"] == "1.0"
    assert artifact["$defs"]["Attribute"]["properties"]["data_type"]["enum"] == list(schema.DATA_TYPES)


def test_seeds_are_valid_complete_documents():
    paths = sorted((ROOT / "resources/ontology").glob("*.json"))
    assert len(paths) == 3
    for path in paths:
        vd = validate_document(json.loads(path.read_text()))
        assert vd.document_bytes > 100


def test_new_modules_parse_as_python39():
    paths = list((ROOT / "src/kdb/retrieval/ontology").glob("*.py"))
    paths += list((ROOT / "src/kdb/entrypoints/http/retrieval").glob("ontology*.py"))
    paths.append(ROOT / "src/kdb/entrypoints/cli/tools/ontology_clone.py")
    for path in paths:
        ast.parse(path.read_text(), filename=str(path), feature_version=(3, 9))


def test_ontology_contracts_are_indexed_and_have_required_sections():
    index = json.loads((ROOT / "function_schema/current_index.json").read_text())
    indexed = {contract["schema_file"] for module in index["modules"] for contract in module["contracts"]}
    assert index["contract_count"] == sum(len(module["contracts"]) for module in index["modules"])
    paths = sorted((ROOT / "function_schema").glob("kdb.*ontology*.md"))
    assert len(paths) >= 28
    markdown_index = (ROOT / "function_schema/current_index.md").read_text()
    for path in paths:
        assert str(path.relative_to(ROOT)) in indexed
        text = path.read_text()
        for section in ("Signature", "Inputs", "Outputs", "SQL", "Source"):
            assert "## " + section in text, path
        source = text.split("## Source\n\n`", 1)[1].split("`", 1)[0]
        assert source in markdown_index
