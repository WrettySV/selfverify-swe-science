# Study artifacts

These files support the published study results summarized in the [repository README](../README.md). Recalculate the tables with `python3 scripts/run_study.py` from the repository root.

| Path | Contents |
|---|---|
| [study/data.json](study/data.json) | Per-task repairs, run identities, test outcomes and usage |
| [study/inputs/](study/inputs/) | Three source patches for each of nine tasks |
| [study/suites/](study/suites/) | Generated Python tests, including rejected outputs |
| [study/selector.py](study/selector.py) | Selection rule used to compute B |
| [study/implementation/](study/implementation/) | Exact implementation used for the recorded verification runs |
| [study/shards/](study/shards/) | Task instructions, execution configuration and image digests |
| [study/checksums.json](study/checksums.json) | File hashes checked before analysis or new verification |
| [grading/](grading/) | Final repair patches and original benchmark grading results for all 27 A runs |
| [baseline_results.json](baseline_results.json) | Three baseline outcomes per task |
| [model_config.json](model_config.json) | Model revision and inference configuration |
| [refinement_audit.json](refinement_audit.json) | Input/output patch hashes and revision records |
| [report_manifest.json](report_manifest.json) | Report metrics and hashes of publication files |
| [scientist_engineer/](scientist_engineer/) | Side comparison: Scientist→Engineer briefs and matched n=2 metrics (REPORT §5 Table 3) |

The `study/` bundle preserves the executed code and observations unchanged. New runs write to a separate output directory; they do not overwrite the published evidence. The baseline table and the A/B patch identities are recorded separately and should not be joined by table position.

Full local execution traces remain in `work/` and `results/`, which are ignored by Git. The bundle contains the evidence needed to reconstruct the published selection results; model weights are referenced by revision rather than stored here.

For Git, include the study bundle, grading files, JSON metadata and this guide. Python caches are ignored. Full traces can be distributed separately; they are not needed to recalculate the tables.
