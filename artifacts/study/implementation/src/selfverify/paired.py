"""Diagnostic paired refinement/selection on a frozen historical candidate pool."""
import ast,hashlib,json,uuid
from pathlib import Path
from selfverify.agent import SelfVerifyCodex, AgentBudgetExceeded
from selfverify.contract import worker,snapshot,evaluate,assess,improves,finalize
from selfverify.stages import discover_workdir,load_prompt,write_remote_text

def legacy_suite(files):
    if sum(len(s.encode()) for s in files.values())>256000:raise ValueError('suite too large')
    inv=json.loads(files.get('manifest.json','{}')).get('invariants',[])
    if not isinstance(inv,list) or not 1<=len(inv)<=5:raise ValueError('expected 1-5 invariants')
    tests=[];names=set()
    for entry in inv:
        path=entry.get('path','');name=Path(path).name
        if path not in (name,'selfverify/invariants/'+name):raise ValueError('invalid test path')
        if name in names or not name.startswith('invariant_') or not name.endswith('.py') or name not in files:raise ValueError('missing or duplicate script')
        if not any(isinstance(n,ast.Assert) for n in ast.walk(ast.parse(files[name]))):raise ValueError('no assertion')
        names.add(name);tests.append({'path':name,'invariant':entry.get('invariant',''),'rationale':entry.get('rationale','')})
    return {'files':dict(files),'tests':tests,'sha256':hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()}

def select_cross(rows,public,n=3):
    """No labels are accepted by this selector; unavailable votes abstain."""
    votes={i:[] for i in range(n)}
    for row in rows:
        if not row.get('source_unchanged') or not row.get('eligible'):continue
        for i,cell in enumerate(row['cells']):
            if i==row['donor_index'] or not cell:continue
            rr=cell['results'];statuses=[r['status'] for r in rr]
            if statuses and all(s in ('pass','assertion') for s in statuses):
                votes[i].append(int(all(s=='pass' for s in statuses)))
    eligible=[i for i in range(n) if public.get(i)] or list(range(n))
    scores={i:sum(v)/len(v) for i,v in votes.items() if v and i in eligible}
    picked=[i for i,s in scores.items() if s==max(scores.values())] if scores else eligible
    return {'picked':picked,'scores':scores,'votes':votes,'decision':'cross_vote' if scores else 'public_fallback','tie_policy':'uniform'}

