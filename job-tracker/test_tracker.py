import copy
import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest import mock
import tracker as t

TODAY = dt.datetime(2026, 9, 21, 12, tzinfo=dt.timezone.utc)


def fixture(title='Business Analyst', url='https://jobs.example.com/role'):
    return {
        'id': t.identity(url), 'company': 'Acme', 'title': title, 'url': url,
        'location': 'United States', 'aliases': [],
        'review': {
            'policy_version': t.POLICY_VERSION, 'evidence_source': 'employer_jd',
            'checked_at': '2026-09-21', 'evidence_url': url, 'page_state': 'open',
            'title_fit': True, 'location_fit': True, 'experience_fit': True,
            'experience_min': 4, 'experience_max': 5, 'employer_posted': '2026-09-20',
            'employment': 'employee', 'full_time': True, 'pay_kind': 'base',
            'pay_min': 100000, 'pay_max': 130000, 'currency': 'USD', 'period': 'year',
            'sponsorship_status': 'not_stated',
            'quotes': {'experience': 'Four years of relevant experience required.'},
            'evidence': {
                'title': 'Employer JD title is Business Analyst.',
                'pay': 'Employer JD says annual base is USD 100,000–130,000.',
                'location': 'Employer JD explicitly permits work in the United States.',
                'experience': 'Employer JD requires four years.',
                'employment': 'Employer JD says regular full-time employee.',
                'freshness': 'Employer JD was posted 20 September 2026.',
                'sponsorship': 'Current employer JD does not state a sponsorship policy.',
            },
        },
    }


