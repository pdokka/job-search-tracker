# Local job search

This is Dheeraj's job tracker project. Read `job-tracker/RUNBOOK.md` before
collection or evidence review and `CONTRIBUTING.md` before shared changes.
Resolve paths from this checkout. Dheeraj's scheduled installation remains
`/Users/dheeraj/Job Search`; a collaborator's clone may be anywhere.

- Use `.venv/bin/python3`; no external Python packages are required.
- Keep `data/state.json`, review history and application status intact.
- Use the tracker import/review commands for state updates so locking and
  backups apply. Do not bypass an active process lock.
- Refresh sources with `.venv/bin/python3 run.py refresh --no-open`.
- Regenerate readable results after reviews with
  `.venv/bin/python3 run.py open --no-open`.
- The scheduled Codex task handles open-web discovery and evidence review.
  A collector run alone must not be reported as a full verification run.
- Do not submit applications, message people, create accounts or buy services.
- Do not change synced reference files in the original ChatGPT project.
- Dheeraj's installation owns the shared state snapshot. Collaborators should
  normally contribute dated import/review files instead of competing snapshots.
- Keep caches, credentials, local setup, logs and backups out of Git commits.