class PairedVerification(SelfVerifyCodex):
    async def _run_selfverify_loop(self,*,instruction,environment,env,logger):
        if self.verification_mode=='continue':
            return await super()._run_selfverify_loop(instruction=instruction,environment=environment,env=env,logger=logger)
        workdir=await discover_workdir(environment);scratch='/tmp/paired-'+uuid.uuid4().hex
        st={'workdir':workdir,'scratch':scratch,'base':scratch+'/base','design':scratch+'/design','runtime':scratch+'/runtime.py'}
        self.artifacts['contract']=st
        await write_remote_text(environment,st['runtime'],Path(__file__).with_name('contract_runtime.py').read_text())
        st.update(await worker(self,environment,'prepare',base=st['base'],design=st['design']))
        st['selected']=await snapshot(self,environment,'original')
        donor_index=int(Path(self.initial_patches).name[1:])
        pool=json.loads((Path(self.initial_patches).parent/'pool.json').read_text())
        source=Path(pool[donor_index]['patch']).read_text();remote=scratch+'/donor.patch'
        await write_remote_text(environment,remote,source);await worker(self,environment,'apply',patch=remote)
        donor=await snapshot(self,environment,'donor');st['selected']=donor
        original_source=(await worker(self,environment,'suite'))['source_sha256']
        public=await evaluate(self,environment,{'files':{},'tests':[]},donor)
        self.artifacts['donor_public']=public
        await write_remote_text(environment,workdir+'/selfverify/README.txt','Self-verify artifacts for this trial.\n')
        logger.log('invariant_gen',status='begin',donor_index=donor_index,timeout_seconds=self.test_design_timeout_sec)
        original_instruction=self._original_instruction;self._original_instruction=None
        try:
            await self._codex_exec(environment,instruction=load_prompt('paired_generation.md'),env=env,
                output_name='codex_invariants_r0.txt',stage='invariant_gen',cwd=workdir,timeout_sec=self.test_design_timeout_sec)
        except (AgentBudgetExceeded,RuntimeError) as exc:logger.log('invariant_gen',status='incomplete',error=str(exc))
        finally:self._original_instruction=original_instruction
        raw=await worker(self,environment,'suite')
        host=self.logs_dir/'paired_suite';host.mkdir(parents=True,exist_ok=True)
        for name,data in raw['files'].items():(host/name).write_text(data)
        row={'donor_index':donor_index,'source_unchanged':raw['source_sha256']==original_source,'cells':[None]*len(pool),'eligible':False}
        def save_row():
            self.artifacts['paired']=row
            (self.logs_dir/'cross_matrix_row.json').write_text(json.dumps(row,indent=2)+'\n')
        save_row()
        try:
            if not row['source_unchanged']:raise ValueError('generator modified source')
            suite=legacy_suite(raw['files'])
        except (ValueError,KeyError,TypeError,SyntaxError) as exc:
            row['suite_error']=str(exc);save_row();logger.log('done',reason='no_usable_suite',error=str(exc));return
        row['suite_sha256']=suite['sha256'];row['n_tests']=len(suite['tests']);save_row()
        logger.log('invariant_gen',status='frozen',n_tests=len(suite['tests']),sha256=suite['sha256'])
        await finalize(self,environment,logger)
        pre=await evaluate(self,environment,suite,None,public=False);row['pre']=pre
        statuses=[r['status'] for r in pre['results']]
        row['eligible']='assertion' in statuses and all(s in ('pass','assertion') for s in statuses)
        # Other patches are uploaded only after the donor's suite is frozen.
        for i,candidate in enumerate(pool):
            path=scratch+f'/cross_{i}.patch'
            await write_remote_text(environment,path,Path(candidate['patch']).read_text())
            row['cells'][i]=await evaluate(self,environment,suite,{'path':path})
            save_row();logger.log('cross_eval',donor_index=donor_index,candidate_index=i,status='done')
        own=row['cells'][donor_index];assessment=assess(pre,own)
        row['self_before']=assessment;row['refinement_attempted']=False;save_row()
        if not assessment['failed'] and assessment['public_pass']:
            logger.log('done',reason='own_checks_passed_no_repair');return
        if not assessment['passed'] and not assessment['failed']:
            logger.log('done',reason='no_semantic_feedback');return
        for name,data in suite['files'].items():await write_remote_text(environment,workdir+'/selfverify/invariants/'+name,data)
        evidence={'assessment':assessment,'results':own,'requirements':suite['tests'],'suite_sha256':suite['sha256']}
        row['refinement_attempted']=True;save_row();logger.log('contract_repair',status='begin',round=1)
        try:
            await self._codex_exec(environment,instruction=load_prompt('contract_repair.md')+'\n\nEvidence:\n'+json.dumps(evidence,indent=2),
                env=env,output_name='codex_contract_repair_r1.txt',stage='contract_repair',cwd=workdir,
                timeout_sec=self.repair_timeout_sec,reserve_sec=(len(suite['tests'])+1)*self.verify_timeout_sec+90)
        except (AgentBudgetExceeded,RuntimeError) as exc:logger.log('contract_repair',status='incomplete',error=str(exc))
        self.artifacts['revisions']+=1
        revised=await snapshot(self,environment,'revised')
        after=await evaluate(self,environment,suite,revised);new=assess(pre,after)
        promoted=improves(assessment,new)
        if promoted:st['selected']=revised
        row.update(self_after=new,refinement_evaluation=after,promoted=promoted);save_row()
        logger.log('done',reason='own_refinement_evaluated',promoted=promoted)
