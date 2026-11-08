"""Equal exporter bodies must retain their different page-formatting policies."""
import json
import pytest

from kdb.mining.common.schema.document_review import output_page_content_trans_result as export_document
from kdb.mining.common.schema.review_formats import output_page_content_trans_result as export_review


@pytest.mark.parametrize('export,tail', [(export_document, '\nhttps://example.invalid/image.png'), (export_review, '')])
def test_page_export_preserves_each_existing_format(export, tail, tmp_path, capsys):
    source = tmp_path / 'pages.json'
    source.write_text(json.dumps({'1': [
        {'type': 'text', 'text_content': 'body'},
        {'type': 'image', 'is_valid': True, 'public_url': 'https://example.invalid/image.png'},
    ]}))
    target = tmp_path / 'result.txt'
    assert export(str(source), wrtite_file=str(target)) is None
    assert target.read_text() == '第1页内容如下:\nbody' + tail
    assert export(str(source), add_page_num=0) is None
    assert capsys.readouterr().out == 'body' + tail + '\n'
