import os
import tempfile
import time
import unittest
from jobtracker.store import Store

@unittest.skipUnless(os.name == 'nt','Native Windows UI checks')
class DesktopTests(unittest.TestCase):
    def test_local_setup_saves_selected_launcher_and_keeps_search_preferences(self):
        from pathlib import Path
        from jobtracker.desktop import App,LocalAISetup
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(tmp)
            profile=store.save_profile('Synthetic local user',{})
            store.put(profile,'settings',dict(provider='OpenAI',enable_web=True,search_key_env='SYNTHETIC_SEARCH_KEY'))
            exe=Path(tmp)/'codex.exe'; exe.touch()
            app=App(store)
            setup=LocalAISetup(app,[dict(provider='Codex CLI',executable=str(exe),cli_command=[str(exe)],source='Synthetic install')])
            app.update()
            try:
                self.assertGreaterEqual(setup.winfo_height(),620)
                setup.connect()
                config=app.flow.config(profile)
                self.assertEqual(config['cli_command'],[str(exe)])
                self.assertEqual(config['model'],'')
                self.assertTrue(config['enable_web'])
                self.assertEqual(config['search_key_env'],'SYNTHETIC_SEARCH_KEY')
                self.assertFalse(config['allow_ai'])
            finally:
                for item in app.tk.splitlist(app.tk.call('after','info')):
                    app.after_cancel(item)
                app.destroy()

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
