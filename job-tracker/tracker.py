#!/usr/bin/env python3
"""Personal job discovery. Public feeds collect leads; evidence reviews qualify jobs.

No dependencies, private API keys, logins, applications, or outbound messages.
Run: python3 tracker.py refresh | render | queries | import FILE | review FILE
"""
import argparse
import concurrent.futures
import datetime as dt
import email.utils
import fcntl
import gzip
import hashlib
import html
import json
import ipaddress
import pathlib
import re
import time
import socket
import urllib.error
import urllib.parse as up
import urllib.request as ur
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent
DATA = ROOT / 'data'
UTC = dt.timezone.utc
UA = 'DheerajJobTracker/1.0 (personal job research; daily refresh)'
FEEDS = {
    'remotive': 'https://remotive.com/api/remote-jobs',
    'remoteok': 'https://remoteok.com/api',
    'arbeitnow': 'https://www.arbeitnow.com/api/job-board-api',
    'jobicy': 'https://jobicy.com/api/v2/remote-jobs?count=100',
    'himalayas': 'https://himalayas.app/jobs/api?limit=20',
    'himalayas_india': 'https://himalayas.app/jobs/api/search?country=IN&q=engineer&sort=recent&page=1',
    'himalayas_junior': 'https://himalayas.app/jobs/api/search?country=IN&seniority=Entry-level&q=developer&page=1',
    'wwr': 'https://weworkremotely.com/remote-jobs.rss',
}

def now():
    return dt.datetime.now(UTC).isoformat(timespec='seconds')

def date(value):
    if not value:
        return None
    try:
        if isinstance(value, (int, float)):
            return dt.datetime.fromtimestamp(value / (1000 if value > 1e12 else 1), UTC)
        return dt.datetime.fromisoformat(str(value).replace('Z', '+00:00')).replace(tzinfo=UTC) if not re.search(r'[+-]\d\d:\d\d$', str(value)) else dt.datetime.fromisoformat(str(value))
    except (ValueError, TypeError):
        try:
            return email.utils.parsedate_to_datetime(value).astimezone(UTC)
        except (ValueError, TypeError):
            return None

def age(value, today=None):
    d = date(value)
    return ((today or dt.datetime.now(UTC)) - d).total_seconds() / 86400 if d else 99999

def read(path, default):
    return json.loads(path.read_text()) if path.exists() else default

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    temp.replace(path)

def plain(value):
    value = html.unescape(html.unescape(str(value or '')))
    value = re.sub(r'<(script|style)\b[^>]*>.*?</\1>', '', value, flags=re.I | re.S)
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', value)).strip()

def canonical(url):
    p = up.urlsplit(html.unescape(url or ''))
    if p.scheme not in ('http', 'https') or not p.netloc:
        raise ValueError('An absolute public job URL is required')
    keep = [(k, v) for k, v in up.parse_qsl(p.query) if not k.lower().startswith(('utm_', 'ref_', 'source')) and k.lower() not in ('ref', 'referrer', 'src', 'gh_src')]
    host = p.netloc.lower()
    if host in ('boards.greenhouse.io', 'job-job-boards.greenhouse.io'):
        host = 'job-boards.greenhouse.io'
    return up.urlunsplit(('https', host, p.path.rstrip('/'), up.urlencode(sorted(keep)), ''))

def identity(url):
    url = canonical(url)
    p = up.urlsplit(url)
    gid = up.parse_qs(p.query).get('gh_jid')
    if gid:
        return 'greenhouse:' + gid[0]
    m = re.search(r'/(?:jobs|positions)/(\d+)', p.path)
    if m and ('greenhouse.io' in p.netloc or 'coinbase.com' in p.netloc):
        return 'greenhouse:' + m[1]
    if p.netloc in ('jobs.ashbyhq.com', 'jobs.lever.co', 'jobs.eu.lever.co'):
        return p.netloc + ':' + p.path.strip('/').removesuffix('/application')
    return hashlib.sha256(url.encode()).hexdigest()[:24]

