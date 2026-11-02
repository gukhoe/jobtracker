import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from jobtracker.local_ai import discover,generate_cli,inspect_cli,launch_command,validate_model,run,cli_error
from jobtracker.ai import generate

class LocalAITests(unittest.TestCase):
    def test_discovery_is_portable_passive_and_resolves_npm(self):
        for username in ('Different User','Example 사용자'):
            with self.subTest(user=username),tempfile.TemporaryDirectory() as folder:
                home=Path(folder)/username
                native=home/'.local/bin'; native.mkdir(parents=True)
                (native/'claude.exe').touch()
                appdata=home/'Roaming'
                npm=appdata/'npm'; npm.mkdir(parents=True)
                node=home/'Node'; node.mkdir(); (node/'node.exe').touch()
                package=npm/'node_modules/@google/gemini-cli'
                (package/'bundle').mkdir(parents=True)
                (package/'bundle/gemini.js').write_text('// synthetic fixture')
                (package/'package.json').write_text(json.dumps(dict(name='@google/gemini-cli',bin={'gemini':'bundle/gemini.js'})))
                env=dict(USERPROFILE=str(home),APPDATA=str(appdata),PATH=os.pathsep.join([str(node),str(native),str(native)]))
                with patch('jobtracker.local_ai.subprocess.Popen') as proc:
                    found=discover(env)
                    proc.assert_not_called()
                self.assertEqual(len([c for c in found if c['provider']=='Claude CLI']),1)
                gemini=next(c for c in found if c['provider']=='Gemini CLI')
                self.assertEqual(gemini['cli_command'],[str((node/'node.exe').resolve()),str((package/'bundle/gemini.js').resolve())])
                # Hosted Windows runners can resolve TEMP's short-name/junction path.
                self.assertTrue(all(all(Path(p).is_relative_to(home.resolve()) for p in c['cli_command']) for c in found))

    def test_bad_manifest_cannot_escape_package_and_no_node_no_gemini(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            npm=root/'npm'; pkg=npm/'node_modules/@google/gemini-cli'; pkg.mkdir(parents=True)
            outside=root/'outside.js'; outside.touch()
            (pkg/'package.json').write_text(json.dumps(dict(name='@google/gemini-cli',bin={'gemini':str(outside)})))
            (npm/'node.exe').touch()
            env=dict(USERPROFILE=str(root),PATH=str(npm))
            self.assertFalse(any(c['provider']=='Gemini CLI' for c in discover(env)))
            (pkg/'package.json').write_text('{invalid')
            self.assertFalse(any(c['provider']=='Gemini CLI' for c in discover(env)))

    def test_cli_defaults_and_prompt_transport(self):
        with tempfile.TemporaryDirectory() as folder:
            exe=Path(folder)/'codex.exe'; exe.touch()
            config=dict(provider='Codex CLI',model='',executable=str(exe))
            def fake(command,args,cwd,**kwargs):
                self.assertNotIn('PRIVATE PROMPT',args)
                self.assertEqual(kwargs['prompt'],'SYSTEM\n\nPRIVATE PROMPT')
                self.assertNotIn('--model',args)
                self.assertIn('read-only',args)
                Path(args[args.index('--output-last-message')+1]).write_text('Draft',encoding='utf-8')
                return 0,''
            with patch('jobtracker.local_ai.run',side_effect=fake):
                self.assertEqual(generate(config,'SYSTEM','PRIVATE PROMPT'),'Draft')
            with self.assertRaises(ValueError):
                generate(dict(provider='OpenAI',model=''),'S','P')
            with self.assertRaises(ValueError):
                validate_model('6.1 Luna')

    def test_claude_and_gemini_text_only_contracts(self):
        with tempfile.TemporaryDirectory() as folder:
            exe=Path(folder)/'cli.exe'; exe.touch()
            for provider in ('Claude CLI','Gemini CLI'):
                def fake(command,args,cwd,**kwargs):
                    self.assertNotIn('SECRET TEXT',args)
                    if provider=='Claude CLI':
                        self.assertEqual(args[args.index('--tools')+1],'')
                        self.assertIn('--strict-mcp-config',args)
                        return 0,json.dumps({'result':'Claude draft','is_error':False})
                    policy=Path(args[args.index('--policy')+1]).read_text()
                    self.assertIn('decision = "deny"',policy)
                    settings=json.loads((Path(cwd)/'.gemini/settings.json').read_text())
                    self.assertFalse(settings['hooksConfig']['enabled'])
                    self.assertEqual(settings['mcp']['allowed'],['__jobtracker_no_servers__'])
                    return 0,json.dumps({'response':'Gemini draft'})
                with patch('jobtracker.local_ai.run',side_effect=fake):
                    self.assertIn('draft',generate_cli(dict(provider=provider,model='',executable=str(exe)),'SECRET TEXT'))

    def test_model_metadata_filters_hidden_entries_and_private_auth_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            exe=Path(folder)/'codex.exe'; exe.touch()
            def fake(command,args,cwd,**kwargs):
                if args==['--version']: return 0,'codex test-version'
                if args==['login','status']: return 0,'Signed in: private@example.org'
                return 0,json.dumps({'models':[{'slug':'visible-model','visibility':'list'},{'slug':'hidden','visibility':'hide'}]})
            with patch('jobtracker.local_ai.run',side_effect=fake):
                result=inspect_cli(dict(provider='Codex CLI',executable=str(exe)))
                self.assertEqual(result['authentication'],'Signed in')
                self.assertEqual(result['models'],['visible-model'])
                self.assertNotIn('private@example.org',json.dumps(result))

    def test_real_subprocess_uses_stdin_for_sensitive_text(self):
        with tempfile.TemporaryDirectory() as folder:
            script=Path(folder)/'fixture.py'
            script.write_text('import sys; print(sys.stdin.read().upper())')
            code,text=run([sys.executable],[str(script)],folder,prompt='Synthetic input')
            self.assertEqual(code,0)
            self.assertEqual(text.strip(),'SYNTHETIC INPUT')

    def test_authentication_failure_is_actionable_and_does_not_echo_output(self):
        message=cli_error('Claude CLI',1,'401 OAuth access token is invalid. private@example.org SECRET')
        self.assertIn('claude auth login',message)
        self.assertNotIn('SECRET',message)
        with tempfile.TemporaryDirectory() as folder:
            script=Path(folder)/'failure.py'
            script.write_text('import sys; print("401 PRIVATE ERROR", file=sys.stderr); sys.exit(1)')
            with self.assertRaisesRegex(RuntimeError,'codex login'):
                run([sys.executable],[str(script)],folder,failure_context='Codex CLI')
