import json

import pytest

import kdb.mining.web.crawlers.batch as web_batch_crawler


def test_firecrawl_only_crawls_without_browser(tmp_path, monkeypatch):
    monkeypatch.setattr(
        web_batch_crawler,
        "fetch_firecrawl_content",
        lambda *args, **kwargs: "# Seller article\n\nUseful body",
    )

    crawler = web_batch_crawler.WebBatchCrawler(
        str(tmp_path), browser_enabled=False
    )
    monkeypatch.setattr(
        crawler,
        "fetch_html_without_browser",
        lambda url: "<html><body>shell</body></html>",
    )

    results = crawler.process_crawl_url(
        "https://vendedores.mercadolibre.com.ar/aprender/nota/example",
        "mercado_local",
        "normal",
        1,
        [],
        use_firecrawl=True,
        firecrawl_only=True,
    )

    assert crawler.driver is None
    assert len(results) == 1
    result = results[0]
    assert tmp_path.joinpath(result["html_local_file"]).exists()
    assert "Useful body" in tmp_path.joinpath(
        result["firecrawl_content_file"]
    ).read_text(encoding="utf-8")


def test_run_task_firecrawl_only_validates_depth_and_writes_manifest(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        web_batch_crawler.WebBatchCrawler,
        "setup_driver",
        lambda self: pytest.fail("firecrawl_only must not start Selenium"),
    )
    monkeypatch.setattr(
        web_batch_crawler,
        "fetch_firecrawl_content",
        lambda *args, **kwargs: "complete body",
    )
    monkeypatch.setattr(
        web_batch_crawler.WebBatchCrawler,
        "fetch_html_without_browser",
        lambda self, url: "<html><body>shell</body></html>",
    )
    output_file = tmp_path / "crawl.jsonl"
    task_info = {
        "client": "mercado_local",
        "index_name": "mercado_local",
        "is_use_firecrawl": True,
        "firecrawl_only": True,
        "url_infos": [
            {
                "url": "https://www.mercadolibre.com.ar/ayuda/33969",
                "content_type": "normal",
                "crawler_degree": 1,
                "keywords": "",
                "limit_page_num": 1,
                "category_id": "2092449414120050690",
                "category_name": "业务地区-阿根廷",
            }
        ],
    }

    web_batch_crawler.run_crawl_task_info(
        "ar-pilot", task_info, str(output_file)
    )
    row = json.loads(output_file.read_text(encoding="utf-8"))
    assert row["task_id"] == "ar-pilot"
    assert row["category_name"] == "业务地区-阿根廷"

    task_info["url_infos"][0]["crawler_degree"] = 2
    with pytest.raises(ValueError, match="depth-1"):
        web_batch_crawler.run_crawl_task_info(
            "ar-invalid", task_info, str(tmp_path / "invalid.jsonl")
        )
