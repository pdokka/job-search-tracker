#!/usr/bin/env python3
"""Local launcher. Collection is automatic; evidence review runs in Codex."""
import argparse
import datetime as dt
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent
TRACKER = ROOT / 'job-tracker'

def results():
    state = json.loads((TRACKER/'data/state.json').read_text())
    jobs = list(state['jobs'].values())
    reviewed = [j for j in jobs if j.get('review')]
    ready = [j for j in reviewed if j['queue'] == 'Ready']
    caution = [j for j in reviewed if j['queue'] == 'Caution ₹17–20L']
    last = state.get('last_refresh')
    local = dt.datetime.fromisoformat(last).astimezone().strftime('%d %B %Y, %I:%M %p %Z') if last else 'Not yet run'
    lines = ['DHEERAJ’S JOB TRACKER', '', 'Last collection: ' + local,
             f'{len(ready)} Ready | {len(caution)} Caution | {len(reviewed)} reviewed | {len(jobs)} collected leads', '',
             'Target: Hyderabad or verified India remote; 1–2 years; base above ₹20L.',
             'Caution floor: ₹17L. Remote contracts must be at least 12 months.', '',
             'A collection run finds leads. Codex verifies pay, eligibility and freshness during the daily review.',
             'Collected leads are not qualified jobs. The daily review is scheduled for 9am India time.', '',
             'READY TO CONSIDER', '=================']
    if not ready:
        lines += ['No role currently clears every check. See the reviewed leads below.', '']
    order = {'Ready': 0, 'Caution ₹17–20L': 1, 'Needs verification': 2, 'Below floor / negotiate': 3, 'Excluded': 4, 'Closed': 5}
    ordered = sorted(reviewed, key=lambda j: (order.get(j['queue'], 6), j['company'].casefold(), j['title']))
    pending_header = False
    for j in ordered:
        r = j['review']
        if j['queue'] != 'Ready' and not pending_header:
            lines += ['', 'OTHER REVIEWED LEADS', '====================']
            pending_header = True
        lines += ['', j['company'] + ' — ' + j['title'], 'Status: ' + j['queue'], 'Job: ' + j['url']]
        if r.get('pay_min') is not None:
            amount = f"{r.get('currency', '')} {r['pay_min']:,.0f}"
            if r.get('pay_max') and r['pay_max'] != r['pay_min']:
                amount += f"–{r['pay_max']:,.0f}"
            lines.append('Published pay: ' + amount + '/' + r.get('period', 'unknown'))
        for label, key in [('Pay evidence', 'pay'), ('Location', 'location'), ('Experience', 'experience'), ('Freshness', 'freshness')]:
            lines.append(label + ': ' + r['evidence'][key])
        if j.get('reasons'):
            lines.append('Missing / failed checks: ' + '; '.join(j['reasons']))
        if r.get('notes'):
            lines.append('Note: ' + r['notes'])
    lines += ['', 'SOURCE COVERAGE', '===============']
    for h in state.get('health', []):
        outcome = h.get('error') or ('More pages remain' if h.get('more_pages') else 'Available response collected')
        lines.append(f"{h['source']}: {h['rows']} rows. {outcome}")
    scanned = {h['source'] for h in state.get('health', [])}
    for key, b in state.get('boards', {}).items():
        if b.get('error') and key not in scanned:
            lines.append(f"{key}: Earlier failure awaiting recheck; not scanned in this pass. {b['error']} (last attempt: {b.get('last_checked', 'unknown')}).")
    crawl = state.get('discovery_health', {})
    lines += [f"Employer-link checks: {crawl.get('inspected', 0)} inspected; {crawl.get('errors', 0)} could not be fetched.",
              '', 'No applications have been submitted by this tracker.',
              'Full evidence and source history: ' + str(TRACKER/'TRACKER.md'), '']
    target = ROOT/'Latest Results.txt'
    temp = target.with_suffix('.txt.tmp')
    temp.write_text('\n'.join(lines), encoding='utf-8')
    temp.replace(target)
    return target

def main():
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['refresh', 'open', 'check'])
    p.add_argument('--no-open', action='store_true')
    args = p.parse_args()
    (ROOT/'logs').mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime('%Y-%m-%d_%H-%M-%S_%f')
    log_path = ROOT/'logs'/(args.action+'-'+stamp+'.log')
    if args.action == 'check':
        command = [sys.executable, '-m', 'unittest', 'discover', '-s', str(TRACKER), '-p', 'test_*.py']
    else:
        command = [sys.executable, str(TRACKER/'tracker.py'), 'refresh' if args.action == 'refresh' else 'render']
    if args.action == 'refresh':
        print('Collecting public job sources. This can take a few minutes.', flush=True)
        print('Salary and eligibility verification also runs in the scheduled Codex review.', flush=True)
    with log_path.open('w', encoding='utf-8') as log:
        child = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')
        try:
            for line in child.stdout:
                print(line, end='', flush=True)
                log.write(line)
                log.flush()
            code = child.wait()
        except KeyboardInterrupt:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
            print('\nStopped. The last saved results remain available.')
            return 130
    if code:
        print('The run did not finish. Details: ' + str(log_path))
        return code
    if args.action != 'check':
        target = results()
        print('Results: ' + str(target))
        if not args.no_open:
            subprocess.run(['/usr/bin/open', '-a', 'TextEdit', str(target)], check=True)
    print('Run log: ' + str(log_path))
    return 0

if __name__ == '__main__':
    sys.exit(main())
