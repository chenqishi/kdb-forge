from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
import os
import sys

from kdb.mining.generation.builders.knowlege_segment_builder_by_dify import run_batch_get_segment_knowledge

if __name__ == '__main__':
    run_batch_get_segment_knowledge(sys.argv[1], sys.argv[2]) 