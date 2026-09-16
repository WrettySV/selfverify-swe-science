# Cross-Candidate Verification for Scientific Software Repair

**Nine tasks · three proposed repairs per task · completed 16 September 2026**

Repository: [WrettySV/selfverify-swe-science](https://github.com/WrettySV/selfverify-swe-science) · Running the study: [README_v3.md](README_v3.md)

## Abstract

A coding agent can make a scientific program pass its visible example while leaving the underlying bug unresolved. Additional tests could reveal the missing behavior, but tests written by the same model may repeat the assumptions behind its repair. We examine two ways to use model-written tests: let an agent improve its own answer, or compare several answers using tests written for the other answers. We implement both workflows and evaluate them on nine scientific software tasks, using three existing repairs per task and newly generated tests. All 27 repairs pass the visible test, yet only 12 solve the task under the benchmark's hidden checks. Own tests never trigger an improvement. Cross-testing narrows the choice on two tasks: its chance of selecting a correct answer rises from 44.44% for random choice to 50.00%. The original baseline attempts also average 50.00%. The result therefore shows useful selection evidence on these answers, alongside a clear failure to obtain feedback for self-refinement; it does not establish an improvement over the baseline solver.

## 1. Why test a repair with another agent's tests?

A scientific bug can concern behavior outside the example in the task description. For example, a numerical correction might work at one resolution but fail after a unit conversion or a change of coordinates. A useful additional test would state an expected relationship and execute the program to check it. If the relationship fails, the agent receives a concrete error to investigate.

SWE-bench Science evaluates this problem across 119 tasks from 98 repositories in 20 scientific domains. Its agents can use public checks while working; private scientific checks assess the submitted repair. The authors identify failures including superficial repair and limited generalization beyond observed cases. [Xu et al., 2026](https://arxiv.org/abs/2608.19799) This motivates our question: **can model-written tests help repair an incorrect answer, or help choose a correct answer from several attempts?**

Prior work already explores both routes. Self-Refine asks a model to critique and revise its own output. [Madaan et al., 2023](https://arxiv.org/abs/2303.17651) Huang et al. show that intrinsic self-correction can fail on reasoning tasks, motivating scrutiny of how feedback is obtained. [Huang et al., 2024](https://arxiv.org/abs/2310.01798) CodeT uses generated tests to choose code solutions. [Chen et al., 2022](https://arxiv.org/abs/2207.10397) CodeMonkeys combines repeated repository-repair attempts, generated tests and a final agent run devoted to selection. [Ehrlich et al., 2025](https://arxiv.org/abs/2501.14723) Kozuchi directly tests multiple repairs with checks collected from other runs. [Bahrami et al., 2026](https://arxiv.org/abs/2608.15579)

**What we adopt and what we investigate.** We adopt the established idea of cross-testing; we do not claim to invent it or to reproduce those complete systems. Our implementation compares using one's own tests for revision with using other attempts' tests for selection on scientific repositories. We ask for checks of scientific behavior, keep their contents unchanged during comparison, exclude a repair's own tests from its selection score, and distinguish failed assertions from execution problems. The contribution is this implementation and its empirical analysis. The principal finding concerns the reliability of generated feedback, rather than a new general selection algorithm.

<!-- PAGEBREAK -->

## 2. How the method handles one task

**Three attempts to solve the same task.** Each attempt has the same task description and its own copy of the repository. The model proposes a code change, then a separate model session reads that answer and writes tests for it. With enough resources, these independent sessions run in parallel. They do not edit a shared repository or see the other answers while writing tests.

This gives three proposed repairs and up to three sets of tests. The controller runs each available set against each repair: up to nine comparisons. These checks run on CPU in clean repository copies. The GPU serves model requests. The same test code is used for every repair so that the comparison does not change its criteria midway.

**A: improve the same answer with its own tests.** When an answer fails its own executable checks, the model receives the failures and can revise that answer once. The original tests are run again. A revision is kept only if the observed results improve without breaking previously passing checks. If all own checks pass, the workflow keeps the answer. Missing or invalid tests also leave the answer unchanged. A produces one final answer for each of the three initial attempts.

**B: choose an answer using the other attempts' tests.** For answer 1, the controller uses tests written for answers 2 and 3; it excludes answer 1's own tests. Each usable set casts one vote: all checks pass, or at least one assertion fails. The highest average vote wins. A set is usable for selection only if it detects a failure in the original unfixed program and otherwise runs without technical errors there. Execution problems on a proposed repair, such as a timeout or import error, provide no vote for that comparison. This is a fixed scoring rule, with no model acting as a judge.

B prefers answers that pass the public test and uses a uniform random choice to resolve ties. If no usable test evidence exists, it chooses randomly among public-passing answers. B selects among the three initial repairs; A's revised answers are assessed separately. Hidden benchmark results are used only after these decisions, to measure correctness.

**How many repetitions?** There are three repair attempts for each task, three own-test evaluations for A, and one selection decision for B. Repeating the entire three-attempt workflow would be a new repetition of B; this study has one such comparison per task.

## 3. Tasks, execution and comparison

We evaluate nine Python repositories: 001 (reaction chemistry), 007 (MR spectroscopy), 008 (plasma), 017 (gamma-ray astronomy), 024 (probabilistic computing), 039 (Earth-surface dynamics), 053 (medical imaging), 094 (magnetic symmetry), and 107 (computer algebra). From an existing 12-task panel we exclude expensive task 033, native C++ task 004 pending build validation, and 014, which duplicates the repository and base commit of the cheaper 008. All other eligible tasks remain, including difficult tasks with no successful repair. Earlier outcomes were already visible; this is an exploratory subset.

For this comparison, we use three repairs the model had already produced and generate new tests for them. Eight tasks use two ordinary baseline attempts and one earlier self-verification attempt; 094 uses three baseline attempts. Selection follows baseline-first and then stored trial order, keeping distinct code changes without using correctness labels. Reusing intermediate results is not itself a methodological problem. The relevant limitation is that the original repair prompts and budgets differ, so this is not an equal-cost comparison of complete solvers.

New test generation uses Qwen3.8-27B, xhigh reasoning, Codex 0.154.0 and Pier 0.3.0, with four parallel model endpoints and separate task containers. Limits are 30 minutes to write tests, 15 minutes for one revision and 60 seconds per test. The verification run took 3 h 5 min; recorded usage is 64.87M input tokens (63.06M cached) and 1.79M output tokens, excluding earlier repair generation.

<!-- PAGEBREAK -->

## 4. What was solved?

An answer **solves the task** when it passes the benchmark's required hidden checks and receives official binary score 1. Passing the visible example alone does not count. In Table 1, **S = solved** and **F = failed**. Positions show the individual attempts in their recorded order; the fraction counts successful attempts.

**Table 1. Results of each baseline and A attempt, and B's selection outcome.** B has one choice per task. “Tie: 1 of 2 answers correct” means its shortlist contains one correct and one incorrect answer, with equal chance of choosing either. “Solved” means every answer left in the shortlist solves the task; “Failed” means none does.

| Task | Baseline attempts; solved | A: own tests; solved | B: cross-testing outcome |
| --- | --- | --- | --- |
| 001 | F, F; 0/2 | F, F, F; 0/3 | Failed |
| 007 | F, S; 1/2 | F, S, F; 1/3 | Tie: 1 of 2 answers correct |
| 008 | F, F; 0/2 | F, F, F; 0/3 | Failed |
| 017 | S, S; 2/2 | S, S, S; 3/3 | Solved |
| 024 | S, S; 2/2 | S, S, S; 3/3 | Solved |
| 039 | F, F; 0/2 | F, F, F; 0/3 | Failed |
| 053 | S, S; 2/2 | S, S, F; 2/3 | Solved |
| 094 | F, F, F; 0/3 | F, F, F; 0/3 | Failed |
| 107 | S, S; 2/2 | S, S, S; 3/3 | Solved |
| **Total** | **9/19 successful attempts** | **12/27 successful attempts** | **4 solved + 1 tie + 4 failed** |

A's outputs are unchanged from the three starting answers: no test failure triggered revision. The third starting answer came from an earlier self-verification attempt except on 094. Thus 9/19 and 12/27 concern different sets of initial answers; they do not show that A improved the baseline. Both sets contain at least one successful answer on 5 of the 9 tasks.

**Why compare with random choice?** All 27 starting answers pass the public test. That test cannot tell the correct and incorrect answers apart here. The relevant control is therefore simply **choose one of the three answers at random**. It has a 1/3 chance of solving 007 and a 2/3 chance of solving 053. Additional tests are useful for selection if they improve those chances. The code retains a public-pass preference for tasks where it matters, but the public filter changes nothing in this experiment.

**Table 2. Chance that one returned answer solves a task, averaged equally across the nine tasks.** For the baseline and A, average the observed attempt outcomes within each task. For selection, average over equally likely tied choices before averaging tasks.

| Method or reference | Average success rate |
| --- | ---: |
| Original baseline attempts | 50.00% |
| Random choice among the three starting answers | 44.44% |
| A: answer after its own tests | 44.44% |
| B: answer chosen using other attempts' tests | 50.00% |

B has four tasks with only correct shortlisted answers, a half-chance on 007, and four failures. Its **average is 4.5 tasks out of 9**, or 50%; no run actually solved half a task, and no final tie draw was performed. Baseline's raw fraction 9/19 = 47.37% differs from its 50% task average because 094 has one extra attempt. The best possible selector among these answers could solve only 5/9 tasks.

<!-- PAGEBREAK -->

## 5. What do these results tell us?

**Cross-testing contains some useful information.** On 007, it removes one of two wrong answers: random choice improves from a 1/3 to a 1/2 chance of success. On 053, it leaves one correct answer and raises success from 2/3 to 1. The overall gain is 5.56 percentage points. However, the original baseline attempts already score 50% on 007 and 100% on 053. Adding an incorrect third answer lowered the random-choice control; cross-testing restores the original level. We therefore find selection value for these three-answer comparisons, but no demonstrated improvement over the baseline solver.

**Own tests fail to provide a reason to revise.** Nineteen of the 27 attempts produce test sets accepted by our checks, giving 57 test-set/repair comparisons. Twelve of those sets belong to incorrect repairs, and all twelve pass on the answer they were written for. Consequently, A makes zero revision calls and creates no newly solved answers. This measures a weakness of the generated feedback, rather than the model's ability to repair code after a useful counterexample. Seeing the answer while designing tests may encourage agreement with it, but the experiment does not isolate that cause.

Eight outputs fail validation: five lack an explicit Python assertion, and three lack the expected 1–5 entries in the test manifest. These are tool-validation results; some rejected output could still contain useful reasoning or another checking construct. A test set accepted by the tool is also not a proven scientific oracle. On 024 all three sets are unusable, so B falls back to random choice. Its 100% there comes entirely from all three starting answers being correct.

**Where the evidence is limited.** Only 007 and 053 contain a mixture of correct and incorrect answers. Four tasks have no correct answer to select, and three have only correct answers. Nine tasks with one three-answer comparison each give limited evidence about generalization. Results from repeated tests on the same repairs are correlated. Removing the development task 017 gives 37.50% for random choice and 43.75% for both B and the original baseline, preserving the same conclusion.

Generated checks may encode incorrect scientific expectations. A caught library error can be re-raised as an assertion, so failure categories do not establish test validity. Excluding own votes does not remove errors shared by the model across attempts. Also, the implementation uploads other repairs before any possible A revision; a future isolated A comparison should revise first or use a fresh container. No revision took place here. B's reported outcomes use existing official scores for the shortlisted answers, with an unresolved tie on 007.

**Next step.** Use one repair-generation protocol for all three attempts, repeat whole tasks, and give baseline, A and B the same total inference allowance. This must include all repair generation, test writing and revision calls. A should receive only its own answer and test feedback; B should return one answer after a declared tie rule. This would test whether either strategy improves complete task solving for its cost.

## 6. Reproduction and conclusion

README_v3 provides one study entry point that runs the required steps and produces the same result tables and per-attempt records. The supplied artifacts allow the completed numbers to be reconstructed without model calls. The same entry point can generate new tests, evaluate the repairs and build a new report; it reuses the supplied repairs, as in the reported comparison. A fresh full-solver experiment is the next study, not a reinterpretation of these results.

The cross-testing principle follows earlier work. Our scientific-repair implementation shows both a modest selection benefit and a stronger negative finding: model-written tests repeatedly accept an incorrect answer without triggering self-refinement. Improving the reliability of that feedback, and measuring selection against an equally funded baseline, are the questions left open by this experiment.

**AI disclosure.** The evaluated model is Qwen3.8-27B. Codex and Cursor assisted implementation; Codex assisted analysis, literature checking and report drafting. All numerical results are backed by the completed nine-task artifacts.

<!-- PAGEBREAK -->

## References


1. Zhipeng Xu, Jiahao Lu, Yining Zheng, Yuxin Wang, and Xipeng Qiu. **SWE-bench Science: Can Coding Agents Resolve Engineering Tasks in Science?** 2026. [arXiv:2608.19799](https://arxiv.org/abs/2608.19799). Dataset: [OpenMOSS-Team/SWE-bench-Science](https://huggingface.co/datasets/OpenMOSS-Team/SWE-bench-Science).

2. Aman Madaan et al. **Self-Refine: Iterative Refinement with Self-Feedback.** 2023. [arXiv:2303.17651](https://arxiv.org/abs/2303.17651).

3. Jie Huang et al. **Large Language Models Cannot Self-Correct Reasoning Yet.** ICLR 2024. [arXiv:2310.01798](https://arxiv.org/abs/2310.01798).

4. Bei Chen, Fengji Zhang, Anh Nguyen, Daoguang Zan, Zeqi Lin, Jian-Guang Lou, and Weizhu Chen. **CodeT: Code Generation with Generated Tests.** 2022. [arXiv:2207.10397](https://arxiv.org/abs/2207.10397).

5. Ryan Ehrlich, Bradley Brown, Jordan Juravsky, Ronald Clark, Christopher Ré, and Azalia Mirhoseini. **CodeMonkeys: Scaling Test-Time Compute for Software Engineering.** 2025. [arXiv:2501.14723](https://arxiv.org/abs/2501.14723).

6. Mehdi Bahrami et al. **Kozuchi Agent: A Language-Agnostic Open-Weight Agent for Software Repair.** 2026. [arXiv:2608.15579](https://arxiv.org/abs/2608.15579).
