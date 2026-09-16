# Retrospective cross-candidate audit

No model calls or test re-execution. Selection reads an allowlist of observations; recorded hidden rewards are joined only after decisions are frozen.

Tasks: 8; candidates: 76; suites: 21; cells: 280.

| Policy | Task-macro expected reward |
|---|---:|
| random | 29.85% |
| public_random | 30.68% |
| first_public | 37.50% |
| cross_vote | 41.15% |
| cross_baseline_split | 41.15% |
| cross_baseline_split_assertion_only | 36.98% |
| vote_including_self | 39.58% |
| oracle pool ceiling (uses hidden labels) | 50.00% |

| Task | Correct / candidates | Public random | First public | Cross vote | Strict sensitivity |
|---|---:|---:|---:|---:|---:|
| 001 | 0 / 12 | 0.00% | 0.00% | 0.00% | 0.00% |
| 004 | 6 / 10 | 66.67% | 100.00% | 62.50% | 62.50% |
| 007 | 2 / 6 | 33.33% | 0.00% | 66.67% | 33.33% |
| 008 | 0 / 12 | 0.00% | 0.00% | 0.00% | 0.00% |
| 017 | 5 / 11 | 45.45% | 100.00% | 100.00% | 100.00% |
| 024 | 5 / 5 | 100.00% | 100.00% | 100.00% | 100.00% |
| 039 | 0 / 5 | 0.00% | 0.00% | 0.00% | 0.00% |
| 094 | 0 / 15 | 0.00% | 0.00% | 0.00% | 0.00% |

Ties use uniform expected reward, not a realised selected patch. First-public follows matrix insertion order; it is an order sensitivity baseline. Unknown cells do not vote.

The strict policy makes a whole suite unknown if any failing test is not classified as an assertion. This is not automatically a better validity rule: task 007 includes TypeErrors inside project source which may be the real defect. The optimistic and strict policies agree on every task except 007.

This pool combines historical pipelines, versions, and budgets. Trials are not necessarily independent or distinct source patches. Donor suites may have been adapted to donor patches. The eight tasks are development data already inspected; these are exploratory results. Cells and suites are correlated, not 280 independent evaluation examples.

The legacy select.json calibrates each suite using hidden rewards of other candidates of the SAME task. Its score is diagnostic rather than a deployable test-task policy. Here the same headline value can be obtained without that calibration, using cross_vote. This post-hoc reproduction does not establish a held-out improvement.

Input matrix SHA256: `701f1a8f9d2504d6f20d23515ff3c36972d1e68d7722d8254b452689bf0141b9`.
