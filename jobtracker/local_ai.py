"""Portable, passive CLI discovery and explicit metadata probes.

Never searches a whole drive, reads token files, installs software or executes
shell shims. npm entry points run through Node with an argument list.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import ctypes
from pathlib import Path

CLI_PROVIDERS = ('Codex CLI','Claude CLI','Gemini CLI')
PACKAGES = {'Codex CLI':'@openai/codex','Claude CLI':'@anthropic-ai/claude-code','Gemini CLI':'@google/gemini-cli'}
COMMANDS = {'Codex CLI':'codex','Claude CLI':'claude','Gemini CLI':'gemini','Ollama':'ollama'}

def is_file(path):
    try:
        return path.is_file()
    except OSError:
        return False

def discover(environ=None, home=None):
    """Return existing launch commands, using only this user's installation paths."""
    env = os.environ if environ is None else environ
    home = Path(home) if home else Path(env.get('USERPROFILE') or env.get('HOME') or Path.home())
    dirs = [Path(x.strip('"')) for x in env.get('PATH','').split(os.pathsep) if x and not x.startswith(('\\\\','//')) and Path(x.strip('"')).is_absolute()]
    dirs += [home / '.local/bin',home / '.cargo/bin',home / 'scoop/shims']
    if env.get('APPDATA'):
        dirs += [Path(env['APPDATA']) / 'npm']
    if env.get('LOCALAPPDATA'):
        programs = Path(env['LOCALAPPDATA']) / 'Programs'
        dirs += [programs / 'OpenAI/Codex/bin', programs / 'Ollama', programs / 'claude']
    if env.get('ProgramFiles'):
        dirs += [Path(env['ProgramFiles']) / 'nodejs',Path(env['ProgramFiles']) / 'Ollama']
    unique_dirs = list(dict.fromkeys(dirs))
    node = next((d / 'node.exe' for d in unique_dirs if is_file(d / 'node.exe')), None)
    if node is None and os.name != 'nt':
        found = shutil.which('node',path=os.pathsep.join(map(str,unique_dirs)))
        node = Path(found) if found else None
    results, seen = [], set()
    def add(provider, command, source):
        paths = [str(Path(p).resolve()) for p in command]
        key = (provider,tuple(os.path.normcase(x) for x in paths))
        if key in seen:
            return
        seen.add(key)
        results.append(dict(provider=provider,cli_command=paths,executable=paths[0],source=source))
    for provider, name in COMMANDS.items():
        for directory in unique_dirs:
            for suffix in (('.exe',) if os.name == 'nt' else ('','.exe')):
                path = directory / (name + suffix)
                if is_file(path):
                    add(provider,[path],'PATH / standard install')
        if provider not in PACKAGES:
            continue
        roots = [d / 'node_modules' / PACKAGES[provider] for d in unique_dirs]
        for root in roots:
            manifest = root / 'package.json'
            try:
                if not manifest.is_file() or manifest.stat().st_size > 1_000_000:
                    continue
                info = json.loads(manifest.read_text(encoding='utf-8'))
                if info.get('name') != PACKAGES[provider]:
                    continue
                if provider == 'Codex CLI':
                    # Native npm packages avoid wrapper shells and unnecessary Node processes.
                    for pattern in ('vendor/*/codex/codex.exe','node_modules/@openai/codex-*/vendor/*/codex/codex.exe'):
                        for native in root.glob(pattern):
                            if native.is_file():
                                add(provider,[native],'npm native package')
                entry = info.get('bin',{})
                entry = entry.get(name) if isinstance(entry,dict) else entry
                script = (root / entry).resolve() if isinstance(entry,str) else None
                if node and script and script.is_relative_to(root.resolve()) and script.is_file() and script.suffix in ('.js','.mjs','.cjs'):
                    add(provider,[node,script],'npm package (Node)')
            except (OSError,ValueError):
                continue
    return results

def launch_command(config):
    command = config.get('cli_command')
    if command and config.get('executable') != command[0]:
        command = None # A manually edited executable replaces the detected launcher.
    command = command or [config.get('executable','')]
    if not isinstance(command,list) or len(command) not in (1,2) or not all(isinstance(x,str) and Path(x).is_file() for x in command):
        raise ValueError('CLI not found. Use Detect local AI or browse to the installed executable.')
    if os.name == 'nt' and Path(command[0]).suffix.lower() != '.exe':
        raise ValueError('Select an executable, not a .cmd/.bat/.ps1 shell wrapper. Detection resolves npm launchers automatically.')
    if len(command) == 2 and (Path(command[0]).stem.lower() != 'node' or Path(command[1]).suffix.lower() not in ('.js','.mjs','.cjs')):
        raise ValueError('Unsupported CLI launcher. Detect the installation again.')
    return command

