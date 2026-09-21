# Contributing

Use this repository for tracker improvements and evidence-backed job discoveries under the current US analyst/product policy in `job-tracker/RUNBOOK.md`.

## Code changes

1. Start from `pdokka/main` on a focused branch.
2. Make a focused change and run `.venv/bin/python3 run.py check --no-open`.
3. Review the staged diff, commit it, and open a pull request into `pdokka/main`.

Do not force-push, merge without review, or discard another person's state.

## Jobs and evidence

- Add discoveries as a dated JSON array under `job-tracker/data/imports/`.
- Add reviews under `job-tracker/data/reviews/`; use `data/seed-reviews.json` as the current schema example.
- Every qualification dimension must be supported by the current original employer JD: requested title, explicit US eligibility, 2–5 year requirement, full-time employee status, USD annual base range, employer posting date, and current sponsorship wording or silence.
- Preserve the evidence URL, check time, paraphrased evidence, and no more than 25 quoted words per posting. Generic EEO/immigration boilerplate is not a sponsorship offer.
- Preserve aliases when replacing an aggregator URL with an employer original so history and the reporting ledger deduplicate correctly.
- Use the import/review commands; do not edit `state.json` directly.

After evidence review, use `baseline` once for the initial snapshot and `publish` for subsequent new-only daily reports. Commit dated import/review/report artifacts and the state ledger together so retries remain idempotent.

## Local-only files

Keep credentials, `.venv`, caches, logs, lock files and backups out of commits. Do not submit applications, contact recruiters, create accounts, or republish the private dataset.
