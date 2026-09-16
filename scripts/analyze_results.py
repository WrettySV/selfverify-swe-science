#!/usr/bin/env python3
"""Recompute the nine-task report from packaged observations; no inference."""
import argparse,csv,hashlib,importlib.util,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DEFAULT_BASELINE=ROOT/'artifacts/baseline_results.json'

def load_bundle(bundle):
    for rel,digest in json.loads((bundle/'checksums.json').read_text()).items():
        if hashlib.sha256((bundle/rel).read_bytes()).hexdigest()!=digest:
            raise ValueError('Artifact checksum mismatch: '+rel)
    spec=importlib.util.spec_from_file_location('frozen_selector',bundle/'selector.py')
    selector=importlib.util.module_from_spec(spec);spec.loader.exec_module(selector)
    return json.loads((bundle/'data.json').read_text()),selector.select_cross

def load_baseline_results(path):
    baseline=json.loads(Path(path).read_text())
    if not isinstance(baseline.get('source'),dict) or not isinstance(baseline.get('tasks'),dict):
        raise ValueError('Baseline results require source metadata and task outcomes')
    for task,record in baseline['tasks'].items():
        outcomes=record.get('outcomes')
        if not isinstance(outcomes,list) or len(outcomes)!=3 or any(type(x) is not int or x not in (0,1) for x in outcomes):
            raise ValueError('Expected three binary baseline outcomes: '+task)
        if len(record.get('run_ids',[]))!=len(outcomes):
            raise ValueError('Baseline run ID count differs from outcome count: '+task)
    return baseline

