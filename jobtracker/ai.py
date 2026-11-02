"""Small provider adapters. No bundled credentials or implicit provider calls."""
import base64
import ctypes
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, quote
from urllib.request import Request, build_opener, HTTPRedirectHandler
from .local_ai import CLI_PROVIDERS, generate_cli

PROVIDERS = {
    'OpenAI': 'https://api.openai.com/v1',
    'Claude': 'https://api.anthropic.com/v1',
    'Gemini': 'https://generativelanguage.googleapis.com/v1beta',
    'Grok': 'https://api.x.ai/v1',
    'Ollama': 'http://127.0.0.1:11434',
    'OpenAI-compatible': 'http://127.0.0.1:1234/v1',
    'Codex CLI': '',
    'Claude CLI': '',
    'Gemini CLI': '',
}

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Redirect refused. Set the final endpoint URL in Settings.')

def validate_url(url):
    p = urlparse(url)
    if p.username or p.password or p.fragment:
        raise ValueError('Endpoint URLs must not contain credentials or fragments.')
    if p.scheme != 'https' and not (p.scheme == 'http' and p.hostname in ('localhost','127.0.0.1','::1')):
        raise ValueError('Use HTTPS, or HTTP on a loopback address for a local service.')
    if not p.hostname:
        raise ValueError('An endpoint URL is required.')
    return url.rstrip('/')

def request_json(url, payload=None, headers=None, timeout=120):
    validate_url(url)
    req = Request(url, data=json.dumps(payload).encode() if payload is not None else None,
                  headers={'Content-Type':'application/json','User-Agent':'JobTracker/0.1', **(headers or {})})
    try:
        with build_opener(NoRedirect()).open(req, timeout=timeout) as response:
            body = response.read(12_000_001)
        if len(body) > 12_000_000:
            raise ValueError('Response exceeded the 12 MB limit.')
        return json.loads(body)
    except HTTPError as exc:
        # Do not echo provider response bodies: these can contain input or credentials.
        raise RuntimeError(f'Service returned HTTP {exc.code}. Check endpoint, model, credentials and quota.') from None
    except URLError:
        raise RuntimeError('Could not reach the service. Check connectivity and endpoint.') from None

class Blob(ctypes.Structure):
    _fields_ = [('size', ctypes.c_ulong), ('data', ctypes.POINTER(ctypes.c_ubyte))]

def _dpapi(data, decrypt=False):
    if os.name != 'nt':
        raise ValueError('Saved keys require Windows DPAPI. Use an environment variable on this OS.')
    buf = ctypes.create_string_buffer(data)
    src = Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    dest = Blob()
    api = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    ok = api(ctypes.byref(src), None, None, None, None, 1, ctypes.byref(dest))
    if not ok:
        raise ValueError('Windows could not access this saved key. Re-enter it on this user account.')
    try:
        return ctypes.string_at(dest.data, dest.size)
    finally:
        ctypes.windll.kernel32.LocalFree(dest.data)

def protect(key):
    return base64.b64encode(_dpapi(key.encode())).decode() if key else ''

def secret(config):
    if config.get('key_env'):
        value = os.environ.get(config['key_env'], '')
    else:
        value = _dpapi(base64.b64decode(config['encrypted_key']), True).decode() if config.get('encrypted_key') else ''
    return value

def generate(config, system, prompt, transport=request_json):
    provider, model = config.get('provider'), config.get('model','').strip()
    if provider not in PROVIDERS or (not model and provider not in CLI_PROVIDERS):
        raise ValueError('Select a provider and enter its exact model ID in AI settings.')
    if provider in CLI_PROVIDERS:
        return generate_cli(config, system + '\n\n' + prompt)
    base = validate_url(config.get('endpoint',''))
    key = secret(config)
    if provider in ('OpenAI','Claude','Gemini','Grok') and not key:
        raise ValueError('Configure your API key or environment variable in AI settings.')
    headers = {'Authorization': 'Bearer ' + key} if key else {}
    if provider in ('OpenAI','Grok'):
        result = transport(base + '/responses', {'model':model,'instructions':system,'input':prompt}, headers)
        text = '\n'.join(part.get('text','') for item in result.get('output',[]) if item.get('type') == 'message' for part in item.get('content',[]) if part.get('type') == 'output_text')
    elif provider == 'Claude':
        result = transport(base + '/messages', {'model':model,'system':system,'max_tokens':8192,'messages':[{'role':'user','content':prompt}]}, {'x-api-key':key,'anthropic-version':'2023-06-01'})
        text = '\n'.join(c.get('text','') for c in result.get('content',[]) if c.get('type') == 'text')
    elif provider == 'Gemini':
        result = transport(base + '/models/' + quote(model, safe='-._') + ':generateContent', {'systemInstruction':{'parts':[{'text':system}]},'contents':[{'role':'user','parts':[{'text':prompt}]}]}, {'x-goog-api-key':key})
        text = '\n'.join(p.get('text','') for c in result.get('candidates',[]) for p in c.get('content',{}).get('parts',[]) if not p.get('thought'))
    elif provider == 'Ollama':
        result = transport(base + '/api/chat', {'model':model,'stream':False,'messages':[{'role':'system','content':system},{'role':'user','content':prompt}]}, headers)
        text = result.get('message',{}).get('content','')
    else:
        result = transport(base + '/chat/completions', {'model':model,'messages':[{'role':'system','content':system},{'role':'user','content':prompt}]}, headers)
        text = result.get('choices',[{}])[0].get('message',{}).get('content','')
    if not isinstance(text, str) or not text.strip():
        raise ValueError('The model returned no text. Check model compatibility or content restrictions.')
    return text.strip()
