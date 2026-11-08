"""Read-only local prerequisites, then exec the canonical service module."""
import importlib
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINTS = {'retrieval': 'kdb.entrypoints.http.retrieval.app', 'off_task': 'kdb.entrypoints.http.tasks.app', 'crawler': 'kdb.entrypoints.http.crawler.app', 'files': 'kdb.entrypoints.http.files.app', 'multilingual': 'kdb.entrypoints.http.multilingual.app', 'fastgpt_proxy': 'kdb.entrypoints.http.fastgpt_proxy.app'}
DEPENDENCIES = {
    'retrieval': ['fastapi', 'pydantic', 'uvicorn', 'httpx', 'requests', 'numpy', 'jieba', 'elasticsearch'],
    'off_task': ['flask', 'mysql.connector', 'psutil', 'fitz', 'boto3', 'botocore', 'docx', 'docx2pdf', 'PyPDF2', 'PIL', 'requests'],
    'crawler': ['flask', 'pydantic', 'requests', 'bs4', 'tkinter'],
    'files': ['flask', 'requests', 'boto3', 'botocore'],
    'multilingual': ['flask', 'fasttext'],
    'fastgpt_proxy': ['fastapi', 'pydantic', 'uvicorn', 'httpx'],
}


def option(argv, name, default=None):
    for index, value in enumerate(argv):
        if value == name:
            return argv[index + 1] if index + 1 < len(argv) else None
        if value.startswith(name + '='):
            return value.split('=', 1)[1]
    return default


def probe_module(name):
    try:
        spec = importlib.util.find_spec(name)
        result = {'module': name, 'available': spec is not None,
                  'load_path': getattr(spec, 'origin', None)}
        if spec is not None and name == 'elasticsearch':
            sdk = importlib.import_module(name)
            result['load_path'] = getattr(sdk, '__file__', None)
            version = getattr(sdk, '__version__', None)
            result['version'] = list(version) if isinstance(version, tuple) else str(version)
        return result
    except Exception as exc:
        return {'module': name, 'available': False, 'error_type': type(exc).__name__}


def read_config(path, role, report, required=()):
    if not path:
        report['errors'].append('missing_path:' + role)
        return {}
    file_path = Path(path).expanduser()
    if not file_path.is_absolute():
        file_path = Path.cwd() / file_path
    record = {'role': role, 'path': str(file_path), 'exists': file_path.is_file()}
    report['resources'].append(record)
    if not record['exists']:
        report['errors'].append('missing_file:' + role)
        return {}
    try:
        record['size_bytes'] = file_path.stat().st_size
        if record['size_bytes'] > 2 * 1024 * 1024:
            raise ValueError('config too large')
        with file_path.open(encoding='utf-8') as stream:
            config = json.load(stream)
        if not isinstance(config, dict):
            raise ValueError('config must be an object')
    except Exception as exc:
        record['error_type'] = type(exc).__name__
        report['errors'].append('invalid_json:' + role)
        return {}
    missing = [field for field in required if not config.get(field)]
    if missing:
        report['errors'].append('missing_fields:' + role + ':' + ','.join(missing))
    return config