def fetch(url, cache_key=None):
    parsed = up.urlsplit(url)
    if parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username:
        raise ValueError('Only public web URLs are fetched')
    for address in socket.getaddrinfo(parsed.hostname, parsed.port or 443):
        if not ipaddress.ip_address(address[4][0]).is_global:
            raise ValueError('Private network destination refused')
    cache = DATA / 'cache' / ((cache_key or hashlib.sha256(url.encode()).hexdigest()) + '.json')
    saved = read(cache, {})
    if saved.get('url') == url and time.time() - saved.get('fetched', 0) < 20 * 3600:
        return saved['body'], saved.get('final_url', url), True
    request = ur.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json,text/html,application/rss+xml,*/*'})
    with ur.urlopen(request, timeout=20) as response:
        body = response.read(12_000_000).decode('utf-8', errors='replace')
        final = response.url
    write(cache, {'url': url, 'final_url': final, 'fetched': time.time(), 'body': body})
    return body, final, False

def linked_boards(text):
    text = html.unescape(str(text)).replace('\\/', '/')
    patterns = [('greenhouse', r'https?://(?:job-boards|boards)\.greenhouse\.io/([\w-]+)'),
                ('ashby', r'https?://jobs\.ashbyhq\.com/([\w.-]+)'),
                ('lever', r'https?://jobs\.lever\.co/([\w.-]+)')]
    return {(kind, slug) for kind, pattern in patterns for slug in re.findall(pattern, text)}

def software(title):
    return bool(re.search(r'engineer|developer|programmer|\bsde\b|\bsre\b|devops|data scientist|quality assurance|\bqa\b', title, re.I))

def hints(job):
    text = job.get('text', '')
    loc = job.get('location', '')
    years = re.findall(r'.{0,45}\b[0-9]+(?:\s*[-–]\s*[0-9]+)?\+?\s*(?:years|yrs).{0,80}', text, re.I)
    money = re.findall(r'.{0,45}(?:₹|\$|€|£|\bINR\b|\bUSD\b|\bLPA\b|salary|compensation|base pay).{0,150}', text, re.I)
    score = 0
    if re.search(r'hyderabad|\bindia\b|worldwide|anywhere|global|apac', loc, re.I): score += 6
    elif re.search(r'remote', loc, re.I): score += 1
    elif loc: score -= 8
    if re.search(r'\b[012](?:\s*[-–]\s*\d+)?\+?\s*(years|yrs)|junior|early career|new grad', text + ' ' + job['title'], re.I): score += 4
    advertised = job.get('advertised_pay')
    numeric_pay = bool(re.search(r'[$₹€£]\s*[\d,.]+|\b\d[\d,.]*\s*(?:LPA|lakhs?|USD|INR)', text, re.I))
    if isinstance(advertised, dict): numeric_pay |= bool(advertised.get('min') or advertised.get('max'))
    elif advertised: numeric_pay |= bool(re.search(r'\d', str(advertised)))
    if numeric_pay: score += 3
    if re.search(r'principal|staff|director|manager', job['title'], re.I): score -= 8
    if re.search(r'\b[5-9]\+? years', text, re.I): score -= 2
    return {'score': score, 'experience_clues': years[:8], 'salary_clues': money[:8]}

def record(company, title, url, location='', text='', posted=None, **kw):
    return dict(company=plain(company), title=plain(title), url=url, location=plain(location), text=plain(text), source_posted=posted, **kw)

def parse_feed(name, body):
    if name.startswith('himalayas'): name = 'himalayas'
    jobs = []
    if name == 'wwr':
        for j in ET.fromstring(body).findall('.//item'):
            title = j.findtext('title', '')
            co, _, role = title.partition(': ')
            jobs.append(record(co, role or title, j.findtext('link'), 'Remote; country eligibility unverified', j.findtext('description'), j.findtext('pubDate')))
        return jobs, None, None
    data = json.loads(body)
    if name == 'remotive':
        for j in data['jobs']:
            jobs.append(record(j['company_name'], j['title'], j['url'], j.get('candidate_required_location'), j.get('description'), j.get('publication_date'), advertised_pay=j.get('salary'), employment_type=j.get('job_type')))
        return jobs, None, data.get('total-job-count')
    if name == 'remoteok':
        for j in data:
            if not j.get('position'): continue
            jobs.append(record(j['company'], j['position'], j['url'], j.get('location'), j.get('description'), j.get('date'), application_url=j.get('apply_url'), advertised_pay={'min': j.get('salary_min'), 'max': j.get('salary_max'), 'currency': 'unverified'}))
        return jobs, None, None
    if name == 'arbeitnow':
        for j in data['data']:
            jobs.append(record(j['company_name'], j['title'], j['url'], j.get('location'), j.get('description'), j.get('created_at'), remote=j.get('remote')))
        return jobs, data.get('links', {}).get('next'), data.get('meta', {}).get('total')
    if name == 'jobicy':
        for j in data['jobs']:
            jobs.append(record(j['companyName'], j['jobTitle'], j['url'], j.get('jobGeo'), j.get('jobDescription'), j.get('pubDate'), advertised_pay={k:v for k,v in j.items() if k.startswith('salary')}))
        return jobs, None, None
    if name == 'himalayas':
        for j in data['jobs']:
            loc = ', '.join(x.get('name', '') if isinstance(x, dict) else x for x in j.get('locationRestrictions', [])) or 'Worldwide (feed claim)'
            jobs.append(record(j['companyName'], j['title'], j.get('applicationLink') or j['guid'], loc, j.get('description'), j.get('pubDate'), attribution_url=j['guid'], employment_type=j.get('employmentType'), advertised_pay={'min':j.get('minSalary'), 'max':j.get('maxSalary'), 'currency':j.get('currency'), 'period':j.get('salaryPeriod')}))
        cursor = data.get('nextCursor')
        return jobs, ('https://himalayas.app/jobs/api?limit=20&cursor=' + up.quote(cursor)) if cursor else None, data.get('totalCount')
    raise ValueError(name)

def board_jobs(kind, slug):
    if kind == 'greenhouse':
        url = f'https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true'
    elif kind == 'ashby':
        url = f'https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true'
    else:
        url = f'https://api.lever.co/v0/postings/{slug}?mode=json'
    body, _, cached = fetch(url)
    data = json.loads(body)
    rows = data if kind == 'lever' else data['jobs']
    out = []
    for j in rows:
        if kind == 'greenhouse':
            out.append(record(slug, j['title'], j['absolute_url'], j.get('location', {}).get('name'), j.get('content'), None, source_modified=j.get('updated_at')))
        elif kind == 'ashby':
            out.append(record(slug, j['title'], j['jobUrl'], j.get('location'), j.get('descriptionPlain'), j.get('publishedAt'), advertised_pay=j.get('compensation'), employer_posted=j.get('publishedAt')))
        else:
            out.append(record(slug, j['text'], j['hostedUrl'], j.get('categories', {}).get('location'), j.get('descriptionPlain', '') + ' ' + j.get('additionalPlain', '') + ' ' + json.dumps(j.get('lists', [])), None, advertised_pay=j.get('salaryRange')))
    return out, url, cached

def merge(state, job, source, stamp):
    if not job.get('url') or not software(job.get('title', '')): return None
    job['url'] = canonical(job['url'])
    key = identity(job['url'])
    # A feed may return an alias again after we found the employer's original.
    # Keep its provenance without replacing reviewed employer facts or status.
    if not source.startswith(('employer:', 'manual:')):
        owner_key = next((k for k, j in state['jobs'].items()
                          if k != key and any(identity(a) == key for a in j.get('aliases', []))), None)
        if owner_key:
            previous = state['jobs'].pop(key, {})
            owner = state['jobs'][owner_key]
            owner = {**previous, **owner,
                     'sources': {**previous.get('sources', {}), **owner.get('sources', {})},
                     'first_seen': min(previous.get('first_seen', owner['first_seen']), owner['first_seen']),
                     'last_seen': stamp}
            owner['sources'][source] = {'last_seen': stamp,
                                        'url': job.get('attribution_url') or job['url'],
                                        'posted': job.get('source_posted')}
            state['jobs'][owner_key] = owner
            return owner_key
    old = state['jobs'].get(key, {})
    for alias in job.get('aliases', []):
        alias_key = identity(alias)
        if alias_key != key and alias_key in state['jobs']:
            previous = state['jobs'].pop(alias_key)
            old = {**previous, **old, 'sources':{**previous.get('sources',{}),**old.get('sources',{})}, 'first_seen':min(previous['first_seen'],old.get('first_seen',previous['first_seen']))}
    origins = old.get('sources', {})
    origins[source] = {'last_seen': stamp, 'url': job.get('attribution_url') or job['url'], 'posted': job.get('source_posted')}
    digest = hashlib.sha256(job.get('text', '').encode()).hexdigest()
    review = old.get('review')
    # Changes never silently preserve a previous qualification.
    if review and old.get('text_hash') and old['text_hash'] != digest and source.startswith('employer:'):
        review['needs_recheck'] = True
    new = {**old, **job, 'id': key, 'first_seen': old.get('first_seen', stamp), 'last_seen': stamp, 'sources': origins, 'text_hash': digest, 'review': review}
    if source.startswith('employer:'):
        new['last_employer_seen'] = stamp
    new['hints'] = hints(new)
    state['jobs'][key] = new
    for kind, slug in linked_boards(job.get('url', '') + ' ' + str(job.get('application_url', '')) + ' ' + job.get('text', '')):
        state['boards'].setdefault(kind + ':' + slug, {'kind': kind, 'slug': slug, 'discovered_from': job['url'], 'first_seen': stamp})
    return key

def validate_review(r):
    required = ('url', 'checked_at', 'evidence_url', 'evidence', 'page_state', 'location_fit', 'experience_fit', 'employment', 'pay_kind', 'pay_min', 'pay_max', 'currency', 'period')
    for k in required:
        if k not in r: raise ValueError('Review missing ' + k)
    canonical(r['url']); canonical(r['evidence_url'])
    if r['pay_min'] is not None and (r['pay_min'] < 0 or r['pay_max'] is not None and r['pay_min'] > r['pay_max']):
        raise ValueError('Invalid salary range')
    for k in ('pay', 'location', 'experience', 'freshness', 'employment'):
        if not r['evidence'].get(k): raise ValueError('Missing evidence explanation: ' + k)
    if sum(len(x.split()) for x in r.get('quotes', {}).values()) > 25:
        raise ValueError('Use short exact excerpts (25 words maximum per posting); paraphrase evidence')

def classify(job, today=None):
    r = job.get('review') or {}
    if job.get('check', {}).get('state') == 'closed' or r.get('page_state') == 'closed':
        return 'Closed', ['Employer posting explicitly closed or removed']
    if not r: return 'Needs verification', ['Unreviewed discovery; salary, country and experience are not yet evidence']
    reasons = []
    if age(r.get('checked_at'), today) > 7 or r.get('needs_recheck'): reasons.append('Evidence needs a fresh check')
    if age(job.get('check', {}).get('checked_at'), today) <= 2 and job.get('check', {}).get('state') in ('blocked', 'error'):
        reasons.append('Current page could not be verified')
    if r.get('page_state') != 'open': reasons.append('Active application page unconfirmed')
    if r.get('location_fit') is False or r.get('experience_fit') is False:
        return 'Excluded', ['Location or required experience does not fit']
    if r.get('location_fit') is not True: reasons.append('India eligibility or Hyderabad location unconfirmed')
    if r.get('experience_fit') is not True: reasons.append('1–2-year eligibility unconfirmed')
    fresh = 0 <= age(r.get('employer_posted'), today) <= 30
    active = 0 <= age(r.get('active_signal_date'), today) <= 30 and bool(r.get('active_signal_url'))
    if not (fresh or active): reasons.append('No employer posting date or dated hiring signal within 30 days')
    if r.get('employment') == 'contract':
        if not r.get('remote_confirmed') or (r.get('contract_months') or 0) < 12:
            reasons.append('Remote contract of at least 12 months unconfirmed')
    elif r.get('employment') not in ('permanent','employee'): reasons.append('Employment type unconfirmed')
    if r.get('pay_kind') not in ('base', 'guaranteed_cash'): reasons.append('Guaranteed base/cash is not established by the posting')
    if r.get('pay_applies_to_india') is not True: reasons.append('Published salary applicability to India unconfirmed')
    annual = None
    if r.get('pay_min') is not None and r.get('period') in ('year', 'month'):
        fx = 1 if r.get('currency') == 'INR' else r.get('fx_rate')
        if r.get('currency') != 'INR' and (not fx or age(r.get('fx_date'), today) > 7 or not r.get('fx_source')):
            reasons.append('Fresh currency conversion missing')
        elif fx:
            annual = r['pay_min'] * fx * (12 if r['period'] == 'month' else 1)
    else: reasons.append('No annual/monthly guaranteed salary floor; hourly rates are not annual base')
    if annual is not None and annual < 1_700_000:
        return 'Below floor / negotiate', reasons + ['Advertised minimum is below ₹17L; upper range is not an offer']
    if reasons: return 'Needs verification', reasons
    if annual is None: return 'Needs verification', ['Annual pay cannot be calculated']
    return ('Ready' if annual > 2_000_000 else 'Caution ₹17–20L'), []

def check_job(job):
    stamp = now()
    url = job.get('review', {}).get('evidence_url') if job.get('review') else job['url']
    try:
        body, final, cached = fetch(url)
        text = plain(body)
        closed = bool(re.search(r'job (?:is no longer|has been filled|has expired)|no longer accepting applications|position (?:has been filled|is closed)|opening is no longer available', text, re.I))
        blocked = bool(re.search(r'just a moment|verify you are human|access denied|enable javascript to run this app', text, re.I)) or len(text) < 100
        return {'checked_at':stamp, 'state':'closed' if closed else 'blocked' if blocked else 'reachable', 'final_url':final, 'cached':cached, 'note':'Reachability alone does not prove active hiring', 'content_hash':hashlib.sha256(text.encode()).hexdigest()}
    except urllib.error.HTTPError as e:
        return {'checked_at':stamp, 'state':'closed' if e.code in (404,410) else 'blocked' if e.code in (401,403,429) else 'error', 'note':str(e)}
    except Exception as e:
        return {'checked_at':stamp, 'state':'error', 'note':str(e)}

def refresh(state):
    stamp = now(); health = []; before = set(state['jobs']); discovered_before = set(state['boards'])
    for name, start in FEEDS.items():
        count = 0; pages = 0; total = None; cached_count = 0; error = None
        # Latest pages every day plus a persistent backfill walk: no claim of full coverage.
        paths = [(start, 8 if name == 'himalayas' else 3 if name == 'arbeitnow' else 1)]
        if name in ('himalayas_india','himalayas_junior'):
            paths = [(start.replace('page=1','page='+str(n)),1) for n in range(1,6)]
        if name == 'himalayas' and state.get('himalayas_backfill'):
            paths.append((state['himalayas_backfill'], 12))
        next_url = None
        try:
            visited = set()
            for url, budget in paths:
                for page in range(budget):
                    if not url or url in visited: break
                    visited.add(url)
                    body, _, cached = fetch(url, name if url == start else None)
                    rows, next_url, total = parse_feed(name, body)
                    pages += 1; count += len(rows); cached_count += int(cached)
                    # Discover boards from source HTML before stripping links.
                    for kind, slug in linked_boards(body):
                        state['boards'].setdefault(kind + ':' + slug, {'kind':kind, 'slug':slug, 'discovered_from':url, 'first_seen':stamp})
                    for job in rows: merge(state, job, name, stamp)
                    url = next_url
                    if url: time.sleep(.3)
            if name == 'himalayas': state['himalayas_backfill'] = next_url
        except Exception as e: error = str(e)
        health.append({'source':name, 'checked_at':stamp, 'pages':pages, 'rows':count, 'reported_total':total, 'more_pages':bool(next_url) or (isinstance(total,(int,float)) and count < total), 'cached_pages':cached_count, 'error':error})
        print(name, 'rows:', count, 'error:', error, flush=True)
    health.append(community(state))
    expand(state, limit=20)
    # Dynamically discovered registry, not a hardcoded company allowlist.
    boards = sorted(state['boards'].items(), key=lambda x:x[1].get('last_checked',''))[:40]
    def scan(item):
        key, b = item
        try: return key, board_jobs(b['kind'], b['slug']), None
        except Exception as e: return key, None, str(e)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for key, result, error in pool.map(scan, boards):
            b = state['boards'][key]; b['last_checked'] = stamp; b['error'] = error
            rows, url, cached = result if result else ([], '', False)
            for job in rows: merge(state, job, 'employer:' + key, stamp)
            health.append({'source':key, 'checked_at':stamp, 'rows':len(rows), 'cached_pages':int(cached), 'error':error})
    reviewed = [j for j in state['jobs'].values() if j.get('review') and j['review'].get('page_state') != 'closed']
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for job, result in zip(reviewed, pool.map(check_job, reviewed)):
            if job.get('check',{}).get('content_hash') and result.get('content_hash') and job['check']['content_hash'] != result['content_hash']:
                job['review']['needs_recheck'] = True
            job['check'] = result
    state['last_refresh'] = stamp
    state['health'] = health
    state['runs'].append({'at':stamp, 'new_jobs':len(set(state['jobs']) - before), 'new_boards':len(set(state['boards'])-discovered_before), 'sources':health})
    print('Stored software leads:', len(state['jobs']), 'discovered boards:', len(state['boards']), flush=True)

def community(state):
    stamp=now(); count=0
    health={'source':'Hacker News hiring announcements','checked_at':stamp,'rows':0,'pages':0,'error':None}
    try:
        endpoint='https://hn.algolia.com/api/v1/search_by_date?query=Ask%20HN%3A%20Who%20is%20hiring%3F&tags=story&hitsPerPage=10'
        results=json.loads(fetch(endpoint)[0])
        story=next(j for j in results['hits'] if re.match(r'^Ask HN: Who is hiring\? \(',j['title']) and age(j['created_at'])<=45)
        data=json.loads(fetch('https://hn.algolia.com/api/v1/items/'+story['objectID'])[0])
        for j in data.get('children',[]):
            raw=j.get('text') or ''; text=plain(raw)
            if not software(text): continue
            first=re.split(r'<p>|\n',raw,flags=re.I)[0]
            title=plain(first)[:180]
            company=re.split(r'\s*[|•]\s*',title)[0][:65]
            role=title if software(title) else 'Engineering hiring — '+title
            url='https://news.ycombinator.com/item?id='+str(j['id'])
            for kind,slug in linked_boards(raw):
                state['boards'].setdefault(kind+':'+slug,{'kind':kind,'slug':slug,'first_seen':stamp,'discovered_from':url})
            merge(state,record(company,role,url,title,text,j.get('created_at'),announcement=True),'hn-who-is-hiring',stamp)
            count+=1
        health.update(rows=count,pages=1,thread_url='https://news.ycombinator.com/item?id='+story['objectID'])
    except Exception as e: health['error']=str(e)
    print('HN engineering announcements:',count,'error:',health['error'],flush=True)
    return health

def expand(state, limit=30):
    """Inspect promising source pages for employer links; never submit an application."""
    candidates = sorted((j for j in state['jobs'].values() if j['hints']['score'] >= 4 and age(j.get('discovery_checked')) >= 7), key=lambda j:j['hints']['score'], reverse=True)[:limit]
    def inspect(job):
        try:
            body, final, _ = fetch(job['url'])
            boards = linked_boards(body + ' ' + final)
            urls = []
            for link, label in re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', body, re.I|re.S):
                label = plain(label)
                target = up.urljoin(final, html.unescape(link))
                if re.search(r'apply|company website|employer|careers',label,re.I) and up.urlsplit(target).scheme in ('http','https'):
                    urls.append({'url':target,'label':label[:100]})
            return boards, urls[:15], None
        except Exception as e: return set(), [], str(e)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for job, (boards, urls, error) in zip(candidates, pool.map(inspect,candidates)):
            job['discovery_checked']=now();job['employer_link_candidates']=urls;job['discovery_error']=error
            for kind,slug in boards:
                state['boards'].setdefault(kind+':'+slug,{'kind':kind,'slug':slug,'first_seen':now(),'discovered_from':job['url']})
    errors = sum(bool(j.get('discovery_error')) for j in candidates)
    state['discovery_health'] = {'checked_at':now(),'inspected':len(candidates),'errors':errors}
    print('Inspected discovery pages:',len(candidates),'failed:',errors,flush=True)

def queries():
    day = dt.datetime.now(UTC).timetuple().tm_yday
    hosts = ['jobs.ashbyhq.com', 'job-boards.greenhouse.io', 'jobs.lever.co', 'apply.workable.com', 'teamtailor.com', 'freshteam.com', 'careers-page.com', 'wellfound.com/jobs', 'ycombinator.com/companies', 'cutshort.io/job', 'linkedin.com/jobs/view', 'indeed.com/viewjob', 'builtin.com/job', 'remoterocketship.com', 'himalayas.app', 'news.ycombinator.com']
    role = ['software engineer', 'backend engineer', 'frontend developer', 'full stack engineer', 'integration engineer', 'AI engineer', 'QA automation engineer'][day % 7]
    base = [f'"{role}" "remote" "India" salary', f'"{role}" "worldwide" salary', '"engineer" "Hyderabad" "salary" "2 years"', '"developer" "Hyderabad" "LPA" "1 year"', '"engineer" "work from anywhere" "compensation"', '"developer" "same pay" remote', '"engineer" "location independent" salary', '"engineer" "remote" "India" "12 months" salary']
    for i in range(8): base.append(f'site:{hosts[(day*8+i)%len(hosts)]} "{role}" remote')
    return base

def pay_label(job):
    r = job.get('review') or {}
    if r.get('pay_min') is None: return 'Not verified'
    kind={'base':'base','guaranteed_cash':'fixed cash','salary_unsplit':'base split unconfirmed','ctc':'CTC','unknown':'unverified'}.get(r['pay_kind'],r['pay_kind'])
    return f"{r['currency']} {r['pay_min']:,.0f}" + (f"–{r['pay_max']:,.0f}" if r.get('pay_max') and r['pay_max'] != r['pay_min'] else '') + '/' + r['period'] + ' (' + kind + ')'

def cell(value): return str(value or 'Unknown').replace('|','/').replace('\n',' ')

def render(state):
    groups = {}
    events = state.setdefault('events', [])
    for j in state['jobs'].values():
        group, reasons = classify(j)
        if j.get('queue') != group and (j.get('queue') in ('Ready','Caution ₹17–20L') or group in ('Ready','Caution ₹17–20L','Closed')):
            events.append({'at':now(),'id':j['id'],'from':j.get('queue'),'to':group,'reasons':reasons})
        j['queue'] = group; j['reasons'] = reasons
        groups.setdefault(group, []).append(j)
    eligible = groups.get('Ready', []) + groups.get('Caution ₹17–20L', [])
    lines = ['# Daily job tracker', '', 'Last collection: ' + state.get('last_refresh','Not run'), '', '**Main target:** >₹20L annual guaranteed base. **Caution:** ₹17–20L. Hyderabad or verified remote from India; 1–2 years. Remote contracts require documented duration of at least 12 months.', '', 'Fresh means an employer posting date within 30 days or a dated employer/recruiter hiring signal within 30 days. First discovery, aggregator repost dates, page edits and a working Apply button do not reset the age.', '', f"**{len(groups.get('Ready', []))} ready · {len(groups.get('Caution ₹17–20L', []))} caution · {len(state['jobs'])} collected software leads · {len(state['boards'])} discovered employer boards.** Collected leads are not qualifying jobs.", '']
    lines += ['## Application queue', '']
    if not eligible: lines += ['No role currently clears every evidence gate. See reviewed leads below; missing evidence is not filled with assumptions.', '']
    for group in ('Ready','Caution ₹17–20L'):
        rows = groups.get(group, [])
        if not rows: continue
        lines += ['### ' + group, '', '| Job | Published pay | Experience evidence | Location | Employer posted / hiring signal |', '|---|---|---|---|---|']
        for j in rows:
            r=j['review']
            lines.append(f"| [{cell(j['company'])} — {cell(j['title'])}]({j['url']}) | {pay_label(j)} | {cell(r['evidence']['experience'])} | {cell(j['location'])} | {cell(r.get('employer_posted') or r.get('active_signal_date'))} |")
        lines += ['']
    lines += ['## Previously reviewed leads', '', '| Job | Published pay | Employer posted | Status / missing evidence |', '|---|---|---|---|']
    for j in sorted(state['jobs'].values(), key=lambda j:j['company']):
        if j.get('review') and j['queue'] not in ('Ready','Caution ₹17–20L'):
            lines.append(f"| [{cell(j['company'])} — {cell(j['title'])}]({j['url']}) | {pay_label(j)} | {cell(j['review'].get('employer_posted'))} | {j['queue']}: {cell('; '.join(j['reasons']))} |")
    lines += ['', '## Coverage and failures', '', 'Public feeds have different coverage, delays and page limits. Counts include irrelevant geographies and seniorities. Discovery continues beyond the employers already found.', '', '| Source | Rows fetched | Pages | Outcome |', '|---|---|---|---|']
    for h in state.get('health', []):
        status = h.get('error') or ('Partial: further pages remain' if h.get('more_pages') else 'Fetched available response; not a whole-internet census')
        lines.append(f"| {h['source']} | {h['rows']} | {h.get('pages',1)} | {cell(status)} |")
    scanned = {h['source'] for h in state.get('health', [])}
    outstanding = [(key, b) for key, b in state.get('boards', {}).items()
                   if b.get('error') and key not in scanned]
    if outstanding:
        lines += ['', 'Earlier employer-board failures awaiting recheck (not scanned in this pass):', '']
        for key, b in outstanding:
            lines.append(f"- {key}: {b['error']} (last attempt: {b.get('last_checked', 'unknown')}).")
    crawl = state.get('discovery_health',{})
    lines += ['', f"Employer-link discovery: {crawl.get('inspected',0)} pages inspected; {crawl.get('errors',0)} could not be fetched. Blocked pages require another public source or browser verification."]
    lines += ['', '## Discovery sources', '', 'Source links are retained with every lead. Feed data must be traced to the employer before qualification. [Remotive](https://remotive.com), [Remote OK](https://remoteok.com), [Arbeitnow](https://www.arbeitnow.com), [Jobicy](https://jobicy.com), [Himalayas](https://himalayas.app), [We Work Remotely](https://weworkremotely.com), and the current Hacker News hiring thread.', '', 'The scheduled review also runs the rotating discovery queries and checks original application routes. It does not submit applications or message employers.', '']
    searchlog = read(DATA/'search-log.json',[])
    lines += ['## Open-web discovery audit', '', f'{len(searchlog)} queries recorded. Last query: ' + (searchlog[-1]['checked_at'] if searchlog else 'Not yet recorded'), '', 'Queries and source failures are retained in data/search-log.json; searched does not mean exhaustive coverage.', '']
    (ROOT/'TRACKER.md').write_text('\n'.join(lines))
    pending = sorted((j for j in state['jobs'].values() if j['queue']=='Needs verification'), key=lambda j:(bool(j.get('review')),j['hints']['score'],j['first_seen']), reverse=True)
    write(DATA/'review-queue.json', [{k:v for k,v in j.items() if k != 'text'} for j in pending[:200]])
    stamp = dt.datetime.now(UTC).strftime('%Y-%m-%d')
    write(DATA/'daily'/f'{stamp}.json', {'generated_at':now(),'ready_ids':[j['id'] for j in eligible], 'counts':{k:len(v) for k,v in groups.items()}, 'health':state.get('health',[])})
    (ROOT/'DISCOVERY-QUERIES.md').write_text('# Today’s discovery queries\n\nRun these through web search with a 30-day preference, then open original postings. Record failures and unproductive searches too. No employer allowlist. A recency search filter is not proof of posting date.\n\n'+'\n'.join('- '+q for q in queries())+'\n')

def main():
    p = argparse.ArgumentParser(); p.add_argument('command', choices=['refresh','community','expand','render','queries','import','review']); p.add_argument('file',nargs='?'); a=p.parse_args()
    if a.command in ('import', 'review') and not a.file:
        p.error('This command requires a JSON file')
    if a.command == 'queries':
        print('\n'.join(queries())); return
    DATA.mkdir(exist_ok=True)
    with (DATA/'.run.lock').open('a+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('The tracker is already running. Please try again when it finishes.')
        if a.command != 'render' and (DATA/'state.json').exists():
            backups = ROOT.parent/'backups'
            backups.mkdir(exist_ok=True)
            target = backups/('state-' + dt.datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ') + '.json.gz')
            with gzip.open(target, 'wb') as backup:
                backup.write((DATA/'state.json').read_bytes())
            for old in sorted(backups.glob('state-*.json.gz'))[:-14]:
                old.unlink()
        execute(a)

def execute(a):
    state = read(DATA/'state.json', {'jobs':{}, 'boards':{}, 'runs':[]})
    if a.command == 'refresh': refresh(state)
    if a.command == 'community': state.setdefault('health',[]).append(community(state))
    if a.command == 'expand': expand(state)
    if a.command == 'import':
        items = read(pathlib.Path(a.file), [])
        for job in items: merge(state, job, job.get('source','web-discovery'), now())
    if a.command == 'review':
        for r in read(pathlib.Path(a.file), []):
            validate_review(r)
            key = identity(r['url'])
            if key not in state['jobs']: raise ValueError('Import job before reviewing: '+r['url'])
            state['jobs'][key]['review'] = r
    render(state); write(DATA/'state.json',state)
    print('Tracker:', ROOT/'TRACKER.md')

if __name__ == '__main__': main()
