Recheck the original review findings against the CURRENT candidate repair.
The files in source/ already contain this candidate; candidate.patch is its
complete diff against the original source. This is a review-only stage.

Inspect the public basis and the actual code path for each finding. Decide
whether the claimed defect is now resolved, unresolved, or uncertain. Do not
assume the earlier reviewer was correct. A passing public fixture alone does
not establish that the finding is resolved. Do not introduce new requirements.

Save selfverify/review/report.json early, updating it as you inspect:
{
  "findings": [
    {"id":"the original finding id", "status":"resolved|unresolved|uncertain",
     "evidence":"specific current code path and public requirement establishing the decision"}
  ]
}
Include every original finding exactly once. Do not modify source/ or task files.
Use focused reads or short diagnostics; do not generate a new test suite.
