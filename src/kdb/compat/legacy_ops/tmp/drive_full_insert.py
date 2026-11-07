import json, sys, os, time, logging
sys.path.insert(0, '/root/knowledge_database_builder')
logging.basicConfig(level=logging.WARNING, format='%(levelname)s:%(name)s:%(message)s')
from knowledge_interface_tools.search_index_data_interface import SearchDataInterface

DATA_FILE = '/root/knowledge_database_builder/tmp/群聊总结知识_合并版_20260905.jsonl'
CONFIG = '/root/knowledge_database_builder/config/config_for_search_index.json'
INDEX = 'payoneer_olive'

si = SearchDataInterface(config_path=CONFIG, index_name='mix')

def main():
    total = 0; ok = 0; fail = 0; skipped_internal_dup = 0
    fail_samples = []
    seen = set()
    start_all = time.time()
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except Exception as e:
                fail += 1
                fail_samples.append(('parse', str(e)[:120]))
                continue
            # internal exact dedup within the batch
            key = (data.get('title',''), data.get('content',''))
            if key in seen:
                skipped_internal_dup += 1
                continue
            seen.add(key)
            total += 1
            try:
                success, message = si.insert_data(data, index_name=INDEX, is_update_data=True, check_duplicate=False)
                if success:
                    ok += 1
                else:
                    fail += 1
                    fail_samples.append((data.get('title', '')[:30], str(message)[:120]))
            except Exception as e:
                fail += 1
                fail_samples.append((data.get('title', '')[:30], 'EXC ' + str(e)[:150]))
            if total % 100 == 0:
                print('PROGRESS total=%d ok=%d fail=%d dup=%d elapsed=%.1fs' % (total, ok, fail, skipped_internal_dup, time.time()-start_all), flush=True)
    print('==== INSERT SUMMARY ====', flush=True)
    print('total_processed:', total, flush=True)
    print('inserted_ok:', ok, flush=True)
    print('failed_total:', fail, flush=True)
    print('skipped_internal_duplicate:', skipped_internal_dup, flush=True)
    print('fail_samples:', json.dumps(fail_samples[:20], ensure_ascii=False), flush=True)
    print('elapsed_total: %.1fs' % (time.time()-start_all), flush=True)
    print('==== END ====', flush=True)

if __name__ == '__main__':
    main()
