import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from jobtracker.ai import request_json, generate
from jobtracker.store import Store
from jobtracker.workflow import Workflow

class WorkflowTests(unittest.TestCase):
    def test_scheduled_pipeline_advances_and_preserves_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=Store(tmp)
            p=s.save_profile('Synthetic user',{'keywords':'engineer'})
            source=s.save_resume(p,'Master','Verified engineering experience')
            s.put(p,'settings',dict(provider='Ollama',model='test',allow_ai=True))
            s.put(p,'feed',dict(company='Example',type='Lever',board='example'))
            jobs=[dict(company='Example',title='Engineer '+str(i),url='https://example.org/job/'+str(i),description='Engineering',availability='open') for i in range(3)]
            for job in jobs:
                ident,_=s.upsert_job(p,job)
                s.approve(p,ident)
            calls=[]
            flow=Workflow(s,fetch=lambda f:jobs,ai=lambda *args:calls.append(args) or 'Synthetic draft')
            schedule=dict(resume_id=source,assess=True,draft=True,limit=1)
            for _ in range(4):
                run=flow.run(p,schedule)
                self.assertEqual(s.get(p,'run',run)['status'],'succeeded')
            self.assertEqual(len(calls),6) # two tasks for each of three jobs, then no paid repeats
            self.assertEqual(len(s.list(p,'draft')),6)
            target=s.list(p,'job')[0]
            s.upsert_job(p,dict(target,description='New requirements'))
            flow.run(p,dict(schedule,assess=False))
            self.assertEqual(len(calls),6) # changed job lost approval
            self.assertEqual(s.get(p,'resume',source)['text'],'Verified engineering experience')

    def test_source_key_and_url_duplicates_merge(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=Store(tmp); p=s.save_profile('Test',{})
            job=dict(company='Example',title='Designer',url='https://example.org/jobs/1')
            first,_=s.upsert_job(p,job)
            second,fresh=s.upsert_job(p,dict(job,source_key='feed:1'))
            self.assertEqual(first,second); self.assertFalse(fresh)
            self.assertEqual(len(s.list(p,'job')),1)

    def test_real_loopback_transport_to_ollama_adapter(self):
        received=[]
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                received.append((self.path,json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
                body=json.dumps({'message':{'content':'Local test response'}}).encode()
                self.send_response(200); self.end_headers(); self.wfile.write(body)
            def log_message(self,*a): pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        try:
            out=generate(dict(provider='Ollama',model='synthetic',endpoint=f'http://127.0.0.1:{server.server_port}'),'System','Prompt')
            self.assertEqual(out,'Local test response')
            self.assertEqual(received[0][0],'/api/chat')
            self.assertFalse(received[0][1]['stream'])
        finally:
            server.shutdown(); server.server_close(); thread.join()
