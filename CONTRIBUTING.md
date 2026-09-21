# Contributing

Use this repository for tracker improvements and evidence-backed job discoveries. Preserve the salary, location, experience, freshness and contract rules in the runbook.

## Code changes

1. Pull the latest `main` before starting, with a clean working tree.
2. Create a branch describing the change.
3. Make a focused change and run `.venv/bin/python3 run.py check --no-open`.
4. Push the branch and open a pull request explaining the change and validation.

Do not force-push or discard another person's changes. Review the staged diff before committing.

## Jobs and evidence

- Add discoveries to a new JSON array under `job-tracker/data/imports/`, named with the date and your handle or topic.
- Add reviews under `job-tracker/data/reviews/` using the same naming convention. Use `job-tracker/data/seed-reviews.json` as the schema reference.
- Include the original employer URL and separate evidence for salary, geography, experience, employment and freshness. Record missing facts honestly.
- Preserve aliases when replacing an aggregator URL with the employer's original so history is merged.
- Use the import/review commands in the README. Do not edit `state.json` directly.

Dheeraj's installation is the current owner of the shared state snapshot. To avoid competing daily snapshots, collaborators should normally submit new import/review files; the owner can apply them to the latest state and regenerate reports. If you run a local collection to investigate, avoid including unrelated state/report changes in a code pull request.

Generated reports contain dates and source failures. A successful fetch alone does not prove active hiring. Do not change a role to Ready until every required check passes.

## Local-only files

Keep credentials, `.venv`, source-response caches, logs, machine setup, lock files and backups out of commits. The tracked job data is for this private collaboration; do not republish it as a public dataset.

Do not submit applications, contact recruiters or create accounts through the tracker.
