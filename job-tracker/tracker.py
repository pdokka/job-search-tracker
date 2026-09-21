#!/usr/bin/env python3
"""Personal job discovery. Public feeds collect leads; evidence reviews qualify jobs.

No dependencies, private API keys, logins, applications, or outbound messages.
Run: python3 tracker.py refresh | render | baseline | publish | queries | import FILE | review FILE
"""
import argparse
import concurrent.futures
import copy
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
UA = 'DheerajJobTracker/2.0 (personal job research; daily refresh)'
POLICY_VERSION = 'us-analyst-product-v1'
TARGET_TITLES = (
    'Business Analyst', 'Data Analyst', 'Systems Analyst',
    'Business Systems Analyst', 'Product Owner', 'Product Analyst',
    'Associate Product Manager', 'Product Manager', 'Financial Analyst',
    'Business Intelligence Analyst',
)
HIMALAYAS_US_FEEDS = {
    'himalayas_us_' + re.sub(r'\W+', '_', title.casefold()).strip('_'):
        'https://himalayas.app/jobs/api/search?country=US&q=' + up.quote(title) + '&sort=recent&page=1'
    for title in TARGET_TITLES
}
FEEDS = {
    'remotive': 'https://remotive.com/api/remote-jobs',
    'remoteok': 'https://remoteok.com/api',
    'arbeitnow': 'https://www.arbeitnow.com/api/job-board-api',
    'jobicy': 'https://jobicy.com/api/v2/remote-jobs?count=100',
    'himalayas': 'https://himalayas.app/jobs/api?limit=20',
    'wwr': 'https://weworkremotely.com/remote-jobs.rss',
    **HIMALAYAS_US_FEEDS,
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
    """Return whether a title is one of the requested roles.

    The historical function name is retained because saved collection code and
    collaborators import it. Senior/lead variants are excluded. "Manager" is
    not a generic negative because Product Manager is itself a target title.
    """
    normalized = re.sub(r'[^a-z0-9]+', ' ', str(title or '').casefold()).strip()
    if re.search(r'\b(?:senior|sr|lead|principal|staff|director|head|vp|vice president)\b', normalized):
        return False
    targets = tuple(re.sub(r'[^a-z0-9]+', ' ', t.casefold()).strip() for t in TARGET_TITLES)
    return any(re.search(r'(?<![a-z0-9])' + re.escape(target) + r'(?![a-z0-9])', normalized)
               for target in targets)

def hints(job):
    text = job.get('text', '')
    loc = job.get('location', '')
    years = re.findall(r'.{0,45}\b[0-9]+(?:\s*[-–]\s*[0-9]+)?\+?\s*(?:years|yrs).{0,80}', text, re.I)
    money = re.findall(r'.{0,45}(?:₹|\$|€|£|\bINR\b|\bUSD\b|\bLPA\b|salary|compensation|base pay).{0,150}', text, re.I)
    score = 0
    if re.search(r'\b(?:united states|u\.?s\.?a?|us)\b', loc, re.I): score += 6
    elif re.search(r'remote', loc, re.I): score += 1
    elif loc: score -= 8
    if re.search(r'\b[2-5](?:\s*[-–]\s*[2-5])?\+?\s*(years|yrs)', text + ' ' + job['title'], re.I): score += 4
    advertised = job.get('advertised_pay')
    numeric_pay = bool(re.search(r'[$₹€£]\s*[\d,.]+|\b\d[\d,.]*\s*(?:LPA|lakhs?|USD|INR)', text, re.I))
    if isinstance(advertised, dict): numeric_pay |= bool(advertised.get('min') or advertised.get('max'))
    elif advertised: numeric_pay |= bool(re.search(r'\d', str(advertised)))
    if numeric_pay: score += 3
    if re.search(r'\b(?:senior|sr|lead|principal|staff|director)\b', job['title'], re.I): score -= 8
    if re.search(r'\b(?:6|[7-9]|\d{2,})\+? years', text, re.I): score -= 2
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
    required = ('url', 'checked_at', 'evidence_url', 'evidence', 'page_state',
                'policy_version', 'evidence_source', 'title_fit', 'location_fit', 'experience_fit',
                'experience_min', 'experience_max', 'employment', 'full_time',
                'pay_kind', 'pay_min', 'pay_max', 'currency', 'period',
                'employer_posted', 'sponsorship_status', 'quotes')
    for k in required:
        if k not in r: raise ValueError('Review missing ' + k)
    canonical(r['url']); canonical(r['evidence_url'])
    if r['pay_min'] is not None and (r['pay_min'] < 0 or r['pay_max'] is not None and r['pay_min'] > r['pay_max']):
        raise ValueError('Invalid salary range')
    if r['policy_version'] != POLICY_VERSION:
        raise ValueError('Review policy_version must be ' + POLICY_VERSION)
    if r['evidence_source'] != 'employer_jd':
        raise ValueError('Every qualification dimension must use the current employer JD')
    if r['sponsorship_status'] not in ('offered', 'not_stated', 'conditional', 'not_offered', 'restricted'):
        raise ValueError('Invalid sponsorship_status')
    if r['sponsorship_status'] == 'conditional' and not r.get('sponsorship_conditions'):
        raise ValueError('Conditional sponsorship requires sponsorship_conditions')
    if r['employment'] not in ('employee', 'permanent', 'contract', 'temporary', 'internship', 'part_time', 'unknown'):
        raise ValueError('Invalid employment')
    if r['currency'] not in ('USD', None):
        raise ValueError('US policy reviews must use USD or null currency')
    if r['pay_kind'] not in ('base', 'salary_unsplit', 'total_comp', 'unknown'):
        raise ValueError('Invalid pay_kind')
    for k in ('title', 'pay', 'location', 'experience', 'freshness', 'employment', 'sponsorship'):
        if not r['evidence'].get(k): raise ValueError('Missing evidence explanation: ' + k)
    if sum(len(x.split()) for x in r.get('quotes', {}).values()) > 25:
        raise ValueError('Use short exact excerpts (25 words maximum per posting); paraphrase evidence')
    if not any(str(x).strip() for x in r['quotes'].values()):
        raise ValueError('Preserve at least one short exact excerpt from the current employer JD')

def classify(job, today=None):
    r = job.get('review') or {}
    if job.get('check', {}).get('state') == 'closed' or r.get('page_state') == 'closed':
        return 'Closed', ['Employer posting explicitly closed or removed']
    if not r: return 'Needs verification', ['Unreviewed discovery; salary, country and experience are not yet evidence']
    reasons = []
    if r.get('policy_version') != POLICY_VERSION:
        return 'Needs verification', ['Review predates the current US analyst/product policy; new employer-JD evidence is required']
    if r.get('evidence_source') != 'employer_jd':
        return 'Needs verification', ['Current employer JD evidence is required for every qualification dimension']
    if age(r.get('checked_at'), today) > 7 or r.get('needs_recheck'): reasons.append('Evidence needs a fresh check')
    if age(job.get('check', {}).get('checked_at'), today) <= 2 and job.get('check', {}).get('state') in ('blocked', 'error'):
        reasons.append('Current page could not be verified')
    if r.get('page_state') != 'open': reasons.append('Active application page unconfirmed')
    if not software(job.get('title', '')) or r.get('title_fit') is False:
        return 'Excluded', ['Title is outside the requested analyst/product roles or is senior/lead']
    if r.get('title_fit') is not True: reasons.append('Requested title fit is unconfirmed')
    if r.get('location_fit') is False:
        return 'Excluded', ['Role is not explicitly eligible in the United States']
    if r.get('location_fit') is not True: reasons.append('Explicit United States eligibility is unconfirmed')
    if r.get('experience_fit') is False:
        return 'Excluded', ['Required experience is outside the accepted 2–5 year range']
    exp_min, exp_max = r.get('experience_min'), r.get('experience_max')
    if (r.get('experience_fit') is not True or not isinstance(exp_min, (int, float))
            or not 2 <= exp_min <= 5 or (exp_max is not None and exp_max > 5)):
        reasons.append('Employer JD must establish required experience in the accepted 2–5 year range')
    fresh = 0 <= age(r.get('employer_posted'), today) <= 30
    if not fresh: reasons.append('No employer-JD posting date within 30 days')
    if r.get('employment') not in ('permanent', 'employee') or r.get('full_time') is not True:
        return 'Excluded', ['Only full-time employee roles qualify; contract/temp/internship/part-time does not']
    if r.get('sponsorship_status') in ('not_offered', 'restricted'):
        return 'Excluded', ['Current JD excludes candidates needing current/future sponsorship or requires unrestricted status']
    if r.get('sponsorship_status') not in ('offered', 'not_stated', 'conditional'):
        reasons.append('Current JD sponsorship status is unconfirmed')
    if r.get('pay_kind') != 'base': reasons.append('Annual base salary is not established by the employer JD')
    annual_min = r.get('pay_min') if r.get('currency') == 'USD' and r.get('period') == 'year' else None
    annual_max = r.get('pay_max') if annual_min is not None else None
    if annual_min is None or annual_max is None:
        reasons.append('USD annual base salary range is undisclosed or incomplete')
    elif annual_max < 100_000:
        return 'Below $100k base', reasons + ['Advertised maximum annual base is below $100,000']
    if reasons: return 'Needs verification', reasons
    return ('Ready' if annual_min >= 100_000 else 'Caution: range crosses $100k'), []

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
        if name.startswith('himalayas_us_'):
            paths = [(start.replace('page=1','page='+str(n)),1) for n in range(1,4)]
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
    print('Stored target-role leads:', len(state['jobs']), 'discovered boards:', len(state['boards']), flush=True)

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
    print('HN target-role announcements:',count,'error:',health['error'],flush=True)
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
    role = TARGET_TITLES[day % len(TARGET_TITLES)]
    base = [f'"{title}" "United States" "base salary"' for title in TARGET_TITLES]
    base += [f'"{role}" remote USA sponsorship', f'"{role}" hybrid USA "$100,000"']
    for i in range(4): base.append(f'site:{hosts[(day*4+i)%len(hosts)]} "{role}" "United States"')
    return base

def pay_label(job):
    r = job.get('review') or {}
    if r.get('pay_min') is None: return 'Not verified'
    kind={'base':'base','salary_unsplit':'base split unconfirmed','total_comp':'total compensation','unknown':'unverified'}.get(r['pay_kind'],r['pay_kind'])
    return f"{r['currency']} {r['pay_min']:,.0f}" + (f"–{r['pay_max']:,.0f}" if r.get('pay_max') and r['pay_max'] != r['pay_min'] else '') + '/' + r['period'] + ' (' + kind + ')'

def cell(value): return str(value or 'Unknown').replace('|','/').replace('\n',' ')

QUALIFYING_QUEUES = ('Ready', 'Caution: range crosses $100k')

def posted_value(job):
    return (job.get('review') or {}).get('employer_posted')

def qualifying_jobs(state):
    jobs = [j for j in state['jobs'].values() if j.get('queue') in QUALIFYING_QUEUES]
    return sorted(jobs, key=lambda j: (posted_value(j) is None,
                                       -(date(posted_value(j)).timestamp() if date(posted_value(j)) else 0),
                                       j.get('company', '').casefold(), j.get('title', '').casefold()))

def sponsorship_label(review):
    labels = {
        'offered': 'Offered', 'not_stated': 'Not stated / needs confirmation',
        'conditional': 'Conditional', 'not_offered': 'Not offered',
        'restricted': 'Restricted authorization required',
    }
    label = labels.get(review.get('sponsorship_status'), 'Unknown')
    condition = review.get('sponsorship_conditions')
    return label + (': ' + str(condition) if condition else '')

def qualifying_table(jobs):
    lines = ['| Title / company | US location | Employer posted | Annual base salary | Required experience | Sponsorship + current JD evidence |',
             '|---|---|---|---|---|---|']
    for j in jobs:
        r = j['review']
        salary = pay_label(j)
        if j.get('queue') == 'Caution: range crosses $100k':
            salary += ' — **Caution: lower end below $100k**'
        sponsor = sponsorship_label(r) + ' — ' + cell(r['evidence']['sponsorship'])
        posted = r.get('employer_posted') or '**Unknown — does not qualify**'
        link = r.get('evidence_url') or j['url']
        lines.append(f"| [{cell(j['title'])} — {cell(j['company'])}]({link}) | {cell(r['evidence']['location'])} | {cell(posted)} | {salary} | {cell(r['evidence']['experience'])} | {cell(sponsor)} |")
    return lines

def report_keys(job):
    urls = [job.get('url')] + list(job.get('aliases', []))
    return {job['id']} | {identity(url) for url in urls if url}

def publish_report(state, baseline=False, day=None):
    """Atomically publish a baseline or new-only daily report, then advance its ledger."""
    day = day or dt.datetime.now(UTC).strftime('%Y-%m-%d')
    reporting = state.setdefault('reporting', {'reported_keys': [], 'publications': {}})
    reported = set(reporting.get('reported_keys', []))
    all_jobs = qualifying_jobs(state)
    jobs = all_jobs if baseline else [j for j in all_jobs if report_keys(j).isdisjoint(reported)]
    key = 'baseline' if baseline else day
    directory = DATA / 'reports'
    target = directory / ('BASELINE.md' if baseline else day + '.md')
    publication = reporting.get('publications', {}).get(key, {})
    if baseline and publication and target.exists():
        return target
    previous_ids = publication.get('ids', [])
    if previous_ids:
        previous = {j['id']: j for j in publication.get('jobs', [])}
        previous.update({j['id']: j for j in all_jobs
                         if j['id'] in previous_ids and j['id'] not in previous})
        previous.update({j['id']: j for j in jobs})
        jobs = sorted(previous.values(), key=lambda j: (posted_value(j) is None,
                      -(date(posted_value(j)).timestamp() if date(posted_value(j)) else 0),
                      j.get('company', '').casefold()))
    heading = '# Initial qualifying-job baseline' if baseline else '# New qualifying jobs — ' + day
    lines = [heading, '', 'Published: ' + publication.get('published_at', now()), '',
             '**Evidence-reviewed matches: ' + str(len(jobs)) + '.**', '']
    if not baseline:
        shortfall = max(0, 15 - len(jobs))
        lines += [f'New-match target: 15. Honest shortfall: {shortfall}. No unsuitable or previously reported jobs were used as filler.', '']
    lines += qualifying_table(jobs) if jobs else ['No qualifying jobs were available for this publication.', '']
    lines += ['', 'Qualification requires a current employer JD. Sponsorship silence is labeled “Not stated / needs confirmation”; it is not treated as an offer.', '']
    directory.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + '.tmp')
    temp.write_text('\n'.join(lines), encoding='utf-8')
    temp.replace(target)
    # The ledger advances only after the publication has been atomically replaced.
    published_keys = set().union(*(report_keys(j) for j in jobs)) if jobs else set()
    reporting['reported_keys'] = sorted(reported | published_keys)
    reporting.setdefault('publications', {})[key] = {
        'published_at': publication.get('published_at', now()), 'path': str(target.relative_to(ROOT)),
        'ids': [j['id'] for j in jobs], 'count': len(jobs), 'baseline': baseline,
        'jobs': [copy.deepcopy({k: j[k] for k in ('id', 'company', 'title', 'url', 'aliases', 'review', 'queue') if k in j}) for j in jobs],
    }
    return target

