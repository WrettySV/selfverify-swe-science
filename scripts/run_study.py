#!/usr/bin/env python3
"""One entry point for the nine-task study and its result tables."""
import argparse,copy,importlib.util,json
from pathlib import Path
from analyze_results import ROOT,DEFAULT_BASELINE,load_bundle,load_baseline_results,analyze,write_outputs,render

def collect_run(data,out,tasks):
    """Read new executions, retaining recorded correctness of initial answers for B."""
    result=copy.deepcopy(data)
    result['tasks']={t:d for t,d in result['tasks'].items() if t in tasks}
    path=out/'implementation/src/selfverify/metrics.py'
    spec=importlib.util.spec_from_file_location('run_usage',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    for task,d in result['tasks'].items():
        records=[]
        for i in range(3):
            paths=list((out/'results'/f'paired-{task}-p{i}').glob('task_*/result.json'))
            if len(paths)!=1:raise ValueError(f'Missing or ambiguous completed attempt: {task}/{i+1}')
            trial=paths[0].parent;raw=json.loads(paths[0].read_text())
            reward=((raw.get('verifier_result') or {}).get('rewards') or {}).get('reward')
            if reward not in (0,1):raise ValueError(f'Unscored attempt: {task}/{i+1}; inspect its logs')
            summary=json.loads((trial/'agent/selfverify_summary.json').read_text())
            row=trial/'agent/cross_matrix_row.json'
            records.append({'candidate_index':i,'trial':trial.name,'reward':reward,
                'public':summary.get('donor_public',{}).get('public',{}),
                'matrix_row':json.loads(row.read_text()) if row.exists() else None,
                'usage':module.collect_session_usage(trial/'agent')})
        d['records']=records
    return result

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out',type=Path,default=ROOT/'work/study-results')
    ap.add_argument('--bundle',type=Path,default=ROOT/'artifacts/study')
    ap.add_argument('--baseline-results',type=Path,default=DEFAULT_BASELINE,help='Baseline outcome table')
    ap.add_argument('--new-tests',action='store_true',help='Generate and execute new tests on supplied initial repairs, then report')
    ap.add_argument('--science-root',type=Path)
    ap.add_argument('--env-file',type=Path,action='append',default=[])
    ap.add_argument('--task',action='append',default=[])
    ap.add_argument('--check',action='store_true',help='Prepare an inference run without model calls (with --new-tests)')
    a=ap.parse_args();data,selector=load_bundle(a.bundle.resolve());out=a.out.resolve()
    baseline=load_baseline_results(a.baseline_results)
    if a.new_tests:
        if not a.science_root or not a.env_file:ap.error('--new-tests requires --science-root and --env-file')
        from run_verification import prepare,execute
        jobs=prepare(a.bundle.resolve(),out,a.task,[p.expanduser().resolve() for p in a.env_file],a.science_root.resolve())
        if a.check:
            print(f'Prepared {len(jobs)} attempts in {out}; no model calls.');return
        execute(out,jobs,len(a.env_file))
        data=collect_run(data,out,a.task or list(data['tasks']))
        (out/'observations.json').write_text(json.dumps(data,indent=2)+'\n')
    else:
        if a.check or a.science_root or a.env_file:ap.error('Inference options require --new-tests')
        if a.task:
            if not set(a.task)<=set(data['tasks']):ap.error('Unknown task ID')
            data['tasks']={t:d for t,d in data['tasks'].items() if t in a.task}
    result=analyze(data,selector,baseline);write_outputs(data,result,out)
    print(render(result));print('Results:',out)
if __name__=='__main__':main()
