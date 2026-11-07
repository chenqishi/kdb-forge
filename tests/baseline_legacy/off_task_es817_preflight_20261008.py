"""Readonly offline-worker readiness metadata; no job or ES connection."""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('tests/off_task_es817_preflight_20261008.py')
import importlib.util
import json
import shlex
import subprocess
from pathlib import Path

ROOT = Path(__legacy_source_file__).resolve().parents[1]
OUT = ROOT/'docs/reviews/off_task_es817_20261008'
REMOTE = r'''
import hashlib,json,os,shutil,subprocess,time
from pathlib import Path
root=Path('/root/knowledge_database_builder')
report={'root':str(root),'captured_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'processes':[],'configs':[],'sources':[],'interpreter_probes':[]}
for p in Path('/proc').iterdir():
    if not p.name.isdigit():continue
    try:
        args=[a.decode(errors='replace') for a in (p/'cmdline').read_bytes().split(b'\0') if a]
        if not any(a.endswith('/off_task_control_service.py') or a=='off_task_control_service.py' for a in args):continue
        environment=dict(item.split(b'=',1) for item in (p/'environ').read_bytes().split(b'\0') if b'=' in item)
        path=environment.get(b'PATH',b'').decode()
        python=shutil.which('python',path=path)
        script_dir=args[args.index('--script-dir')+1] if '--script-dir' in args else None
        report['processes'].append({'pid':int(p.name),'start_ticks':(p/'stat').read_text().rsplit(') ',1)[1].split()[19],
            'cwd':os.readlink(p/'cwd'),'exe':os.readlink(p/'exe'),'script_dir':script_dir,'path_python':python})
        if python:
            version_probe=subprocess.run([python,'-c',"import elasticsearch,json,sys,importlib.util; print(json.dumps(dict(executable=sys.executable,version=sys.version.split()[0],client=getattr(elasticsearch,'__versionstr__',str(elasticsearch.__version__)),fire=bool(importlib.util.find_spec('fire')))))"],
                capture_output=True,text=True,timeout=10,env={**os.environ,'PATH':path})
            report['interpreter_probes'].append({'returncode':version_probe.returncode,'result':json.loads(version_probe.stdout) if version_probe.returncode==0 else 'dependency probe failed'})
    except OSError:pass
for p in sorted((root/'config').glob('*.json')):
    try:config=json.loads(p.read_text())
    except Exception:continue
    if not isinstance(config,dict) or 'search_engine_config_path' not in config:continue
    target=Path(config['search_engine_config_path'])
    if not target.is_absolute():target=root/target
    row={'business_config':str(p),'business_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
        'engine_config':str(target),'engine_exists':target.exists(),'check_duplicate':config.get('check_duplicate',True)}
    if target.exists():
        engine=json.loads(target.read_text())
        row.update(es_version=engine.get('es_version'),vector_fields=engine.get('vector_fields'),providers=list((engine.get('providers') or {}).keys()),engine_sha256=hashlib.sha256(target.read_bytes()).hexdigest())
    report['configs'].append(row)
for name in ['knowledge_interface_tools/es8_search_interface.py','knowledge_interface_tools/es8_client_router.py','knowledge_interface_tools/es_search_interface.py','knowledge_interface_tools/search_index_data_interface.py','control_service/off_task_control_service.py']:
    p=root/name
    row={'file':name,'exists':p.exists()}
    if p.exists():
        source=p.read_text();row.update(sha256=hashlib.sha256(source.encode()).hexdigest(),has_es8_import='es8_search_interface' in source)
    report['sources'].append(row)
report['specific_configs']={name:(root/'config'/name).exists() for name in ['mercado_local_config.json','payoneer_olive_config.json','config_for_search_index_es817.local.json','config_es_engine_es817.old.local.json']}
print(json.dumps(report,ensure_ascii=False))
'''


def main():
    target = OUT/'preflight.json'
    if target.exists():
        raise ValueError('preserve prior preflight evidence')
    result = subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=8','shenzhen-120',
        'python3 -c '+shlex.quote(REMOTE)],capture_output=True,text=True,timeout=30,check=True)
    evidence = {'main':json.loads(result.stdout),'sg':{'root':str(ROOT),'configs':[]}}
    for name in ('config_for_search_index.json','config_for_search_index_es817.local.json'):
        cfg = json.loads((ROOT/'config'/name).read_text())
        evidence['sg']['configs'].append({'config':name,'engine_config':cfg['search_engine_config_path']})
    probe = subprocess.run(['/root/kdb-forge/.venv-es817/bin/python','-c',
        "import importlib.util,json;print(json.dumps({k:bool(importlib.util.find_spec(k)) for k in ['fire','termcolor','six','flask','mysql','minio','elasticsearch']}))"],
        capture_output=True,text=True,timeout=10,check=True)
    evidence['sg']['retrieval_venv_modules']=json.loads(probe.stdout)
    evidence['actual_es_reads']=evidence['actual_es_writes']=evidence['model_calls']=0
    target.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
    target.chmod(0o600)
    print(json.dumps(evidence,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
