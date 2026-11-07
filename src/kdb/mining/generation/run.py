from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('run.py')
import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__legacy_source_file__)))

from knowledge_generate.knowlege_segment_builder_by_dify import run_batch_get_segment_knowledge

if __name__ == '__main__':
    run_batch_get_segment_knowledge(sys.argv[1], sys.argv[2]) 