class EligibilityTests(unittest.TestCase):
    def group(self, job):
        return t.classify(job, TODAY)[0]

    def test_all_requested_titles(self):
        for title in t.TARGET_TITLES:
            with self.subTest(title=title):
                self.assertTrue(t.software(title))
                self.assertEqual(self.group(fixture(title)), 'Ready')

    def test_title_boundaries_and_product_manager_exception(self):
        self.assertFalse(t.software('Senior Business Analyst'))
        self.assertFalse(t.software('Lead Product Analyst'))
        self.assertFalse(t.software('Senior Product Manager'))
        self.assertTrue(t.software('Product Manager, Growth'))
        self.assertTrue(t.software('Associate Product Manager'))
        self.assertFalse(t.software('Engineering Manager'))

    def test_us_location_required(self):
        job = fixture(); job['review']['location_fit'] = False
        self.assertEqual(self.group(job), 'Excluded')
        job = fixture(); job['review']['location_fit'] = None
        self.assertEqual(self.group(job), 'Needs verification')

    def test_experience_2_through_5(self):
        for years in range(2, 6):
            job = fixture(); job['review'].update(experience_min=years, experience_max=years)
            self.assertEqual(self.group(job), 'Ready')
        for years in (1, 6):
            job = fixture(); job['review'].update(experience_min=years, experience_max=years)
            self.assertEqual(self.group(job), 'Needs verification')

    def test_full_time_employee_only(self):
        for employment in ('contract', 'temporary', 'internship', 'part_time', 'unknown'):
            job = fixture(); job['review']['employment'] = employment
            self.assertEqual(self.group(job), 'Excluded')
        job = fixture(); job['review']['full_time'] = False
        self.assertEqual(self.group(job), 'Excluded')

    def test_salary_floor_and_crossing_range(self):
        job = fixture(); job['review'].update(pay_min=90000, pay_max=130000)
        self.assertEqual(self.group(job), 'Caution: range crosses $100k')
        job = fixture(); job['review'].update(pay_min=90000, pay_max=99999)
        self.assertEqual(self.group(job), 'Below $100k base')
        job = fixture(); job['review'].update(pay_min=None, pay_max=None)
        self.assertEqual(self.group(job), 'Needs verification')

    def test_non_usd_and_total_comp_do_not_qualify(self):
        job = fixture(); job['review']['currency'] = 'EUR'
        self.assertEqual(self.group(job), 'Needs verification')
        job = fixture(); job['review']['pay_kind'] = 'total_comp'
        self.assertEqual(self.group(job), 'Needs verification')

    def test_sponsorship_statuses(self):
        for status in ('offered', 'not_stated', 'conditional'):
            job = fixture(); job['review']['sponsorship_status'] = status
            if status == 'conditional': job['review']['sponsorship_conditions'] = 'Only selected visa categories.'
            self.assertEqual(self.group(job), 'Ready')
        for status in ('not_offered', 'restricted'):
            job = fixture(); job['review']['sponsorship_status'] = status
            self.assertEqual(self.group(job), 'Excluded')

    def test_old_india_review_requires_new_policy_evidence(self):
        job = fixture(); job['review'].update(policy_version='india-v1', pay_applies_to_india=True)
        group, reasons = t.classify(job, TODAY)
        self.assertEqual(group, 'Needs verification')
        self.assertIn('predates', reasons[0])

    def test_employer_jd_and_freshness_required(self):
        job = fixture(); job['review']['evidence_source'] = 'aggregator'
        self.assertEqual(self.group(job), 'Needs verification')
        job = fixture(); job['review']['employer_posted'] = '2026-08-01'
        self.assertEqual(self.group(job), 'Needs verification')
        job['review'].update(active_signal_date='2026-09-20', active_signal_url='https://acme.example/hiring')
        self.assertEqual(self.group(job), 'Needs verification')

    def test_review_validation_requires_new_schema(self):
        review = fixture()['review'] | {'url': fixture()['url']}
        t.validate_review(review)
        for field in ('sponsorship_status', 'experience_min', 'full_time'):
            bad = copy.deepcopy(review); del bad[field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                t.validate_review(bad)

    def test_closed_and_network_failure(self):
        job = fixture(); job['check'] = {'state': 'blocked', 'checked_at': '2026-09-21'}
        self.assertEqual(self.group(job), 'Needs verification')
        job = fixture(); job['check'] = {'state': 'closed', 'checked_at': '2026-09-21'}
        self.assertEqual(self.group(job), 'Closed')


class IdentityTests(unittest.TestCase):
    def test_canonical_dedup(self):
        self.assertEqual(t.identity('https://www.coinbase.com/careers/positions/123?gh_jid=123&utm_source=x'),
                         t.identity('https://boards.greenhouse.io/coinbase/jobs/123'))
        self.assertEqual(t.identity('https://jobs.lever.co/acme/abc/application?source=LinkedIn'),
                         t.identity('https://jobs.lever.co/acme/abc'))

    def test_source_alias_merges_history(self):
        state = {'jobs': {}, 'boards': {}}
        t.merge(state, t.record('Acme', 'Business Analyst', 'https://aggregator.example/role'), 'feed', '2026-08-01')
        job = t.record('Acme', 'Business Analyst', 'https://jobs.lever.co/acme/123', aliases=['https://aggregator.example/role'])
        key = t.merge(state, job, 'employer:lever:acme', '2026-09-21')
        self.assertEqual(len(state['jobs']), 1)
        self.assertEqual(state['jobs'][key]['first_seen'], '2026-08-01')
        self.assertIn('feed', state['jobs'][key]['sources'])

    def test_unrelated_title_not_collected(self):
        state = {'jobs': {}, 'boards': {}}
        self.assertIsNone(t.merge(state, t.record('Acme', 'Software Engineer', 'https://example.com/1'), 'feed', '2026-09-21'))


class ReportingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data_patch = mock.patch.object(t, 'DATA', Path(self.temp.name) / 'data')
        self.root_patch = mock.patch.object(t, 'ROOT', Path(self.temp.name))
        self.data_patch.start(); self.root_patch.start()
        self.addCleanup(self.data_patch.stop); self.addCleanup(self.root_patch.stop)

    def state(self, jobs):
        for job in jobs:
            job['queue'] = t.classify(job, TODAY)[0]
        return {'jobs': {j['id']: j for j in jobs}, 'boards': {}, 'runs': []}

    def test_master_sort_newest_first_unknown_last(self):
        old = fixture('Data Analyst', 'https://example.com/old'); old['review']['employer_posted'] = '2026-09-10'
        new = fixture('Product Analyst', 'https://example.com/new'); new['review']['employer_posted'] = '2026-09-20'
        unknown = fixture('Financial Analyst', 'https://example.com/unknown'); unknown['review']['employer_posted'] = None
        unknown['queue'] = 'Ready'  # sorting helper is independently exercised; classifier rejects unknown freshness.
        state = self.state([old, new]); state['jobs'][unknown['id']] = unknown
        self.assertEqual([j['id'] for j in t.qualifying_jobs(state)], [new['id'], old['id'], unknown['id']])

    def test_baseline_then_daily_new_only_and_retry(self):
        first = fixture('Business Analyst', 'https://example.com/first')
        state = self.state([first])
        baseline = t.publish_report(state, baseline=True, day='2026-09-21')
        self.assertIn(first['url'], baseline.read_text())
        second = fixture('Data Analyst', 'https://example.com/second')
        second['queue'] = t.classify(second, TODAY)[0]; state['jobs'][second['id']] = second
        daily = t.publish_report(state, day='2026-09-22')
        text = daily.read_text()
        self.assertIn(second['id'], state['reporting']['publications']['2026-09-22']['ids'])
        self.assertNotIn('Business Analyst — Acme', text)
        self.assertIn('Honest shortfall: 14', text)
        self.assertEqual(t.publish_report(state, day='2026-09-22').read_text(), text)

    def test_alias_of_reported_job_does_not_duplicate(self):
        aggregator = 'https://aggregator.example/acme-role'
        first = fixture(url='https://jobs.lever.co/acme/123'); first['aliases'] = [aggregator]
        state = self.state([first]); t.publish_report(state, baseline=True)
        replacement = fixture(url=aggregator); replacement['aliases'] = [first['url']]
        replacement['queue'] = 'Ready'; state['jobs'] = {replacement['id']: replacement}
        report = t.publish_report(state, day='2026-09-22')
        self.assertIn('No qualifying jobs', report.read_text())

    def test_failed_publication_does_not_advance_ledger(self):
        job = fixture(); state = self.state([job])
        with mock.patch.object(Path, 'replace', side_effect=OSError('disk full')):
            with self.assertRaises(OSError): t.publish_report(state, baseline=True)
        self.assertEqual(state['reporting']['reported_keys'], [])


if __name__ == '__main__':
    unittest.main()
