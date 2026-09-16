import copy,csv,hashlib,importlib.util,json,shutil,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from analyze_results import DEFAULT_BASELINE,load_bundle,load_baseline_results,analyze,write_outputs

class StudyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data,selector=load_bundle(ROOT/'artifacts/study');cls.selector=staticmethod(selector)
    def test_reconstruct_completed_metrics_and_attempt_counts(self):
        r=analyze(self.data,self.selector)
        self.assertEqual(r['totals']['baseline_attempts'],19)
        self.assertEqual(r['totals']['baseline_successes'],9)
        self.assertEqual(r['totals']['correct_A'],12)
        self.assertEqual(r['totals']['suites'],19)
        self.assertEqual(r['totals']['cells'],57)
        self.assertEqual(r['totals']['repairs'],0)
        self.assertEqual(r['macro']['B'],.5)
        self.assertAlmostEqual(r['macro']['public_random'],4/9)
        self.assertEqual(r['tasks']['007']['B_candidates'],[1,2])
        self.assertEqual(r['tasks']['053']['B_candidates'],[2])
        self.assertEqual(r['tasks']['024']['B_decision'],'public_fallback')
    def test_counterfactual_hidden_labels_do_not_change_selection(self):
        original=analyze(self.data,self.selector)
        other=copy.deepcopy(self.data)
        for task in other['tasks'].values():
            for c in task['candidates']:c['historical_reward']=1-c['historical_reward']
            for r in task['records']:r['reward']=1-r['reward']
        counterfactual=analyze(other,self.selector)
        for t in original['tasks']:
            self.assertEqual(original['tasks'][t]['B_candidates'],counterfactual['tasks'][t]['B_candidates'])
            self.assertAlmostEqual(original['tasks'][t]['B']+counterfactual['tasks'][t]['B'],1)
    def test_all_unusable_rows_fall_back_to_public(self):
        row={'source_unchanged':True,'eligible':False,'donor_index':0,'cells':[None]*3}
        self.assertEqual(self.selector([row],{0:False,1:True,2:True})['picked'],[1,2])
    def test_self_vote_cannot_select_its_donor(self):
        row={'source_unchanged':True,'eligible':True,'donor_index':0,'cells':[{'results':[{'status':'pass'}]},None,None]}
        r=self.selector([row],{0:True,1:True,2:True})
        self.assertEqual(r['decision'],'public_fallback');self.assertEqual(r['picked'],[0,1,2])
    def test_prepare_refuses_existing_output(self):
        from run_verification import prepare
        with self.assertRaisesRegex(ValueError,'refusing to overwrite'):
            prepare(ROOT/'artifacts/study',ROOT,[],[],ROOT)
    def test_solved_counts_and_all_public_pass(self):
        r=analyze(self.data,self.selector)
        self.assertEqual(r['solved'],{'B_only_correct_answers':4,'B_mixed_ties':1,'B_only_incorrect_answers':4,'B_average_solved_tasks':4.5,'public_passes':27})
    def test_collect_run_reads_new_results_instead_of_old_outcomes(self):
        from run_study import collect_run
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);dest=out/'implementation/src/selfverify';dest.mkdir(parents=True)
            shutil.copy2(ROOT/'artifacts/study/implementation/src/selfverify/metrics.py',dest/'metrics.py')
            for rec in self.data['tasks']['007']['records']:
                i=rec['candidate_index'];trial=out/'results'/f'paired-007-p{i}'/f'task_007__fixture{i}'
                (trial/'agent').mkdir(parents=True)
                (trial/'result.json').write_text(json.dumps({'verifier_result':{'rewards':{'reward':1}}}))
                (trial/'agent/selfverify_summary.json').write_text(json.dumps({'donor_public':{'public':rec['public']}}))
                (trial/'agent/cross_matrix_row.json').write_text(json.dumps(rec['matrix_row']))
            new=collect_run(self.data,out,['007']);r=analyze(new,self.selector)
            self.assertEqual(list(r['tasks']),['007'])
            self.assertEqual(r['tasks']['007']['A'],[1,1,1])
            self.assertEqual(r['tasks']['007']['B'],.5)
            self.assertEqual([x['reward'] for x in self.data['tasks']['007']['records']],[0,1,0])
            (trial/'result.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'Unscored attempt'):collect_run(self.data,out,['007'])
    def test_expanded_baseline_changes_reference_only(self):
        baseline=load_baseline_results(DEFAULT_BASELINE)
        original=analyze(self.data,self.selector)
        r=analyze(self.data,self.selector,baseline)
        self.assertEqual(r['totals']['baseline_attempts'],27)
        self.assertEqual(r['totals']['baseline_successes'],10)
        self.assertAlmostEqual(r['macro']['baseline_mean'],10/27)
        self.assertAlmostEqual(r['without_017']['baseline_mean'],8/24)
        self.assertEqual(r['baseline_source']['kind'],'user_reported_table')
        for t in original['tasks']:
            for key in ('initial','A','B','B_candidates','B_candidate_rewards','public_random','suites','cells'):
                self.assertEqual(r['tasks'][t][key],original['tasks'][t][key])
        changed=copy.deepcopy(baseline)
        for task in changed['tasks'].values():task['outcomes']=[1-y for y in task['outcomes']]
        counterfactual=analyze(self.data,self.selector,changed)
        for t in r['tasks']:
            self.assertEqual(counterfactual['tasks'][t]['B_candidates'],r['tasks'][t]['B_candidates'])
        self.assertAlmostEqual(counterfactual['macro']['baseline_mean'],17/27)

    def test_export_keeps_baseline_positions_separate_from_patch_ids(self):
        r=analyze(self.data,self.selector,load_baseline_results(DEFAULT_BASELINE))
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);write_outputs(self.data,r,out)
            with (out/'baseline_attempts.csv').open() as f:baseline=list(csv.DictReader(f))
            with (out/'attempts.csv').open() as f:patches=list(csv.DictReader(f))
            self.assertEqual(len(baseline),27)
            self.assertEqual(sum(int(row['solved']) for row in baseline),10)
            self.assertTrue(all(row['run_id']=='' for row in baseline))
            self.assertEqual([row['solved'] for row in baseline if row['task']=='007'],['0','0','1'])
            # The historical 007 patch IDs retain their original outcomes [0,1,None].
            self.assertEqual([row['original_pool_baseline_solved'] for row in patches if row['task']=='007'],['0.0','1.0',''])
            self.assertEqual(len(patches),27)
            self.assertIn('37.04%',(out/'results.md').read_text())

    def test_reported_baseline_requires_binary_outcomes_and_run_id_slots(self):
        baseline=load_baseline_results(DEFAULT_BASELINE)
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'baseline.json'
            for bad in ([0,0,'S'],[0,0,2],[0,0]):
                changed=copy.deepcopy(baseline);changed['tasks']['001']['outcomes']=bad
                p.write_text(json.dumps(changed))
                with self.assertRaisesRegex(ValueError,'three binary baseline outcomes'):load_baseline_results(p)
            changed=copy.deepcopy(baseline);changed['tasks']['001']['run_ids']=[]
            p.write_text(json.dumps(changed))
            with self.assertRaisesRegex(ValueError,'run ID count'):load_baseline_results(p)

    def test_before_after_metrics_and_three_answer_coverage(self):
        r=analyze(self.data,self.selector,load_baseline_results(DEFAULT_BASELINE))
        self.assertEqual(r['totals']['correct_initial'],12)
        self.assertEqual(r['totals']['correct_A'],12)
        self.assertEqual(r['totals']['newly_correct_A'],0)
        self.assertEqual(r['totals']['regressions_A'],0)
        self.assertEqual(r['macro']['initial_mean'],r['macro']['A_mean'])
        for method in ('baseline','initial','A'):
            self.assertEqual(r['coverage'][method]['solved_tasks'],5)
            self.assertEqual(r['coverage'][method]['tasks'],9)
            self.assertAlmostEqual(r['coverage'][method]['fraction'],5/9)
        self.assertIsNone(r['B_pass_at_3'])
        self.assertEqual(r['tasks']['007']['B'],.5)
        self.assertEqual(r['tasks']['007']['A_covered'],1)
        self.assertEqual(r['tasks']['001']['A_covered'],0)

    def test_corrections_and_regressions_do_not_cancel_in_the_counts(self):
        changed=copy.deepcopy(self.data)
        changed['tasks']['007']['records'][0]['reward']=1
        changed['tasks']['007']['records'][1]['reward']=0
        r=analyze(changed,self.selector)
        self.assertEqual(r['totals']['correct_initial'],r['totals']['correct_A'])
        self.assertEqual(r['totals']['newly_correct_A'],1)
        self.assertEqual(r['totals']['regressions_A'],1)
        self.assertEqual(r['tasks']['007']['A_newly_correct'],1)
        self.assertEqual(r['tasks']['007']['A_regressions'],1)

    def test_packaged_grades_and_final_patches_match_report_observations(self):
        artifacts = ROOT / 'artifacts'
        grading = artifacts / 'grading'
        checksums = json.loads((grading / 'checksums.json').read_text())
        for name, digest in checksums.items():
            self.assertEqual(hashlib.sha256((grading / name).read_bytes()).hexdigest(), digest, name)
        records = json.loads((grading / 'index.json').read_text())['records']
        expected = {(task, rec['candidate_index']): rec
                    for task, data in self.data['tasks'].items() for rec in data['records']}
        self.assertEqual(len(records), len(expected))
        self.assertEqual({(rec['task'], rec['candidate_index']) for rec in records}, set(expected))
        for rec in records:
            observed = expected[rec['task'], rec['candidate_index']]
            grade = json.loads((artifacts / rec['reward_file']).read_text())
            self.assertEqual(grade['reward'], observed['reward'])
            self.assertEqual(rec['reward'], observed['reward'])
            self.assertEqual(rec['trial'], observed['trial'])
            self.assertEqual(grade['task_id'], 'task_' + rec['task'])
            self.assertEqual(hashlib.sha256((artifacts / rec['final_patch']).read_bytes()).hexdigest(),
                             rec['final_patch_sha256'])
            self.assertTrue((artifacts / rec['input_patch']).is_file())
        audit = json.loads((artifacts / 'refinement_audit.json').read_text())
        for rec in audit['attempts']:
            for stage in ('initial', 'final'):
                path = ROOT / rec[stage + '_patch']
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), rec[stage + '_sha256'])

if __name__=='__main__':unittest.main()
