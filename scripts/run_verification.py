#!/usr/bin/env python3
"""Prepare or run new verification on the study's supplied repairs."""
import argparse,json,os,re,shutil,signal,subprocess,sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from analyze_results import load_bundle
ROOT=Path(__file__).resolve().parents[1]

def prepare(bundle,out,tasks,env_files,science_root):
    data,_=load_bundle(bundle)
    if out.exists():raise ValueError('Use a new output directory; refusing to overwrite '+str(out))
    if not (science_root/'scripts/run_batch.py').is_file():raise ValueError('Expected release root containing scripts/run_batch.py')
    for f in env_files:
        if not f.is_file():raise ValueError('Missing env file: '+str(f))
        values={}
        for line in f.read_text().splitlines():
            match=re.match(r'(?:export\s+)?([A-Z_]+)\s*=\s*(.*)',line.strip())
            if match:values[match[1]]=match[2].strip().strip(chr(34)).strip(chr(39))
        for key,value in [('CODEX_VERSION','0.154.0'),('CODEX_REASONING_EFFORT','xhigh')]:
            if values.get(key)!=value:raise ValueError(f'{key} must be {value} in the model env file')
    selected=tasks or list(data['tasks'])
    if not set(selected)<=set(data['tasks']):raise ValueError('Unknown task ID')
    out.mkdir(parents=True)
    shutil.copytree(bundle/'implementation',out/'implementation',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    adapter=out/'implementation/scripts/pier_local_python'
    pier_python=Path.home()/'.local/share/uv/tools/datacurve-pier/bin/python'
    if not pier_python.is_file():raise ValueError('Install datacurve-pier with uv tool first')
    adapter.write_text('#!'+str(pier_python)+'\n'+adapter.read_text().split('\n',1)[1])
    jobs=[]
    for task in selected:
        shutil.copytree(bundle/'shards'/task,out/'shards'/task)
        pool=[]
        for c in data['tasks'][task]['candidates']:
            i=c['index'];dest=out/'inputs'/task/f'p{i}';dest.mkdir(parents=True)
            patch=dest/f'task_{task}.patch';shutil.copy2(bundle/c['patch'],patch)
            pool.append({'index':i,'patch':str(patch),'source_sha256':c['source_sha256']})
        (out/'inputs'/task/'pool.json').write_text(json.dumps(pool,indent=2)+'\n')
        for i in range(3):
            lane=len(jobs)%len(env_files);name=f'paired-{task}-p{i}'
            cmd=[sys.executable,str(out/'implementation/scripts/run_experiment.py'),'--condition','selfverify','--verification-mode','contract',
                 '--path',str(out/'shards'/task),'--initial-patches',str(out/'inputs'/task/f'p{i}'),'--env-file',str(env_files[lane]),
                 '--swe-science-root',str(science_root),'--jobs-dir',str(out/'results'),'--job-name',name,'--model','Qwen3.8-27B',
                 '--n-attempts','1','--n-concurrent','1','--max-loop-seconds','6000','--test-design-timeout-sec','1800',
                 '--repair-timeout-sec','900','--verify-timeout-sec','60','--max-repair-rounds','1','--agent-timeout-multiplier','2']
            jobs.append({'name':name,'lane':lane,'command':cmd})
    (out/'jobs.json').write_text(json.dumps(jobs,indent=2)+'\n');(out/'logs').mkdir()
    return jobs

def execute(out,jobs,lanes):
    def lane(number):
        for job in (j for j in jobs if j['lane']==number):
            with (out/'logs'/f"{job['name']}.log").open('wb') as f:
                # Same proxy adapter as the original run. It delegates to Pier installed through uv tool.
                proc=subprocess.Popen(job['command'],cwd=out/'implementation',stdout=f,stderr=subprocess.STDOUT,start_new_session=True,
                    env={**os.environ,'PIER_PY':str(out/'implementation/scripts/pier_local_python')})
                try:proc.wait(timeout=8400)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid,signal.SIGTERM)
                    try:proc.wait(timeout=20)
                    except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
                    raise RuntimeError('Job watchdog expired: '+job['name'])
            (out/'logs'/f"{job['name']}.status.json").write_text(json.dumps({'returncode':proc.returncode})+'\n')
            if proc.returncode:raise RuntimeError('Failed job: '+job['name'])
    with ThreadPoolExecutor(max_workers=lanes) as executor:list(executor.map(lane,range(lanes)))

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--bundle',type=Path,default=ROOT/'artifacts/study');ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--task',action='append',default=[]);ap.add_argument('--env-file',type=Path,action='append',required=True)
    ap.add_argument('--science-root',type=Path,required=True);ap.add_argument('--run',action='store_true',help='Execute inference; otherwise prepare only')
    a=ap.parse_args();out=a.out.resolve()
    jobs=prepare(a.bundle.resolve(),out,a.task,[f.expanduser().resolve() for f in a.env_file],a.science_root.resolve())
    print(f'Prepared {len(jobs)} new verifier branches in {out}. No candidate patches are regenerated.',flush=True)
    if a.run:execute(out,jobs,len(a.env_file))
if __name__=='__main__':main()
