"""Shared file output with the caller's original page-formatting policy."""
import json


def write_page_content(page_content_file, add_page_num, wrtite_file, formatter):
    add_page_num = bool(add_page_num)
    page_content_json = json.load(open(page_content_file, 'r', encoding='utf-8'))
    trans_text = formatter(page_content_json, add_page_num)
    if wrtite_file:
        with open(wrtite_file, 'w', encoding='utf-8') as f:
            f.write(trans_text)
    else:
        print(trans_text)
