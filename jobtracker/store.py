"""Profile-scoped persistence. All timestamps are UTC, all source resumes immutable."""
import hashlib
import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

STATES = ('discovered', 'shortlisted', 'drafting', 'ready', 'submitted', 'interview', 'offer', 'rejected', 'withdrawn')

def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def uid():
    return uuid.uuid4().hex

def data_dir():
    return Path(os.environ.get('JOBTRACKER_DATA_DIR') or Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local/share')) / 'JobTracker')

class Store:
    def __init__(self, root=None):
        self.root = Path(root) if root else data_dir()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / 'tracker.sqlite3'
        with self.db() as c:
            c.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS profiles(id TEXT PRIMARY KEY, name TEXT NOT NULL, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY, profile TEXT NOT NULL REFERENCES profiles(id),
              kind TEXT NOT NULL, data TEXT NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS records_scope ON records(profile,kind);
            CREATE TABLE IF NOT EXISTS job_keys(profile TEXT, source_key TEXT, record_id TEXT, PRIMARY KEY(profile,source_key));
            CREATE TABLE IF NOT EXISTS leases(profile TEXT PRIMARY KEY, owner TEXT, expires REAL);
            ''')

    @contextmanager
    def db(self):
        c = sqlite3.connect(self.path, timeout=30)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    def profiles(self):
        with self.db() as c:
            return [dict(id=r['id'], name=r['name'], **json.loads(r['data'])) for r in c.execute('SELECT * FROM profiles ORDER BY name')]

    def save_profile(self, name, data, ident=None):
        ident = ident or uid()
        if not name.strip():
            raise ValueError('Profile name is required.')
        with self.db() as c:
            c.execute('INSERT INTO profiles VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,data=excluded.data', (ident, name.strip(), json.dumps(data)))
        return ident

    def profile(self, ident):
        return next(p for p in self.profiles() if p['id'] == ident)

    def list(self, profile, kind):
        with self.db() as c:
            return [dict(json.loads(r['data']), id=r['id'], created=r['created'], updated=r['updated']) for r in c.execute('SELECT * FROM records WHERE profile=? AND kind=? ORDER BY updated DESC', (profile, kind))]

    def get(self, profile, kind, ident):
        return next((r for r in self.list(profile, kind) if r['id'] == ident), None)

    def put(self, profile, kind, data, ident=None):
        ident, stamp = ident or uid(), now()
        payload = {k: v for k, v in data.items() if k not in ('id', 'created', 'updated')}
        with self.db() as c:
            old = c.execute('SELECT profile,kind FROM records WHERE id=?', (ident,)).fetchone()
            if old and (old['profile'] != profile or old['kind'] != kind):
                raise ValueError('Record belongs to another profile or type.')
            c.execute('INSERT INTO records VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data,updated=excluded.updated', (ident, profile, kind, json.dumps(payload, ensure_ascii=False), stamp, stamp))
        return ident

    def remove(self, profile, kind, ident):
        with self.db() as c:
            c.execute('DELETE FROM records WHERE profile=? AND kind=? AND id=?', (profile, kind, ident))

    def upsert_job(self, profile, job):
        if not job.get('title') or not job.get('company') or not job.get('url'):
            raise ValueError('Jobs require company, title and a source URL.')
        key = job.get('source_key') or job['url'].split('#')[0].rstrip('/')
        canonical = job['url'].split('#')[0].rstrip('/')
        digest = hashlib.sha256(json.dumps({k: job.get(k) for k in ('title','company','description','location','salary_min','salary_max','salary_basis','currency')}, sort_keys=True).encode()).hexdigest()
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT record_id FROM job_keys WHERE profile=? AND source_key=?', (profile, key)).fetchone()
            if not row:
                row = c.execute("SELECT id FROM records WHERE profile=? AND kind='job' AND json_extract(data,'$.canonical_url')=?", (profile,canonical)).fetchone()
            ident = row[0] if row else uid()
            oldrow = c.execute('SELECT data,created FROM records WHERE id=? AND profile=?', (ident, profile)).fetchone()
            old = json.loads(oldrow['data']) if oldrow else {}
            merged = {**old, **job, 'content_hash':digest, 'source_key':key, 'canonical_url':canonical, 'checked_at':now()}
            for reserved in ('id','created','updated'):
                merged.pop(reserved,None)
            for field in ('status','notes','approved_hash','receipt','follow_up'):
                if field in old:
                    merged[field] = old[field]
            merged.setdefault('status', 'discovered')
            stamp = now()
            c.execute('INSERT INTO records VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data,updated=excluded.updated', (ident,profile,'job',json.dumps(merged),oldrow['created'] if oldrow else stamp,stamp))
            c.execute('INSERT OR REPLACE INTO job_keys VALUES(?,?,?)', (profile,key,ident))
        return ident, not bool(oldrow)

    def approve(self, profile, job_id):
        job = self.get(profile, 'job', job_id)
        if not job:
            raise ValueError('Select a job first.')
        job.update(approved_hash=job['content_hash'], approved_at=now(), status='shortlisted')
        self.put(profile, 'job', job, job_id)

    def save_resume(self, profile, label, text, job_id=None, source_id=None):
        if not text.strip():
            raise ValueError('Resume text cannot be empty.')
        ident = uid()
        folder = self.root / 'documents' / profile
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (ident + '.txt')
        path.write_text(text, encoding='utf-8')
        self.put(profile, 'resume', dict(label=label, text=text, path=str(path), job_id=job_id, source_id=source_id, sha256=hashlib.sha256(text.encode()).hexdigest()), ident)
        return ident

    def backup(self):
        folder = self.root / 'backups'
        folder.mkdir(exist_ok=True)
        dest = folder / (datetime.now().strftime('%Y%m%d-%H%M%S-') + uid()[:6] + '.sqlite3')
        with self.db() as source:
            target = sqlite3.connect(dest)
            try:
                source.backup(target)
            finally:
                target.close()
        return dest

def salary_class(job, profile):
    if job.get('salary_basis') != 'base' or job.get('currency','').upper() != profile.get('currency','USD').upper():
        return 'unknown'
    target = float(profile.get('minimum_base') or 0)
    low, high = job.get('salary_min'), job.get('salary_max')
    if low is not None and float(low) >= target:
        return 'meets'
    if high is not None and float(high) >= target:
        return 'overlaps'
    return 'below' if high is not None else 'unknown'
