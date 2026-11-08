"""Document review export retains the original image-aware formatting."""
from kdb.mining.common.schema.document_content import trans_page_content_to_text
from kdb.mining.common.schema.page_export import write_page_content


def output_page_content_trans_result(page_content_file, add_page_num=1, wrtite_file=None):
    return write_page_content(page_content_file, add_page_num, wrtite_file, trans_page_content_to_text)