def check(service, argv):
    report = {'service': service, 'interpreter': sys.executable,
              'python_version': sys.version.split()[0], 'sys_prefix': sys.prefix,
              'sys_base_prefix': getattr(sys, 'base_prefix', sys.prefix),
              'interpreter_realpath': str(Path(sys.executable).resolve()), 'cwd': str(Path.cwd()),
              'entrypoint': ENTRYPOINTS[service],
              'entrypoint_source': str(ROOT / 'src/kdb/services' / service / 'app.py'),
              'checks_are_local_only': True, 'dependencies': [], 'resources': [],
              'errors': [], 'warnings': ['Presence checks do not prove backend/auth/model validity.']}
    if sys.version_info < (3, 9):
        report['errors'].append('python_3_9_or_newer_required')
    for name in DEPENDENCIES[service]:
        item = probe_module(name)
        report['dependencies'].append(item)
        if not item['available']:
            report['errors'].append('missing_dependency:' + name)
        if name == 'elasticsearch' and item['available']:
            version = item.get('version')
            version_text = '.'.join(str(part) for part in version) if isinstance(version, list) else str(version)
            if not version_text.startswith('8.17.'):
                report['errors'].append('elasticsearch_8_17_required')
    # Original argparse --help exits before reading its runtime resources.
    if '--help' in argv and service in {'off_task', 'files', 'multilingual'}:
        report['warnings'].append('Legacy --help requested; runtime resources not required for help.')
        report['ok'] = not report['errors']
        return report
    if service in {'retrieval', 'off_task', 'crawler', 'files', 'fastgpt_proxy'}:
        read_config(ROOT / 'private/runtime_config/hardcoded_defaults.json', 'private_defaults', report)
    if service == 'retrieval':
        primary = argv[0] if argv else None
        cfg = read_config(primary, 'search_config', report, ['search_engine_config_path', 'embedding_config_path'])
        for field in ['search_engine_config_path', 'embedding_config_path', 'simility_config_path']:
            if cfg.get(field):
                requirements = ['DASHSCOPE_API_KEY'] if field == 'embedding_config_path' else []
                data = read_config(cfg[field], field, report, requirements)
                if field == 'search_engine_config_path' and data:
                    if not str(data.get('es_version', '')).startswith('8.17'):
                        report['errors'].append('engine_config_es_version_8_17_required')
                    if not data.get('index_name') or not data.get('vector_fields'):
                        report['errors'].append('engine_config_index_name_and_vector_fields_required')
    elif service == 'off_task':
        script_root = Path(option(argv, '--script-dir', str(ROOT)))
        if not (ROOT / 'src/kdb/mining/pipelines').is_dir():
            report['errors'].append('missing_pipeline_source:kdb.entrypoints.cli.mining')
        read_config(script_root / 'config/mysql_conn_config.json', 'mysql_config', report, ['host', 'database', 'user', 'password'])
        resource = option(argv, '--resource-config')
        if resource is not None:
            read_config(resource, 'task_resource_config', report)
        report['warnings'].append('Real start creates SQL pool, worker and monitoring threads; mining subprocess PATH is inherited unchanged.')
    elif service == 'files':
        explicit = option(argv, '--config')
        candidates = [explicit] if explicit else [os.environ.get('MINIO_CONFIG_PATH'), ROOT / 'config/minio_config.json', ROOT / 'config/minio_config_default.json', ROOT / 'config/minio_config_default_aws_test.json']
        selected = next((value for value in candidates if value and Path(value).expanduser().is_file()), explicit)
        config = read_config(selected, 'minio_config', report)
        if any(not config.get(field) for field in ['endpoint_url', 'access_key', 'secret_key']):
            report['warnings'].append('Original MinioTools default fields/private defaults will supply omitted connection fields; no client or auth validation performed.')
    elif service == 'multilingual':
        path = Path(option(argv, '--model_path', str(ROOT / 'resources/models/lid.176.ftz')))
        report['resources'].append({'role': 'fasttext_model', 'path': str(path), 'exists': path.is_file()})
        if not path.is_file() or path.stat().st_size == 0:
            report['errors'].append('missing_or_empty_fasttext_model')
    elif service == 'fastgpt_proxy':
        config = Path('config/config.json')
        if config.is_file():
            read_config(config, 'fastgpt_config', report, ['knowledge_base_url'])
        else:
            report['warnings'].append('Original FastGPT built-in upstream/private-default API key fallback is active; no config file, upstream auth validation or request was performed.')
    report['ok'] = not report['errors']
    return report


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] not in ENTRYPOINTS:
        print(json.dumps({'ok': False, 'errors': ['unknown_service']}))
        return 64
    service, legacy = args[0], args[1:]
    check_only = bool(legacy and legacy[0] == '--check')
    if check_only:
        legacy = legacy[1:]
    report = check(service, legacy)
    print(json.dumps(report, ensure_ascii=False), flush=True)
    if not report['ok']:
        return 78
    if check_only:
        return 0
    os.execv(sys.executable, [sys.executable, '-m', ENTRYPOINTS[service], *legacy])
    raise AssertionError('execv unexpectedly returned')


if __name__ == '__main__':
    raise SystemExit(main())
