import copy
import datetime as dt
import unittest
import tracker as t

TODAY = dt.datetime(2026, 9, 18, 12, tzinfo=dt.timezone.utc)

def fixture():
    return {'review': {'checked_at':'2026-09-18', 'page_state':'open', 'location_fit':True,
        'experience_fit':True, 'employer_posted':'2026-09-10', 'employment':'permanent',
        'pay_kind':'base', 'pay_applies_to_india':True, 'pay_min':2100000,
        'pay_max':3000000, 'currency':'INR', 'period':'year'}}

class EligibilityTests(unittest.TestCase):
    def group(self, job): return t.classify(job, TODAY)[0]
    def test_ready(self): self.assertEqual(self.group(fixture()), 'Ready')
    def test_20l_is_caution_not_above20(self):
        j=fixture();j['review']['pay_min']=2000000
        self.assertEqual(self.group(j), 'Caution ₹17–20L')
    def test_17l_floor(self):
        j=fixture();j['review']['pay_min']=1700000
        self.assertEqual(self.group(j), 'Caution ₹17–20L')
    def test_ceiling_does_not_override_floor(self):
        j=fixture();j['review']['pay_min']=1600000
        self.assertEqual(self.group(j), 'Below floor / negotiate')
    def test_old_repost_is_not_fresh(self):
        j=fixture();j['review']['employer_posted']='2026-05-01';j['first_seen']='2026-09-18'
        self.assertEqual(self.group(j), 'Needs verification')
    def test_recent_dated_hiring_signal(self):
        j=fixture();r=j['review'];r['employer_posted']='2026-05-01';r['active_signal_date']='2026-09-17';r['active_signal_url']='https://employer.example/hiring'
        self.assertEqual(self.group(j), 'Ready')
    def test_future_date_does_not_count(self):
        j=fixture();j['review']['employer_posted']='2026-12-01'
        self.assertEqual(self.group(j), 'Needs verification')
    def test_us_salary_not_india_proof(self):
        j=fixture();j['review']['pay_applies_to_india']=False
        self.assertEqual(self.group(j), 'Needs verification')
    def test_salary_is_not_automatically_base(self):
        j=fixture();j['review']['pay_kind']='salary_unsplit'
        self.assertEqual(self.group(j), 'Needs verification')
    def test_contract_requires_12months_remote(self):
        j=fixture();j['review']['employment']='contract';j['review']['remote_confirmed']=True
        self.assertEqual(self.group(j), 'Needs verification')
        j['review']['contract_months']=11
        self.assertEqual(self.group(j), 'Needs verification')
        j['review']['contract_months']=12
        self.assertEqual(self.group(j), 'Ready')
        j['review']['remote_confirmed']=False
        self.assertEqual(self.group(j), 'Needs verification')
    def test_foreign_fx_must_be_recent(self):
        j=fixture();r=j['review'];r.update(currency='USD',pay_min=2000,pay_max=2000,period='month',fx_rate=95.77,fx_date='2026-09-18',fx_source='https://wise.com')
        self.assertEqual(self.group(j), 'Ready')
        r['fx_date']='2026-08-01'
        self.assertEqual(self.group(j), 'Needs verification')
    def test_hourly_not_annualized(self):
        j=fixture();j['review']['period']='hour'
        self.assertEqual(self.group(j), 'Needs verification')
    def test_network_failure_not_closed(self):
        j=fixture();j['check']={'state':'blocked','checked_at':'2026-09-18'}
        self.assertEqual(self.group(j), 'Needs verification')
    def test_confirmed_closed(self):
        j=fixture();j['check']={'state':'closed','checked_at':'2026-09-18'}
        self.assertEqual(self.group(j), 'Closed')
    def test_exp_and_geo_fail(self):
        for key in ('experience_fit','location_fit'):
            j=fixture();j['review'][key]=False
            self.assertEqual(self.group(j),'Excluded')
    def test_senior_title_not_automatic_rejection(self):
        j=fixture();j['title']='Senior Frontend Engineer'
        self.assertEqual(self.group(j),'Ready')
    def test_canonical_dedup(self):
        self.assertEqual(t.identity('https://www.coinbase.com/careers/positions/123?gh_jid=123&utm_source=x'),t.identity('https://boards.greenhouse.io/coinbase/jobs/123'))
        self.assertEqual(t.identity('https://jobs.lever.co/acme/abc/application?source=LinkedIn'),t.identity('https://jobs.lever.co/acme/abc'))
        url='https://job-boards.greenhouse.io/acme/jobs/123'
        self.assertEqual(t.canonical(url),url)
        self.assertEqual(t.canonical(t.canonical(url)),url)
    def test_source_alias_merges_history(self):
        s={'jobs':{},'boards':{}}
        t.merge(s,t.record('Acme','Software Engineer','https://aggregator.example/role'),'feed','2026-08-01')
        j=t.record('Acme','Software Engineer','https://jobs.lever.co/acme/123',aliases=['https://aggregator.example/role'])
        key=t.merge(s,j,'employer:lever:acme','2026-09-18')
        self.assertEqual(len(s['jobs']),1)
        self.assertEqual(s['jobs'][key]['first_seen'],'2026-08-01')
        self.assertIn('feed',s['jobs'][key]['sources'])
    def test_first_seen_preserved(self):
        s={'jobs':{},'boards':{}};j=t.record('Acme','Software Engineer','https://jobs.lever.co/acme/123')
        key=t.merge(s,j,'feed','2026-09-01');t.merge(s,j,'feed','2026-09-18')
        self.assertEqual(s['jobs'][key]['first_seen'],'2026-09-01')
        self.assertIn('lever:acme',s['boards'])
    def test_returning_feed_alias_keeps_original_review_and_application(self):
        s={'jobs':{},'boards':{}}
        alias='https://aggregator.example/role'
        j=t.record('Acme','Software Engineer','https://jobs.lever.co/acme/123',
                   text='Employer facts',aliases=[alias])
        key=t.merge(s,j,'employer:lever:acme','2026-09-18')
        s['jobs'][key].update(review=fixture()['review'],application_status='Applied')
        expected=copy.deepcopy(s['jobs'][key])
        result=t.merge(s,t.record('Acme','Software Engineer',alias,text='Feed repost'),
                       'feed','2026-09-20')
        self.assertEqual(result,key)
        self.assertEqual(len(s['jobs']),1)
        for field in ('text','text_hash','review','application_status','last_employer_seen'):
            self.assertEqual(s['jobs'][key][field],expected[field])
        self.assertEqual(s['jobs'][key]['sources']['feed']['url'],alias)
    def test_returning_alias_repairs_existing_duplicate_and_preserves_history(self):
        s={'jobs':{},'boards':{}}
        alias='https://aggregator.example/role'
        duplicate_key=t.merge(s,t.record('Acme','Software Engineer',alias),'old-feed','2026-08-01')
        duplicate=copy.deepcopy(s['jobs'][duplicate_key])
        key=t.merge(s,t.record('Acme','Software Engineer','https://jobs.lever.co/acme/123',aliases=[alias]),
                    'employer:lever:acme','2026-09-18')
        s['jobs'][duplicate_key]=duplicate
        t.merge(s,t.record('Acme','Software Engineer',alias),'feed','2026-09-20')
        self.assertEqual(len(s['jobs']),1)
        self.assertEqual(s['jobs'][key]['first_seen'],'2026-08-01')
        self.assertIn('old-feed',s['jobs'][key]['sources'])
    def test_salaryless_discovery_retained(self):
        s={'jobs':{},'boards':{}};key=t.merge(s,t.record('New company','Senior Software Engineer','https://example.org/jobs/abc'),'feed','2026-09-18')
        self.assertIsNotNone(key)
        self.assertEqual(self.group(s['jobs'][key]),'Needs verification')

if __name__ == '__main__': unittest.main()
