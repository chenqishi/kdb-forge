from kdb.operations.data_migration.sql import get_all_tables
from kdb.operations.data_migration.sql import get_table_create_sql
from kdb.operations.data_migration.sql import get_table_row_count
from kdb.operations.data_migration.sql import load_table_config
from kdb.operations.data_migration.sql import migrate_table_data
from kdb.operations.data_migration.sql import migrate_table_schema
from kdb.operations.data_migration.sql import print_migration_summary
from kdb.operations.data_migration.sql import process_table
from kdb.operations.data_migration.sql import sql_database_transfer
from kdb.retrieval.maintenance.transfer import _transfer_single_index
from kdb.retrieval.maintenance.transfer import batch_transfer_es_data
from kdb.retrieval.maintenance.transfer import filter_embedding_fields
from kdb.retrieval.maintenance.transfer import get_all_indices
from kdb.retrieval.maintenance.transfer import print_batch_migration_summary
from kdb.retrieval.maintenance.transfer import print_es_migration_summary
from kdb.retrieval.maintenance.transfer import transfer_es_data
import logging

if __name__ == "__main__":
    import logging
    import sys
    import fire

    # 配置日志
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format='[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '
               '[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s'
    )
    fire.Fire({'sql_database_transfer': sql_database_transfer, 'load_table_config': load_table_config, 'get_all_tables': get_all_tables, 'get_table_row_count': get_table_row_count, 'get_table_create_sql': get_table_create_sql, 'process_table': process_table, 'migrate_table_schema': migrate_table_schema, 'migrate_table_data': migrate_table_data, 'print_migration_summary': print_migration_summary, 'transfer_es_data': transfer_es_data, 'filter_embedding_fields': filter_embedding_fields, 'print_es_migration_summary': print_es_migration_summary, 'get_all_indices': get_all_indices, 'batch_transfer_es_data': batch_transfer_es_data, '_transfer_single_index': _transfer_single_index, 'print_batch_migration_summary': print_batch_migration_summary})
