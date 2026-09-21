# Local job search

Read `job-tracker/RUNBOOK.md` before collection or evidence review and
`CONTRIBUTING.md` before shared changes. Resolve paths from this checkout.

- Use `.venv/bin/python3`; no external Python packages are required.
- Preserve `job-tracker/data/state.json`, review history, reporting ledger and application status.
- Use tracker commands for imports, reviews and publication so locking and backups apply. Never bypass an active lock.
- Refresh with `.venv/bin/python3 run.py refresh --no-open`; render with `.venv/bin/python3 run.py open --no-open`.
- The search targets the requested analyst/product titles in the United States, 2–5 years required experience, full-time employee work, and employer-stated USD annual base reaching $100,000.
- Only a current employer JD can support qualification. Preserve evidence source, short quote, and check time. Old India-policy reviews require a new policy review and cannot qualify.
- Sponsorship silence is eligible only with a prominent “Not stated / needs confirmation” label; never infer sponsorship from boilerplate.
- The scheduled evidence-review task performs open-web discovery and review. Collection alone is not a verification run and must not publish fabricated matches.
- Do not submit applications, message people, create accounts, buy services, or alter synced upstream reference files.
- Keep caches, credentials, local setup, logs and backups out of commits.