def cli_error(provider,code,text):
    lower = text.lower()
    if any(x in lower for x in ('oauth access token is invalid','401','unauthorized','authentication failed','not logged in','failed to authenticate')):
        login = {'Codex CLI':'codex login','Claude CLI':'claude auth login','Gemini CLI':'gemini'}.get(provider,'the CLI login command')
        return f'{provider} authentication failed. Sign in again in a terminal with {login}, then retry. Detected sign-in metadata does not prove the token is valid.'
    if any(x in lower for x in ('429','rate limit','quota exceeded','usage limit')):
        return f'{provider} reached an account usage limit. Check your CLI account quota and retry later.'
    if any(x in lower for x in ('model is not supported','model not found','unknown model','invalid model','does not exist')):
        return f'{provider} could not use the selected model. Select an exact detected model ID or leave the model blank for the CLI default.'
    if any(x in lower for x in ('unexpected argument','unknown option','unrecognized argument')):
        return f'{provider} does not support the required headless options. Update the CLI and detect it again.'
    return f'{provider} exited with code {code}. Check sign-in, model access and connectivity in its terminal, then retry.'

class ProcessTree:
    """Windows job ownership ensures CLI descendants cannot outlive a request."""
    def __init__(self,process):
        self.handle = None
        if os.name != 'nt':
            return
        from ctypes import wintypes as w
        class Basic(ctypes.Structure):
            _fields_=[('process_time',ctypes.c_int64),('job_time',ctypes.c_int64),('flags',w.DWORD),('min_ws',ctypes.c_size_t),('max_ws',ctypes.c_size_t),('active',w.DWORD),('affinity',ctypes.c_size_t),('priority',w.DWORD),('scheduling',w.DWORD)]
        class Info(ctypes.Structure):
            _fields_=[('basic',Basic),('io',ctypes.c_uint64*6),('process_memory',ctypes.c_size_t),('job_memory',ctypes.c_size_t),('peak_process',ctypes.c_size_t),('peak_job',ctypes.c_size_t)]
        api = ctypes.WinDLL('kernel32',use_last_error=True)
        api.CreateJobObjectW.restype=w.HANDLE
        api.SetInformationJobObject.argtypes=[w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD]
        api.AssignProcessToJobObject.argtypes=[w.HANDLE,w.HANDLE]
        api.CloseHandle.argtypes=[w.HANDLE]
        handle = api.CreateJobObjectW(None,None)
        info=Info(); info.basic.flags=0x2000 # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not handle or not api.SetInformationJobObject(handle,9,ctypes.byref(info),ctypes.sizeof(info)) or not api.AssignProcessToJobObject(handle,int(process._handle)):
            if handle: api.CloseHandle(handle)
            process.kill(); process.wait()
            raise RuntimeError('Windows could not isolate the CLI process. Check local process security policy.')
        self.handle,self.api=handle,api

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle=None

