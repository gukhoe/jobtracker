import os
import tempfile
import time
import unittest
from jobtracker.store import Store

@unittest.skipUnless(os.name == 'nt','Native Windows UI checks')
class DesktopTests(unittest.TestCase):
    def test_due_schedule_claimed_once_and_gui_stays_responsive(self):
        from jobtracker.desktop import App
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(tmp)
            profile=store.save_profile('Synthetic desktop user',{})
            schedule=store.put(profile,'schedule',dict(enabled=True,time='09:00',timezone='UTC',days=[0,3],next_run='2020-01-01T00:00:00+00:00'))
            app=App(store); app.withdraw()
            calls=[]
            class FakeFlow:
                def run(self,p,s):
                    calls.append((p,s['id']))
                    return 'Synthetic scheduled run completed'
                def config(self,p): return {}
            app.flow=FakeFlow()
            try:
                app.tick()
                limit=time.monotonic()+3
                while app.busy and time.monotonic()<limit:
                    app.update(); time.sleep(.01)
                self.assertFalse(app.busy)
                app.tick()
                self.assertEqual(calls,[(profile,schedule)])
                self.assertGreater(store.get(profile,'schedule',schedule)['next_run'],'2020-01-01')
                self.assertEqual(len(app.tabs.tabs()),7)
            finally:
                for item in app.tk.splitlist(app.tk.call('after','info')):
                    app.after_cancel(item)
                app.destroy()
