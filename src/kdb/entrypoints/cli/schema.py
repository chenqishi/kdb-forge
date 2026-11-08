from kdb.mining.common.schema.excel_import import classify_excel_upload
from kdb.mining.common.schema.excel_import import excel_to_qa_json
from kdb.mining.common.schema.qa_records import batch_trans_qa_to_search_data
from kdb.mining.common.schema.qa_records import trans_qa_to_search_data_one_file
from kdb.mining.common.schema.review_formats import batch_json_to_excel
from kdb.mining.common.schema.review_formats import batch_select_high_quality_qa_and_white_answer_to_json
from kdb.mining.common.schema.review_formats import batch_select_high_quality_qa_to_json
from kdb.mining.common.schema.review_formats import batch_split_json_quality_to_excel
from kdb.mining.common.schema.document_review import output_page_content_trans_result
from kdb.mining.common.schema.review_formats import output_qa_json_trans_result
from kdb.mining.common.schema.review_import import trans_review_excel_to_json_file
from kdb.mining.common.schema.review_import import trans_web_excel_to_json_file
from kdb.mining.common.schema.segment_records import trans_html_segment_to_search_data_for_file
from kdb.mining.common.schema.segment_records import trans_segment_to_search_data_for_file
from kdb.retrieval.maintenance.excel_export import trans_es_data_to_excel
from kdb.retrieval.maintenance.excel_export import trans_es_modify_data_to_excel
import logging
import sys

if __name__ == '__main__':
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')  
    import fire
    fire.Fire({
        'batch_json_to_excel': batch_json_to_excel,
        'output_qa_json_trans_result': output_qa_json_trans_result,
        'output_page_content_trans_result': output_page_content_trans_result,
        'batch_split_json_quality_to_excel': batch_split_json_quality_to_excel,
        'batch_trans_qa_to_search_data': batch_trans_qa_to_search_data,
        'batch_select_high_quality_qa_to_json': batch_select_high_quality_qa_to_json,
        'excel_to_qa_json': excel_to_qa_json,
        'batch_select_high_quality_qa_and_white_answer_to_json': batch_select_high_quality_qa_and_white_answer_to_json,
        'trans_segment_to_search_data_for_file': trans_segment_to_search_data_for_file,
        'trans_html_segment_to_search_data_for_file': trans_html_segment_to_search_data_for_file,
        'trans_review_excel_to_json_file': trans_review_excel_to_json_file,
        'trans_web_excel_to_json_file': trans_web_excel_to_json_file,
        'classify_excel_upload': classify_excel_upload,
        'trans_es_data_to_excel': trans_es_data_to_excel,
        'trans_qa_to_search_data_one_file': trans_qa_to_search_data_one_file,
        'trans_es_modify_data_to_excel': trans_es_modify_data_to_excel,
    })
