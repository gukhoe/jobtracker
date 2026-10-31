import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from jobtracker.store import Store, salary_class
from jobtracker.ai import generate, validate_url, protect, secret
from jobtracker.workflow import Workflow, next_due
from jobtracker.research import fetch_feed, matches

class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.s = Store(self.tmp.name)
        self.p = self.s.save_profile('Test',{'minimum_base':100,'currency':'USD'})
        self.q = self.s.save_profile('Other',{})
        self.job = dict(company='Example Company',title='Engineer',url='https://example.org/jobs/1',description='Build systems',location='Remote')

    def test_isolation_update_and_approval_invalidation(self):
        ident,fresh = self.s.upsert_job(self.p,self.job)
        self.assertTrue(fresh)
        self.s.approve(self.p,ident)
        self.assertIsNone(self.s.get(self.q,'job',ident))
        with self.assertRaises(ValueError):
            self.s.put(self.q,'job',{},ident)
        again,fresh = self.s.upsert_job(self.p,dict(self.job,description='Changed requirements'))
        self.assertEqual(ident,again); self.assertFalse(fresh)
        job = self.s.get(self.p,'job',ident)
        self.assertNotEqual(job['approved_hash'],job['content_hash'])
        self.assertEqual(len(self.s.list(self.p,'job')),1)

    def test_source_immutable_and_draft_deduplicated(self):
        ident,_ = self.s.upsert_job(self.p,self.job)
        source = self.s.save_resume(self.p,'Verified source','Real experience')
        self.s.put(self.p,'settings',dict(provider='Ollama',model='local',allow_ai=True))
        calls = []
        flow = Workflow(self.s,ai=lambda *a: calls.append(a) or 'Draft')
        with self.assertRaises(ValueError):
            flow.draft(self.p,ident,source)
        self.s.approve(self.p,ident)
        first = flow.draft(self.p,ident,source)
        self.assertEqual(first,flow.draft(self.p,ident,source))
        self.assertEqual(len(calls),1)
        self.assertEqual(self.s.get(self.p,'resume',source)['text'],'Real experience')
        self.assertTrue(self.s.backup().exists())

    def test_failures_not_success(self):
        flow = Workflow(self.s)
        result = flow.run(self.p)
        self.assertEqual(self.s.get(self.p,'run',result)['status'],'failed')
        self.s.put(self.p,'feed',dict(company='Example',type='Lever',board='example'))
        flow = Workflow(self.s,fetch=lambda f: (_ for _ in ()).throw(ValueError('Offline')))
        result = flow.run(self.p)
        self.assertEqual(self.s.get(self.p,'run',result)['status'],'failed')

    def test_salary_and_schedule_dst(self):
        p = self.s.profile(self.p)
        self.assertEqual(salary_class(dict(salary_min=100,salary_max=200,salary_basis='base',currency='USD'),p),'meets')
        self.assertEqual(salary_class(dict(salary_min=80,salary_max=200,salary_basis='base',currency='USD'),p),'overlaps')
        self.assertEqual(salary_class(dict(salary_min=200,salary_basis='total',currency='USD'),p),'unknown')
        self.assertEqual(salary_class(dict(salary_min=200,salary_basis='base',currency='EUR'),p),'unknown')
        schedule = dict(time='09:00',timezone='America/Chicago',days=[0])
        self.assertEqual(next_due(schedule,datetime(2026,10,31,12,tzinfo=timezone.utc)),'2026-11-02T15:00:00+00:00')

    def test_web_only_exact_source_urls(self):
        self.s.put(self.p,'settings',dict(enable_web=True,allow_ai=True))
        result = Workflow(self.s,search=lambda *a:[dict(url='https://example.org/job/1')],ai=lambda *a:json.dumps([dict(company='Fake',title='Fake',url='https://invented.org/job')])).run(self.p)
        self.assertEqual(len(self.s.list(self.p,'job')),0)

class AdapterTests(unittest.TestCase):
    @patch('jobtracker.ai.secret',return_value='test-key')
    def test_contracts(self,_):
        cases = [
            ('OpenAI','/responses',{'output':[{'type':'message','content':[{'type':'output_text','text':'OK'}]}]}),
            ('Grok','/responses',{'output':[{'type':'message','content':[{'type':'output_text','text':'OK'}]}]}),
            ('Claude','/messages',{'content':[{'type':'text','text':'OK'}]}),
            ('Gemini',':generateContent',{'candidates':[{'content':{'parts':[{'text':'OK'}]}}]}),
            ('Ollama','/api/chat',{'message':{'content':'OK'}}),
            ('OpenAI-compatible','/chat/completions',{'choices':[{'message':{'content':'OK'}}]}),
        ]
        for provider,suffix,response in cases:
            calls=[]
            def transport(url,payload,headers):
                calls.append((url,payload,headers)); return response
            with self.subTest(provider=provider):
                result=generate(dict(provider=provider,model='test-model',endpoint='https://example.org/v1'),'System','Prompt',transport)
                self.assertEqual(result,'OK')
                self.assertTrue(calls[0][0].endswith(suffix))
                self.assertNotIn('test-key',calls[0][0])

    def test_endpoint_validation(self):
        for url in ('http://example.org','https://secret@example.org','file:///etc/passwd'):
            with self.assertRaises(ValueError): validate_url(url)
        self.assertEqual(validate_url('http://127.0.0.1:11434/'),'http://127.0.0.1:11434')

    @unittest.skipUnless(os.name == 'nt','Windows DPAPI')
    def test_saved_key_encrypted(self):
        value=protect('unit-test-only')
        self.assertNotIn('unit-test-only',value)
        self.assertEqual(secret({'encrypted_key':value}),'unit-test-only')

    def test_feed_mapping_and_filters(self):
        raw=[dict(id='1',text='Designer',hostedUrl='https://example.org/1',categories={'location':'Remote'},description='Design')]
        jobs=fetch_feed(dict(type='Lever',company='Example',board='example'),lambda url:raw)
        self.assertTrue(matches(jobs[0],{'keywords':'designer','locations':'remote'}))
        self.assertFalse(matches(jobs[0],{'keywords':'accountant'}))

if __name__ == '__main__':
    unittest.main()