def analyze(data,select_cross,baseline_results=None):
    tasks={};totals={'correct_initial':0,'baseline_successes':0,'baseline_attempts':0,'correct_A':0,'suites':0,'cells':0,'repairs':0,'promotions':0,'own_false_accepts':0,'own_incorrect_with_suite':0,'newly_correct_A':0,'regressions_A':0}
    for task,d in sorted(data['tasks'].items()):
        rows=[];public={}
        for rec in d['records']:
            row=rec.get('matrix_row')
            if row:rows.append(row)
            if 'status' in rec['public']:public[rec['candidate_index']]=rec['public']['status']=='pass'
            if row:
                for i,cell in enumerate(row['cells']):
                    if cell:public[i]=cell.get('public',{}).get('status')=='pass'
        if len(public)!=3:raise ValueError('Incomplete public observations: '+task)
        # Decisions are made before correctness labels are retrieved.
        chosen=select_cross(rows,public,n=3)
        labels=[c['historical_reward'] for c in d['candidates']]
        outcomes=[rec['reward'] for rec in d['records']]
        if not all(v in (0,1) for v in labels+outcomes):raise ValueError('Missing binary labels')
        baseline_in_pool=[v if c['job']=='baseline-main12-n3' else None for v,c in zip(labels,d['candidates'])]
        if baseline_results is not None:
            if task not in baseline_results['tasks']:raise ValueError('Missing baseline task: '+task)
            baseline=list(baseline_results['tasks'][task]['outcomes'])
            baseline_run_ids=list(baseline_results['tasks'][task]['run_ids'])
        else:
            baseline=baseline_in_pool
            baseline_run_ids=[c['trial'] if v is not None else None for c,v in zip(d['candidates'],baseline)]
        observed=[v for v in baseline if v is not None]
        public_ids=[i for i in range(3) if public[i]] or list(range(3))
        suites=sum(bool(row.get('suite_sha256')) for row in rows)
        repairs=sum(bool(row.get('refinement_attempted')) for row in rows)
        cells=sum(c is not None for row in rows for c in row['cells'])
        picked=chosen['picked']
        value={'baseline':baseline,'baseline_in_pool':baseline_in_pool,'baseline_run_ids':baseline_run_ids,'initial':labels,'A':outcomes,'baseline_mean':sum(observed)/len(observed),
               'initial_mean':sum(labels)/3,'A_mean':sum(outcomes)/3,
               'baseline_covered':int(any(observed)),'initial_covered':int(any(labels)),'A_covered':int(any(outcomes)),
               'A_newly_correct':sum(before==0 and after==1 for before,after in zip(labels,outcomes)),
               'A_regressions':sum(before==1 and after==0 for before,after in zip(labels,outcomes)),
               'public_random':sum(labels[i] for i in public_ids)/len(public_ids),
               'B':sum(labels[i] for i in picked)/len(picked),'B_candidates':[i+1 for i in picked],
               'B_candidate_rewards':[labels[i] for i in picked],'B_decision':chosen['decision'],
               'public_passes':sum(public.values()),
               'suites':suites,'cells':cells,'repairs':repairs,'suite_errors':[r.get('suite_error') for r in rows if r.get('suite_error')],
               'oracle':max(labels)}
        tasks[task]=value
        totals['newly_correct_A']+=value['A_newly_correct'];totals['regressions_A']+=value['A_regressions']
        totals['correct_initial']+=sum(labels);totals['baseline_successes']+=sum(observed);totals['baseline_attempts']+=len(observed)
        totals['correct_A']+=sum(outcomes);totals['suites']+=suites;totals['cells']+=cells;totals['repairs']+=repairs
        totals['promotions']+=sum(bool(row.get('promoted')) for row in rows)
        for row in rows:
            i=row['donor_index']
            if row.get('suite_sha256') and labels[i]==0:
                totals['own_incorrect_with_suite']+=1
                own=row['cells'][i]
                if own and all(x['status']=='pass' for x in own['results']):totals['own_false_accepts']+=1
    macro={key:sum(d[key] for d in tasks.values())/len(tasks) for key in ['baseline_mean','initial_mean','A_mean','public_random','B','oracle']}
    sensitivity=[d for t,d in tasks.items() if t!='017']
    without={key:sum(d[key] for d in sensitivity)/len(sensitivity) for key in macro} if sensitivity else {}
    records=[rec for t in data['tasks'].values() for rec in t['records']]
    usage={'complete_branches':sum(r['usage']['complete'] for r in records),'totals':{k:sum(r['usage']['totals'][k] for r in records) for k in records[0]['usage']['totals']}}
    solved={'B_only_correct_answers':sum(d['B']==1 for d in tasks.values()),
            'B_mixed_ties':sum(0<d['B']<1 for d in tasks.values()),
            'B_only_incorrect_answers':sum(d['B']==0 for d in tasks.values()),
            'B_average_solved_tasks':sum(d['B'] for d in tasks.values()),
            'public_passes':sum(d['public_passes'] for d in tasks.values())}
    coverage={key:{'solved_tasks':sum(d[field] for d in tasks.values()),'tasks':len(tasks),
                   'fraction':sum(d[field] for d in tasks.values())/len(tasks)}
              for key,field in [('baseline','baseline_covered'),('initial','initial_covered'),('A','A_covered')]}
    return {'tasks':tasks,'totals':totals,'macro':macro,'without_017':without,'usage':usage,'solved':solved,'coverage':coverage,
            'B_pass_at_3':None,
            'baseline_source':baseline_results['source'] if baseline_results is not None else {'kind':'packaged_historical_results'}}

def vector(xs):return '['+', '.join('-' if x is None else str(int(x)) for x in xs)+']'
def attempt_text(values):
    observed=[v for v in values if v is not None]
    return ', '.join('S' if v else 'F' for v in observed)+f"; {sum(observed):.0f}/{len(observed)}"

def selection_text(d):
    if d['B']==1:return 'Solved'
    if d['B']==0:return 'Failed'
    return f"{d['B']:.0%} chance: {sum(d['B_candidate_rewards']):.0f} correct among {len(d['B_candidate_rewards'])} tied answers"

def render_attempt_table(result):
    lines=['| Task | Baseline attempts | A: own-test verification |','|---|---|---|']
    for t,d in result['tasks'].items():
        lines.append(f"| {t} | {attempt_text(d['baseline'])} | {attempt_text(d['A'])} |")
    n=result['totals'];m=result['macro'];c=result['coverage'];count=3*len(result['tasks'])
    lines.append(f"| **Correct answers** | **{n['baseline_successes']:.0f}/{n['baseline_attempts']}** | **{n['correct_A']:.0f}/{count}** |")
    lines.append(f"| **Mean pass@1** | **{m['baseline_mean']:.2%}** | **{m['A_mean']:.2%}** |")
    lines.append('| **Tasks with at least one correct answer** | '+' | '.join(f"**{c[key]['solved_tasks']}/{c[key]['tasks']} ({c[key]['fraction']:.2%})**" for key in ('baseline','A'))+' |')
    return '\n'.join(lines)

