# Action plan

## Daily collection

The GitHub Actions workflow runs once at 17:00 America/Chicago. It collects public feeds, ten US title searches, Hacker News announcements, and discovered employer boards. Its `cloud-run.json` output reports collection health only; collection does not qualify or publish jobs.

## Separate evidence review

The ChatGPT Work task executes the 16 rotating queries, inspects current original employer JDs, and imports dated discovery/review artifacts. It verifies requested title, explicit US eligibility, required 2–5 years, full-time employee status, USD annual base reaching $100,000, employer-posted freshness within 30 days, and current-JD sponsorship language or silence.

After review it renders the full master report. The first current-policy run uses `run.py baseline --no-open`; subsequent runs use `run.py publish --no-open`. Daily publication includes every new qualifying identity, states any shortfall from 15, and never repeats or pads results.

## Safety

Do not apply, contact anyone, create accounts, buy services, infer missing evidence, or treat EEO boilerplate as a sponsorship offer. Preserve aliases, the reporting ledger, application status, source failures, and historical reviews.
