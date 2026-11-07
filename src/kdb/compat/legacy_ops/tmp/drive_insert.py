import logging, sys
logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
sys.path.insert(0, '/root/knowledge_database_builder')
from knowledge_interface_tools.search_index_data_interface import insert_data_to_search_index
ok = insert_data_to_search_index(
    data_file='/root/knowledge_database_builder/tmp/smoke_test.jsonl',
    config_path='/root/knowledge_database_builder/config/config_for_search_index.json',
    use_platform_index=True,
    index_name_assign='payoneer_olive_smoke_test',
    is_update_data=True,
)
print('DONE ok=', ok)