def run(command, args, folder, prompt=None, timeout=20, env=None, failure_context=None):
    """File-backed output bounds memory and avoids logging private prompt/error text."""
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(command + args,stdin=subprocess.PIPE,stdout=stdout,stderr=stderr,cwd=folder,env=env,
                                   shell=False,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        tree = ProcessTree(process)
        try:
            process.communicate(prompt.encode('utf-8') if prompt is not None else b'',timeout=timeout)
        except subprocess.TimeoutExpired:
            # CLI tools may spawn Node/native children; terminate this process tree only.
            if os.name == 'nt':
                subprocess.run(['taskkill.exe','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
            process.kill(); process.wait()
            raise RuntimeError('CLI timed out. Check sign-in, model access and connectivity, then retry.') from None
        finally:
            tree.close()
        stdout.seek(0); data = stdout.read(4_000_001)
        if len(data) > 4_000_000:
            raise RuntimeError('CLI output exceeded the 4 MB limit.')
        if process.returncode and failure_context:
            stderr.seek(0)
            diagnostic = data.decode('utf-8',errors='replace') + stderr.read(200_000).decode('utf-8',errors='replace')
            raise RuntimeError(cli_error(failure_context,process.returncode,diagnostic))
        return process.returncode,data.decode('utf-8',errors='replace')

def inspect_cli(candidate):
    command = launch_command(candidate)
    result = dict(candidate,version='Unknown',authentication='Not checked',models=[],model_source='')
    with tempfile.TemporaryDirectory(prefix='jobtracker-inspect-',ignore_cleanup_errors=True) as folder:
        try:
            code,text = run(command,['--version'],folder)
            if code == 0:
                result['version'] = text.strip().splitlines()[0][:120] if text.strip() else 'Detected'
            provider = candidate['provider']
            if provider == 'Codex CLI':
                code,_ = run(command,['login','status'],folder)
                result['authentication'] = 'Signed in' if code == 0 else 'Sign in with codex login'
                code,text = run(command,['debug','models'],folder,timeout=25)
                result['model_source'] = 'CLI catalog (account access must still be tested)'
                if code:
                    code,text = run(command,['debug','models','--bundled'],folder)
                    result['model_source'] = 'Bundled catalog (account access unverified)'
                if code == 0:
                    data = json.loads(text)
                    result['models'] = [m['slug'] for m in data.get('models',[]) if m.get('visibility') != 'hide' and m.get('slug')]
            elif provider == 'Claude CLI':
                code,text = run(command,['auth','status'],folder)
                data = json.loads(text) if text.strip().startswith('{') else {}
                result['authentication'] = 'Signed in' if code == 0 and data.get('loggedIn') else 'Sign in with claude auth login'
            elif provider == 'Gemini CLI':
                result['authentication'] = 'Use Test AI connection; sign in with gemini in a terminal if needed'
            else:
                result['authentication'] = 'Local server availability is checked when loading models'
        except (OSError,ValueError,RuntimeError):
            result['authentication'] = 'Metadata check incomplete; use Test AI connection'
    return result

def validate_model(model):
    if model and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/-]*',model):
        raise ValueError('Use an exact model ID, not a display label such as "6.1 Luna". Leave blank for the CLI default or select a detected ID.')

def generate_cli(config, prompt):
    command = launch_command(config)
    provider, model = config['provider'],config.get('model','').strip()
    validate_model(model)
    model_args = ['--model',model] if model else []
    with tempfile.TemporaryDirectory(prefix='jobtracker-ai-',ignore_cleanup_errors=True) as folder:
        env = dict(os.environ)
        if provider == 'Codex CLI':
            output = Path(folder) / 'response.txt'
            args = ['exec','--skip-git-repo-check','--sandbox','read-only','--ephemeral','--output-last-message',str(output)] + model_args + ['-']
        elif provider == 'Claude CLI':
            args = ['--print','--output-format','json','--tools','','--permission-mode','dontAsk','--strict-mcp-config','--mcp-config','{"mcpServers":{}}','--no-session-persistence','--disable-slash-commands','--setting-sources','user','--settings','{"disableAllHooks":true}'] + model_args
        elif provider == 'Gemini CLI':
            policy = Path(folder) / 'text-only.toml'
            policy.write_text('[[rule]]\ntoolName = "*"\ndecision = "deny"\npriority = 999\n',encoding='utf-8')
            settings = Path(folder) / '.gemini/settings.json'
            settings.parent.mkdir()
            settings.write_text(json.dumps({'tools':{'core':[]},'mcp':{'allowed':['__jobtracker_no_servers__']},'hooksConfig':{'enabled':False},'skills':{'enabled':False},'security':{'allowedExtensions':['^__jobtracker_no_extensions__$']},'general':{'enableAutoUpdate':False}}))
            # Project-scoped restrictions never replace the user's or an administrator's settings.
            args = ['--prompt','Answer the request provided on stdin.','--output-format','json','--policy',str(policy),'--allowed-mcp-server-names','__jobtracker_no_servers__','--extensions','__jobtracker_no_extensions__'] + model_args
        else:
            raise ValueError('Unsupported local CLI provider.')
        try:
            code,text = run(command,args,folder,prompt=prompt,timeout=300,env=env,failure_context=provider)
        except OSError:
            raise RuntimeError('Could not start the CLI. Detect it again or check its installation.') from None
        if code:
            raise RuntimeError(f'{provider} exited with code {code}. Check its sign-in and exact model ID in a terminal. No API key is required by JobTracker for CLI sign-in.')
        if provider == 'Codex CLI':
            if not output.is_file() or output.stat().st_size > 4_000_000:
                raise RuntimeError('Codex did not produce a valid text response.')
            text = output.read_text(encoding='utf-8')
        else:
            try:
                data = json.loads(text)
                if data.get('is_error') or data.get('error'):
                    raise ValueError('CLI reported an error')
                text = data.get('result' if provider == 'Claude CLI' else 'response','')
            except ValueError:
                raise RuntimeError(f'{provider} returned an invalid response. Check its CLI version, sign-in and model access.') from None
        if not isinstance(text,str) or not text.strip():
            raise RuntimeError('CLI returned no document text.')
        return text.strip()
