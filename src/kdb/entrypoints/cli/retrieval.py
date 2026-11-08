from kdb.entrypoints.cli.diagnostics.retrieval_examples import test_insert
from kdb.entrypoints.cli.diagnostics.retrieval_examples import test_insert_letian_excel
from kdb.entrypoints.cli.diagnostics.retrieval_examples import test_search_by_query
from kdb.entrypoints.cli.index_upload import insert_data_to_search_index
from kdb.retrieval.application.search_index_data_interface import SearchDataInterface
from kdb.retrieval.engines.protocol import SearchEngine
from kdb.retrieval.ingestion.identifiers import gen_data_id
from kdb.retrieval.maintenance.audit_export import gen_audit_data
from kdb.retrieval.maintenance.audit_export import search_for_audit_data
import logging

if __name__ == "__main__":
    import logging
    import sys
    import fire

    # 配置日志
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.DEBUG,
        format='[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '
               '[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s'
    )

    fire.Fire({'gen_data_id': gen_data_id, 'SearchEngine': SearchEngine, 'SearchDataInterface': SearchDataInterface, 'test_insert_letian_excel': test_insert_letian_excel, 'insert_data_to_search_index': insert_data_to_search_index, 'test_search_by_query': test_search_by_query, 'test_insert': test_insert, 'gen_audit_data': gen_audit_data, 'search_for_audit_data': search_for_audit_data})
