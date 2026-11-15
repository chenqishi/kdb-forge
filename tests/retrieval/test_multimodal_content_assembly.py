"""Keep ingestion content assembly and maintenance normalization explicit."""
from copy import deepcopy

import pytest

from kdb.retrieval.application.search_index_data_interface import SearchDataInterface
from kdb.retrieval.maintenance.prune_dead_urls import (
    join_multimodal_contents as join_maintenance_contents,
)


@pytest.mark.parametrize(
    'parts, expected',
    [
        pytest.param([], '', id='empty'),
        pytest.param(
            [{'type': 'text', 'content': 'first'}, {'type': 'text', 'content': 'second'}],
            'first\nsecond', id='text-order',
        ),
        pytest.param(
            [
                {'type': 'text', 'content': 'answer'},
                {'type': 'image', 'path': 'a/image.png', 'url': 'https://unused.invalid/image'},
                {'type': 'video', 'path': 'a/video.mp4'},
                {'type': 'audio', 'path': 'a/audio.mp3'},
                {'type': 'file', 'path': 'a/report.pdf', 'fileName': 'original.pdf'},
            ],
            'answer\n[multimodal_prefix]a/image.png\n[multimodal_prefix]a/video.mp4'
            '\n[multimodal_prefix]a/audio.mp3\n[multimodal_prefix]a/report.pdf',
            id='media-order-and-path-priority',
        ),
        pytest.param(
            [{'type': 'file', 'path': '', 'url': 'https://example.invalid/report.pdf?x=1'}],
            'https://example.invalid/report.pdf?x=1', id='external-url-fallback',
        ),
        pytest.param(
            [{'type': 'image'}, {'type': 'audio', 'path': None, 'url': ''},
             {'type': 'text', 'content': 'answer'}],
            'answer', id='skip-missing-addresses',
        ),
        pytest.param(
            [{'type': 'unknown', 'content': 'ignored', 'path': 'ignored'},
             {'type': 'text', 'content': 'answer'}],
            'answer', id='skip-unknown-type',
        ),
    ],
)
def test_join_multimodal_contents_preserves_order_and_addresses(parts, expected):
    interface = SearchDataInterface.__new__(SearchDataInterface)
    original = deepcopy(parts)

    assert interface.join_multimodal_contents(parts) == expected
    assert parts == original


@pytest.mark.parametrize('part', [
    pytest.param({'type': 'text', 'content': None}, id='null-text'),
    pytest.param({'type': 'text'}, id='missing-text'),
])
def test_join_multimodal_empty_text_retains_distinct_maintenance_behavior(part):
    interface = SearchDataInterface.__new__(SearchDataInterface)

    assert interface.join_multimodal_contents([part]) is None
    assert join_maintenance_contents([part]) == ''
