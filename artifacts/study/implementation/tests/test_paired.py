import asyncio,json,shutil,subprocess,time,unittest
from pathlib import Path
from unittest.mock import patch
from selfverify.paired import PairedVerification,select_cross
from selfverify.agent import AgentBudgetExceeded
from selfverify.contract import finalize
from selfverify.logging import RunLogger
from test_contract import RuntimeTests
from test_contract_integration import Environment

def cell(status):return {'results':[{'status':status}]}
class SelectorTests(unittest.TestCase):
    def test_diagonal_excluded_and_errors_abstain(self):
        rows=[{'donor_index':0,'source_unchanged':True,'eligible':True,'cells':[cell('pass'),cell('assertion'),cell('runtime_error')]},
              {'donor_index':1,'source_unchanged':True,'eligible':True,'cells':[cell('pass'),cell('pass'),cell('pass')]}]
        r=select_cross(rows,{0:True,1:True,2:True})
        self.assertEqual(r['votes'],{0:[1],1:[0],2:[1]});self.assertEqual(r['picked'],[0,2])
    def test_missing_or_invalid_suites_fall_back_to_public(self):
        rows=[{'donor_index':0,'source_unchanged':False,'eligible':True,'cells':[cell('pass')]*3}]
        self.assertEqual(select_cross(rows,{0:False,1:True,2:True})['picked'],[1,2])
class FlowTests(unittest.TestCase):
    setUp=RuntimeTests.setUp
    snapshot=RuntimeTests.snapshot
    def test_frozen_cross_evaluation_then_own_repair(self):self.flow('repair')
    def test_own_pass_does_not_force_repair(self):self.flow('pass')
    def test_missing_suite_preserves_donor(self):self.flow('missing')
    def flow(self,mode):
        async def run():
            pool=[]
            codes=['def double(x): return 6\n','def double(x): return 2*x\n','def double(x): return x\n']
            if mode=='pass':codes[0]=codes[1]
            for i,code in enumerate(codes):
                (self.work/'source/calc.py').write_text(code);self.snapshot(f'p{i}.patch')
                d=self.root/'inputs'/f'p{i}';d.mkdir(parents=True)
                shutil.copyfile(self.root/f'p{i}.patch',d/(self.work.name+'.patch'))
                pool.append({'index':i,'patch':str(d/(self.work.name+'.patch'))})
            (self.root/'inputs/pool.json').write_text(json.dumps(pool))
            subprocess.run(['git','-C',str(self.work),'reset','--hard',self.prepared['baseline']],check=True,capture_output=True)
            a=object.__new__(PairedVerification);a.verification_mode='contract';a.artifacts={'revisions':0};a.logs_dir=self.root/'logs';a.logs_dir.mkdir()
            a.initial_patches=str(self.root/'inputs/p0');a._original_instruction='double the input';a._deadline=time.monotonic()+300
            a.finalize_reserve_sec=10;a.verify_timeout_sec=2;a.test_design_timeout_sec=10;a.repair_timeout_sec=10
            stages=[]
            async def codex(environment,**kw):
                stages.append(kw['stage'])
                if kw['stage']=='invariant_gen':
                    self.assertEqual((self.work/'source/calc.py').read_text(),codes[0])
                    self.assertFalse(list(Path(a.artifacts['contract']['scratch']).glob('cross_*.patch')))
                    if mode=='missing':raise AgentBudgetExceeded('no files')
                    p=self.work/'selfverify/invariants';p.mkdir()
                    (p/'manifest.json').write_text(json.dumps({'invariants':[{'path':'selfverify/invariants/invariant_bug.py'},{'path':'selfverify/invariants/invariant_zero.py'}]}))
                    (p/'invariant_bug.py').write_text('from calc import double\nassert double(3)==6\n')
                    (p/'invariant_zero.py').write_text('from calc import double\nassert double(0)==0\n')
                elif kw['stage']=='contract_repair':
                    self.assertIn('regression',kw['instruction'])
                    (self.work/'source/calc.py').write_text(codes[1])
                    (self.work/'selfverify/invariants/invariant_zero.py').write_text('assert False\n')
                else:self.fail('unexpected stage')
            a._codex_exec=codex;env=Environment();logger=RunLogger(a.logs_dir)
            with patch('selfverify.paired.discover_workdir',return_value=str(self.work)):
                await a._run_selfverify_loop(instruction='double the input',environment=env,env={},logger=logger)
            self.addCleanup(shutil.rmtree,a.artifacts['contract']['scratch'],True)
            await finalize(a,env,logger);row=a.artifacts['paired']
            self.assertEqual(stages,['invariant_gen']+(['contract_repair'] if mode=='repair' else []))
            self.assertEqual((self.work/'source/calc.py').read_text(),codes[1] if mode=='repair' else codes[0])
            if mode=='missing':self.assertIn('suite_error',row)
            else:
                self.assertEqual(len(row['cells']),3);self.assertTrue(row['eligible'])
                if mode=='repair':self.assertTrue(row['promoted']);self.assertEqual(row['self_after']['failed'],[])
        asyncio.run(run())