def review_candidates(state):
    candidates = []
    for job in state['jobs'].values():
        if job.get('queue') != 'Needs verification' or not software(job.get('title', '')):
            continue
        job['hints'] = hints(job)
        candidates.append(job)
    return sorted(candidates, key=lambda j: (j['hints']['score'],
                  j.get('first_seen', '')), reverse=True)

def render(state):
    groups = {}
    events = state.setdefault('events', [])
    for j in state['jobs'].values():
        group, reasons = classify(j)
        if j.get('queue') != group and (j.get('queue') in QUALIFYING_QUEUES or group in QUALIFYING_QUEUES + ('Closed',)):
            events.append({'at':now(),'id':j['id'],'from':j.get('queue'),'to':group,'reasons':reasons})
        j['queue'] = group; j['reasons'] = reasons
        groups.setdefault(group, []).append(j)
    eligible = groups.get('Ready', []) + groups.get('Caution: range crosses $100k', [])
    lines = ['# Daily job tracker', '', 'Last collection: ' + state.get('last_refresh','Not run'), '', '**Target:** requested analyst/product titles; United States eligible; JD requires 2–5 years; full-time employee; employer-posted USD annual base range reaches at least $100,000.', '', 'A disclosed range crossing $100,000 qualifies with a prominent caution. Current employer-JD evidence and a posting date within 30 days are required. Sponsorship silence remains “Not stated / needs confirmation,” never an inferred offer.', '', f"**{len(groups.get('Ready', []))} ready · {len(groups.get('Caution: range crosses $100k', []))} crossing-range caution · {len(state['jobs'])} retained leads (including legacy history) · {len(state['boards'])} discovered employer boards.** Collected leads are not qualifying jobs.", '']
    lines += ['## Application queue', '']
    if not eligible: lines += ['No role currently clears every evidence gate. See reviewed leads below; missing evidence is not filled with assumptions.', '']
    for group in QUALIFYING_QUEUES:
        rows = [j for j in qualifying_jobs(state) if j.get('queue') == group]
        if not rows: continue
        lines += ['### ' + group, ''] + qualifying_table(rows)
        lines += ['']
    lines += ['## Previously reviewed leads', '', '| Job | Published pay | Employer posted | Status / missing evidence |', '|---|---|---|---|']
    for j in sorted(state['jobs'].values(), key=lambda j:j['company']):
        if j.get('review') and j['queue'] not in QUALIFYING_QUEUES:
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
    lines += ['', '## Discovery sources', '', 'Source links are retained with every lead. Feed data must be traced to the current employer JD before qualification. [Remotive](https://remotive.com), [Remote OK](https://remoteok.com), [Arbeitnow](https://www.arbeitnow.com), [Jobicy](https://jobicy.com), US title searches from [Himalayas](https://himalayas.app), [We Work Remotely](https://weworkremotely.com), and the current Hacker News hiring thread.', '', 'The separate scheduled evidence-review task runs the rotating discovery queries and checks original application routes. It does not submit applications or message employers.', '']
    searchlog = read(DATA/'search-log.json',[])
    lines += ['## Open-web discovery audit', '', f'{len(searchlog)} queries recorded. Last query: ' + (searchlog[-1]['checked_at'] if searchlog else 'Not yet recorded'), '', 'Queries and source failures are retained in data/search-log.json; searched does not mean exhaustive coverage.', '']
    (ROOT/'TRACKER.md').write_text('\n'.join(lines))
    master = ['# Master qualifying jobs', '', 'All currently qualifying jobs, including sponsorship-unstated matches labeled honestly.', '']
    master += qualifying_table(qualifying_jobs(state)) if eligible else ['No current job clears every evidence gate.', '']
    master += ['', 'Closure and material queue changes remain in `data/state.json` events and are not mixed into new-only daily reports.', '']
    (ROOT/'MASTER-QUALIFYING.md').write_text('\n'.join(master), encoding='utf-8')
    changes = ['# Closure and material changes', '',
               'Queue transitions are kept separately from baseline and new-match reports.', '',
               '| Changed at | Job | From | To | Notes |', '|---|---|---|---|---|']
    for event in reversed(events):
        job = state['jobs'].get(event.get('id'), {})
        changes.append(f"| {cell(event.get('at'))} | [{cell(job.get('title') or event.get('id'))}]({job.get('url', '')}) | {cell(event.get('from'))} | {cell(event.get('to'))} | {cell('; '.join(event.get('reasons', [])))} |")
    (ROOT/'CHANGES.md').write_text('\n'.join(changes) + '\n', encoding='utf-8')
    pending = review_candidates(state)
    write(DATA/'review-queue.json', [{k:v for k,v in j.items() if k != 'text'} for j in pending[:200]])
    stamp = dt.datetime.now(UTC).strftime('%Y-%m-%d')
    write(DATA/'daily'/f'{stamp}.json', {'generated_at':now(),'qualifying_ids':[j['id'] for j in eligible], 'counts':{k:len(v) for k,v in groups.items()}, 'health':state.get('health',[])})
    (ROOT/'DISCOVERY-QUERIES.md').write_text('# Today’s discovery queries\n\nRun these through web search with a 30-day preference, then open original postings. Record failures and unproductive searches too. No employer allowlist. A recency search filter is not proof of posting date.\n\n'+'\n'.join('- '+q for q in queries())+'\n')

def main():
    p = argparse.ArgumentParser(); p.add_argument('command', choices=['refresh','community','expand','render','baseline','publish','queries','import','review']); p.add_argument('file',nargs='?'); a=p.parse_args()
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
    render(state)
    if a.command == 'baseline': print('Baseline:', publish_report(state, baseline=True))
    if a.command == 'publish': print('Daily report:', publish_report(state))
    write(DATA/'state.json',state)
    print('Tracker:', ROOT/'TRACKER.md')

if __name__ == '__main__': main()
