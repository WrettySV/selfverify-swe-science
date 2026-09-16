# Scientist→Engineer side comparison

Generation-time role split reported in [REPORT.md](../../REPORT.md) §5 Table 3.
Not part of the A/B cross-candidate verification protocol.

| Path | Contents |
|---|---|
| [metrics.json](metrics.json) | Matched n=2 single-agent vs SE means and per-task counts |
| [job_result.json](job_result.json) | Pier job summary for `se3-qwen38-main9-n2` |
| [experiment.json](experiment.json) | Launch metadata |
| [briefs/](briefs/) | Per-task Scientist brief, critic verdict, usage, inventory |

Full Pier trial trees (agent logs, patches, verifiers) remain outside this
bundle; regenerate with `scripts/run_se_experiment.py` if needed.

```bash
# materialize tasks (same nine IDs as selections/verification-python-9.json)
# then:
.venv/bin/python scripts/run_se_experiment.py --condition se \
  --tasks work/tasks-scientist-engineer-9 \
  --env-file model.env \
  --job-name se-rerun \
  --scientist-model Qwen3.8-27B --model Qwen3.8-27B \
  --n-concurrent 8 --n-attempts 2
```