def render_success_table(result):
    lines=['| Task | Baseline | Random choice | A | B |','|---|---:|---:|---:|---:|']
    for t,d in result['tasks'].items():
        lines.append(f"| {t} | {d['baseline_mean']:.2%} | {d['public_random']:.2%} | {d['A_mean']:.2%} | {d['B']:.2%} |")
    m=result['macro']
    lines.append(f"| **Mean** | **{m['baseline_mean']:.2%}** | **{m['public_random']:.2%}** | **{m['A_mean']:.2%}** | **{m['B']:.2%}** |")
    return '\n'.join(lines)

def render(result):
    m=result['macro'];n=result['totals'];q=result['solved']
    lines=['# Nine-task study results', '',
           'S = correct under the benchmark hidden checks; F = incorrect. The table shows final outcomes for baseline and A. Their starting repairs are different sets.', '',
           render_attempt_table(result), '',
           'The at-least-one row measures observed coverage of the three answers (the pass@3 event). It does not show whether a selector returns the correct answer.', '',
           '## Success of one answer', '',
           render_success_table(result), '',
           'Baseline and A use empirical pass@1: correct answers divided by attempts, then averaged over tasks. Random choice uses the same starting answers as B. B averages over equally likely choices with the best generated-test score; this is conditional selection success on these answers, not repeated full-solver pass@1.',
           'B pass@3 is not measured: there is one three-answer selection per task, not three independent complete B runs.', '',
           f"Public checks pass for {q['public_passes']}/{3*len(result['tasks'])} initial answers, so public filtering leaves the random-choice control unchanged.",
           f"B leaves only correct answers on {q['B_only_correct_answers']} tasks, mixed correct/incorrect ties on {q['B_mixed_ties']}, and only incorrect answers on {q['B_only_incorrect_answers']}. Its mean single-answer success is {m['B']:.2%}.",
           f"Accepted test sets: {n['suites']}/{3*len(result['tasks'])}; recorded test-set/patch executions: {n['cells']}.", '']
    return '\n'.join(lines)

def write_outputs(data,result,out):
    out.mkdir(parents=True,exist_ok=True)
    (out/'metrics.json').write_text(json.dumps(result,indent=2)+'\n')
    (out/'results.md').write_text(render(result))
    (out/'baseline_source.json').write_text(json.dumps(result['baseline_source'],indent=2)+'\n')
    with (out/'baseline_attempts.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['task','reported_position','solved','run_id','source'])
        for t,d in result['tasks'].items():
            for i,(v,run_id) in enumerate(zip(d['baseline'],d['baseline_run_ids']),1):
                if v is not None:w.writerow([t,i,v,run_id,result['baseline_source']['kind']])
    with (out/'per_task_metrics.csv').open('w',newline='') as f:
        columns=['baseline_mean','initial_mean','A_mean','public_random','B','baseline_covered','initial_covered','A_covered','A_newly_correct','A_regressions']
        w=csv.writer(f);w.writerow(['task']+columns)
        for t,d in result['tasks'].items():w.writerow([t]+[d[k] for k in columns])
    with (out/'attempts.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['task','attempt','original_run','original_method','original_pool_baseline_solved','initial_solved','after_own_tests_solved','shortlisted_by_cross_testing'])
        for t,d in result['tasks'].items():
            for i,c in enumerate(data['tasks'][t]['candidates']):
                w.writerow([t,i+1,c['trial'],c['job'],d['baseline_in_pool'][i],d['initial'][i],d['A'][i],i+1 in d['B_candidates']])

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--bundle',type=Path,default=ROOT/'artifacts/study');ap.add_argument('--out',type=Path,default=ROOT/'work/study-results');ap.add_argument('--baseline-results',type=Path,default=DEFAULT_BASELINE);args=ap.parse_args()
    data,selector=load_bundle(args.bundle);r=analyze(data,selector,load_baseline_results(args.baseline_results));write_outputs(data,r,args.out)
    print(render(r));print('Outputs:',args.out)
if __name__=='__main__':main()
