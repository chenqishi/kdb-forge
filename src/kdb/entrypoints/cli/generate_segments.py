from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
import os
import sys

from kdb.mining.common.generation.segments import run_batch_get_segment_knowledge

if __name__ == '__main__':
    run_batch_get_segment_knowledge(sys.argv[1], sys.argv[2]) 