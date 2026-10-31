"""Native English desktop workspace. Slow operations never block Tk's event loop."""
import json
import os
import queue
import shutil
import sys
import threading
import tkinter as tk
import webbrowser
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from tkinter import ttk, filedialog, messagebox
from xml.etree import ElementTree
from . import __version__
from .ai import PROVIDERS, protect, validate_url
from .store import Store, STATES, salary_class, now
from .workflow import Workflow, next_due

class Form(tk.Toplevel):
    def __init__(self, app, title, fields, values, callback):
        super().__init__(app)
        self.title(title)
        self.transient(app)
        self.callback, self.inputs = callback, {}
        body = ttk.Frame(self,padding=18)
        body.pack(fill='both',expand=True)
        for row, (key,label,kind) in enumerate(fields):
            ttk.Label(body,text=label).grid(row=row,column=0,sticky='nw',padx=(0,16),pady=5)
            value = values.get(key,'')
            if kind == 'text':
                widget = tk.Text(body,width=68,height=5,wrap='word',font=('Segoe UI',10),undo=True)
                widget.insert('1.0',str(value))
            elif isinstance(kind,tuple):
                widget = ttk.Combobox(body,values=kind,state='readonly',width=48)
                widget.set(str(value or kind[0]))
            elif kind == 'bool':
                widget = tk.BooleanVar(value=bool(value))
                ttk.Checkbutton(body,variable=widget).grid(row=row,column=1,sticky='w')
            else:
                widget = ttk.Entry(body,width=68,show='•' if kind == 'secret' else '')
                widget.insert(0,str(value if value is not None else ''))
            if kind != 'bool':
                widget.grid(row=row,column=1,sticky='ew',pady=5)
            self.inputs[key] = (widget,kind)
        body.columnconfigure(1,weight=1)
        actions = ttk.Frame(body)
        actions.grid(row=len(fields),column=0,columnspan=2,sticky='e',pady=(16,0))
        ttk.Button(actions,text='Cancel',command=self.destroy).pack(side='left',padx=6)
        ttk.Button(actions,text='Save',command=self.save).pack(side='left')
        self.bind('<Escape>',lambda e:self.destroy())
        self.grab_set()

    def save(self):
        values = {k:(w.get('1.0','end-1c') if kind == 'text' else w.get()) for k,(w,kind) in self.inputs.items()}
        try:
            self.callback(values)
            self.destroy()
        except Exception as exc:
            messagebox.showerror('Check your settings',str(exc),parent=self)

class App(tk.Tk):
    def __init__(self, store=None):
        super().__init__()
        self.store = store or Store()
        self.flow = Workflow(self.store)
        self.events = queue.Queue()
        self.busy = False
        self.pid = None
        self.title('JobTracker')
        self.geometry('1220x800')
        self.minsize(980,650)
        style = ttk.Style(self)
        if 'vista' in style.theme_names():
            style.theme_use('vista')
        style.configure('Treeview',rowheight=30,font=('Segoe UI',10))
        style.configure('Treeview.Heading',font=('Segoe UI',10,'bold'))
        style.configure('TLabel',font=('Segoe UI',10))
        style.configure('TButton',padding=(10,5))
        top = ttk.Frame(self,padding=(20,16))
        top.pack(fill='x')
        ttk.Label(top,text='JobTracker',font=('Segoe UI',21,'bold')).pack(side='left')
        ttk.Label(top,text='Your opportunities. Your data.',padding=(20,0)).pack(side='left')
        self.profiles = ttk.Combobox(top,state='readonly',width=25)
        self.profiles.pack(side='right',padx=8)
        self.profiles.bind('<<ComboboxSelected>>',self.switch_profile)
        ttk.Button(top,text='New profile',command=lambda:self.profile_form(True)).pack(side='right')
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill='both',expand=True,padx=20)
        self.pages = {}
        for name in ('Jobs','Companies','Resumes & drafts','Research & schedule','AI settings','Profile','Activity'):
            frame = ttk.Frame(self.tabs,padding=12)
            self.tabs.add(frame,text=name)
            self.pages[name] = frame
        self.build_jobs()
        self.build_companies()
        self.build_docs()
        self.build_research()
        self.build_settings()
        self.build_profile()
        self.build_activity()
        self.status = tk.StringVar(value='Ready — local data: ' + str(self.store.root))
        ttk.Label(self,textvariable=self.status,padding=(20,10),wraplength=1150).pack(fill='x')
        self.refresh_profiles()
        if not self.people:
            self.tabs.select(self.pages['Profile'])
            self.status.set('Welcome — create a profile, import a resume, then configure research sources and AI.')
        self.after(200,self.poll)
        self.after(1500,self.tick)
        self.protocol('WM_DELETE_WINDOW',self.close)
        self.bind('<Control-r>',lambda e:self.refresh())

    def require(self):
        if not self.pid:
            messagebox.showinfo('Create a profile','Create your profile to begin. Data stays on this computer.')
            return False
        return True

    def button(self,parent,label,fn):
        ttk.Button(parent,text=label,command=lambda:self.safe(fn)).pack(side='left',padx=(0,6),pady=4)

    def safe(self,fn):
        try:
            if self.require():
                fn()
        except Exception as exc:
            messagebox.showerror('Action could not be completed',str(exc),parent=self)

    def tree(self,parent,cols):
        frame = ttk.Frame(parent)
        frame.pack(fill='both',expand=True,pady=8)
        tree = ttk.Treeview(frame,columns=cols,show='headings',selectmode='browse')
        for col in cols:
            tree.heading(col,text=col)
            tree.column(col,width=180,minwidth=70)
        scroll = ttk.Scrollbar(frame,orient='vertical',command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side='left',fill='both',expand=True)
        scroll.pack(side='right',fill='y')
        return tree

    def selected(self,tree,kind):
        selection = tree.selection()
        if not selection:
            raise ValueError('Select an item first.')
        result = self.store.get(self.pid,kind,selection[0])
        if not result:
            raise ValueError('This item is no longer available.')
        return result

    def build_jobs(self):
        p = self.pages['Jobs']
        actions = ttk.Frame(p)
        actions.pack(fill='x')
        for label,fn in [('Add job',self.job_form),('Edit job',lambda:self.job_form(True)),('Open source',self.open_job),('Approve for drafting',self.approve),('Update application',self.application_form),('Generate document',self.generate_form)]:
            self.button(actions,label,fn)
        filters = ttk.Frame(p)
        filters.pack(fill='x',pady=6)
        ttk.Label(filters,text='Search company, role or location').pack(side='left',padx=(0,12))
        self.query = tk.StringVar()
        ttk.Entry(filters,textvariable=self.query,width=40).pack(side='left')
        self.query.trace_add('write',lambda *a:self.refresh_jobs())
        self.jobtree = self.tree(p,('Company','Role','Location','Base salary','Status','Verification'))
        self.jobtree.column('Role',width=280)
        self.jobtree.bind('<<TreeviewSelect>>',self.job_detail)
        self.detail = tk.Text(p,height=8,wrap='word',font=('Segoe UI',10),state='disabled')
        self.detail.pack(fill='x')

    def job_detail(self,*args):
        selection = self.jobtree.selection()
        if not selection or not self.pid:
            return
        job = self.store.get(self.pid,'job',selection[0])
        text = f"{job['title']} | {job['company']}\n{job['url']}\nChecked: {job.get('checked_at','')} | Salary match: {salary_class(job,self.store.profile(self.pid))}\nApproval current: {job.get('approved_hash') == job.get('content_hash')}\n\n{job.get('description','')}\n\nNotes: {job.get('notes','')}\nReceipt: {job.get('receipt','')}"
        self.detail.configure(state='normal')
        self.detail.delete('1.0','end')
        self.detail.insert('1.0',text)
        self.detail.configure(state='disabled')

    def job_form(self,edit=False):
        old = self.selected(self.jobtree,'job') if edit else {}
        fields = [('company','Company','entry'),('title','Job title','entry'),('location','Location / remote','entry'),('url','Official source URL','entry'),('description','Job description / requirements','text'),('salary_min','Annual salary minimum','entry'),('salary_max','Annual salary maximum','entry'),('currency','Currency code','entry'),('salary_basis','Salary basis',('unknown','base','total')),('availability','Availability',('unverified','open','closed'))]
        def save(v):
            validate_url(v['url'])
            for k in ('salary_min','salary_max'):
                v[k] = float(v[k]) if v[k].strip() else None
                if v[k] is not None and v[k] < 0:
                    raise ValueError('Salary cannot be negative.')
            if v['salary_min'] is not None and v['salary_max'] is not None and v['salary_min'] > v['salary_max']:
                raise ValueError('Salary minimum must not exceed maximum.')
            v['source'] = 'User-entered source'
            if old:
                v['source_key'] = old['source_key']
            self.store.upsert_job(self.pid,v)
            self.refresh()
        Form(self,'Edit job' if edit else 'Add a job',fields,old,save)

    def open_job(self):
        url = self.selected(self.jobtree,'job')['url']
        validate_url(url)
        webbrowser.open(url)

    def approve(self):
        job = self.selected(self.jobtree,'job')
        if messagebox.askyesno('Approve this job version',f"Allow tailored document generation for {job['title']} at {job['company']}?\n\nAny later changes to the job requirements require approval again."):
            self.store.approve(self.pid,job['id'])
            self.refresh()

    def application_form(self):
        job = self.selected(self.jobtree,'job')
        def save(v):
            if v['status'] == 'submitted' and not v['receipt'].strip():
                raise ValueError('Record actual submission evidence (confirmation text or URL) first.')
            if v['status'] == 'submitted':
                v['submitted_at'] = job.get('submitted_at') or now()
            job.update(v)
            self.store.put(self.pid,'job',job,job['id'])
            self.store.put(self.pid,'event',dict(job_id=job['id'],status=v['status'],notes=v['notes'],receipt=v['receipt']))
            self.refresh()
        Form(self,'Application status',[('status','Status',STATES),('notes','Notes','text'),('receipt','Submission evidence','entry'),('follow_up','Follow-up date (YYYY-MM-DD)','entry')],job,save)

    def build_companies(self):
        p = self.pages['Companies']
        bar = ttk.Frame(p); bar.pack(fill='x')
        self.button(bar,'Add company',lambda:self.company_form(False))
        self.button(bar,'Edit selected company',lambda:self.company_form(True))
        ttk.Label(p,text='Keep company research, sources and notes alongside your opportunities. Any industry or region is welcome.').pack(anchor='w',pady=8)
        self.companytree = self.tree(p,('Name','Industry','Location','Careers URL','Notes'))

    def company_form(self,edit):
        old = self.selected(self.companytree,'company') if edit else {}
        def save(v):
            if not v['name'].strip():
                raise ValueError('Company name is required.')
            if v['url']:
                validate_url(v['url'])
            self.store.put(self.pid,'company',v,old.get('id'))
            self.refresh()
        Form(self,'Company research',[('name','Company name','entry'),('industry','Industry','entry'),('location','Locations','entry'),('url','Official careers URL','entry'),('notes','Research notes and source URLs','text')],old,save)

    def build_docs(self):
        p = self.pages['Resumes & drafts']
        bar = ttk.Frame(p); bar.pack(fill='x')
        for label,fn in [('Import source resume',self.import_resume),('Add / update source text',self.resume_form),('View selected',self.view_doc),('Export selected',self.export_doc),('Mark draft reviewed',self.review_doc)]:
            self.button(bar,label,fn)
        ttk.Label(p,text='Original sources stay unchanged. AI drafts require your review before use. TXT, DOCX and text-based PDF imports are supported.').pack(anchor='w',pady=6)
        self.doctree = self.tree(p,('Type','Label','Created','Provider / model','Review'))
        self.doctree.column('Label',width=390)
        self.doctree.bind('<Double-1>',lambda e:self.safe(self.view_doc))

    def resume_form(self):
        def save(v):
            self.store.save_resume(self.pid,v['label'],v['text'])
            self.refresh()
        Form(self,'Add a source resume',[('label','Version label','entry'),('text','Verified resume text','text')],{},save)

    def import_resume(self):
        name = filedialog.askopenfilename(filetypes=[('Resumes','*.txt *.docx *.pdf')])
        if not name:
            return
        path = Path(name)
        if path.stat().st_size > 15_000_000:
            raise ValueError('Resume import limit is 15 MB.')
        if path.suffix.lower() == '.docx':
            with zipfile.ZipFile(path) as z:
                info = z.getinfo('word/document.xml')
                if info.file_size > 10_000_000:
                    raise ValueError('DOCX document is too large.')
                root = ElementTree.fromstring(z.read(info))
            ns = {'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            text = '\n'.join(''.join(t.text or '' for t in p.findall('.//w:t',ns)) for p in root.findall('.//w:p',ns))
        elif path.suffix.lower() == '.pdf':
            from pypdf import PdfReader
            text = '\n'.join(p.extract_text() or '' for p in PdfReader(path).pages)
        else:
            text = path.read_text(encoding='utf-8-sig')
        self.store.save_resume(self.pid,path.name,text)
        self.refresh()

    def chosen_doc(self):
        selection = self.doctree.selection()
        if not selection:
            raise ValueError('Select a source resume or draft first.')
        kind, ident = selection[0].split(':',1)
        return kind,self.store.get(self.pid,kind,ident)

    def view_doc(self):
        kind, doc = self.chosen_doc()
        dialog = tk.Toplevel(self)
        dialog.title(doc['label']); dialog.geometry('850x650')
        text = tk.Text(dialog,wrap='word',font=('Segoe UI',11),padx=18,pady=18)
        text.pack(fill='both',expand=True)
        text.insert('1.0',doc['text']); text.configure(state='disabled')

    def export_doc(self):
        _,doc = self.chosen_doc()
        dest = filedialog.asksaveasfilename(defaultextension='.txt',filetypes=[('Plain text','*.txt')])
        if dest:
            Path(dest).write_text(doc['text'],encoding='utf-8')

    def review_doc(self):
        kind,doc = self.chosen_doc()
        if kind != 'draft':
            raise ValueError('Select an AI draft to mark as reviewed.')
        if messagebox.askyesno('Confirm document review','Have you verified every claim, date and qualification against your actual experience?'):
            doc['reviewed'] = True
            doc['reviewed_at'] = now()
            self.store.put(self.pid,kind,doc,doc['id'])
            self.refresh()

    def generate_form(self):
        job = self.selected(self.jobtree,'job')
        sources = self.store.list(self.pid,'resume')
        if not sources:
            raise ValueError('Import a source resume first.')
        options = tuple(r['label'] + ' [' + r['id'][:8] + ']' for r in sources)
        profile = self.pid
        def save(v):
            source = sources[options.index(v['source'])]
            if not messagebox.askyesno('Send to configured AI',f"Send this profile, source resume and job description to {self.flow.config(profile).get('provider','your provider')}?\nReview the result before using it."):
                return
            self.background(lambda:self.flow.draft(profile,job['id'],source['id'],v['task']),'Generating document')
        Form(self,'Generate a reviewable draft',[('source','Source resume',options),('task','Task',('Fit assessment','Tailored resume','Cover letter'))],{},save)

    def build_research(self):
        p = self.pages['Research & schedule']
        ttk.Label(p,text='Research public company feeds and optional web search. Schedules run while the app is open; missed runs execute once on restart.',wraplength=1050).pack(anchor='w',pady=8)
        bar = ttk.Frame(p); bar.pack(fill='x')
        for label,fn in [('Add company feed',self.feed_form),('Remove feed',self.remove_feed),('Run research now',lambda:self.run_workflow(False)),('Edit schedule',self.schedule_form),('Run full workflow now',lambda:self.run_workflow(True))]:
            self.button(bar,label,fn)
        self.schedule_text = tk.StringVar()
        ttk.Label(p,textvariable=self.schedule_text,wraplength=1050).pack(anchor='w',pady=10)
        self.feedtree = self.tree(p,('Company','Type','Board slug'))
        ttk.Label(p,text='Find a board slug in the company’s Lever or Greenhouse careers URL. Feeds retain only jobs matching your profile keywords and locations.\nWeb discovery uses your Brave Search API key and selected AI; search leads remain unverified. No email synchronization or automatic applications.',wraplength=1050).pack(anchor='w',pady=8)
        self.button(p,'Open local data folder',lambda:os.startfile(self.store.root))
        self.button(p,'Back up database',lambda:self.status.set('Backup saved: ' + str(self.store.backup())))
        self.button(p,'Launch at Windows sign-in',self.startup)

    def feed_form(self):
        def save(v):
            if not v['company'].strip() or not v['board'].strip() or not all(x.isalnum() or x in '-_' for x in v['board']):
                raise ValueError('Enter a company and board slug (letters, digits, hyphens or underscores).')
            self.store.put(self.pid,'feed',v)
            self.refresh()
        Form(self,'Add a public company feed',[('company','Company','entry'),('type','Feed type',('Lever','Greenhouse')),('board','Board slug','entry')],{},save)

    def remove_feed(self):
        feed = self.selected(self.feedtree,'feed')
        self.store.remove(self.pid,'feed',feed['id'])
        self.refresh()

    def schedule_form(self):
        rows = self.store.list(self.pid,'schedule')
        old = rows[0] if rows else {}
        sources = self.store.list(self.pid,'resume')
        choices = ('None',) + tuple(r['label'] + ' [' + r['id'][:8] + ']' for r in sources)
        values = dict(old,time=old.get('time','09:00'),timezone=old.get('timezone','UTC'),days=','.join(map(str,old.get('days',[0,3]))),limit=old.get('limit',3),resume='None')
        for i,r in enumerate(sources):
            if r['id'] == old.get('resume_id'):
                values['resume'] = choices[i+1]
        def save(v):
            v['days'] = sorted(set(int(x.strip()) for x in v['days'].split(',')))
            v['limit'] = int(v['limit'])
            if not 1 <= v['limit'] <= 10:
                raise ValueError('AI job limit must be between 1 and 10.')
            index = choices.index(v.pop('resume'))
            v['resume_id'] = sources[index-1]['id'] if index else None
            if (v['assess'] or v['draft']) and not v['resume_id']:
                raise ValueError('Select a source resume for AI processing.')
            if v['assess'] or v['draft']:
                if not self.flow.config(self.pid).get('allow_ai'):
                    raise ValueError('Enable AI sharing in Settings before scheduling document work.')
            v['next_run'] = next_due(v)
            self.store.put(self.pid,'schedule',v,old.get('id'))
            self.refresh()
        Form(self,'Schedule workflow',[('enabled','Enable schedule','bool'),('time','Local time (HH:MM, 24-hour)','entry'),('timezone','IANA timezone (e.g. America/Chicago)','entry'),('days','Weekdays: 0=Mon ... 6=Sun','entry'),('assess','Generate fit assessments','bool'),('draft','Generate resumes for approved jobs','bool'),('resume','Source resume',choices),('limit','Maximum AI jobs per run (1–10)','entry')],values,save)

    def run_workflow(self,full):
        rows = self.store.list(self.pid,'schedule')
        schedule = rows[0] if full and rows else None
        profile = self.pid
        self.background(lambda:self.flow.run(profile,schedule),'Running research workflow')

    def build_settings(self):
        p = self.pages['AI settings']
        ttk.Label(p,text='Connect your AI',font=('Segoe UI',16,'bold')).pack(anchor='w',pady=8)
        ttk.Label(p,text='Choose a cloud API, a local model server or your installed Codex CLI. Consumer chat subscriptions do not supply API credentials.\nKeys saved here are encrypted with Windows DPAPI for this Windows user. Nothing is included in the public repository.',wraplength=1050).pack(anchor='w',pady=8)
        self.settings_text = tk.StringVar()
        ttk.Label(p,textvariable=self.settings_text,wraplength=1000).pack(anchor='w',pady=16)
        self.button(p,'Configure AI and search',self.settings_form)
        self.button(p,'Test AI connection',self.test_ai)

    def settings_form(self):
        rows = self.store.list(self.pid,'settings')
        old = rows[0] if rows else {}
        fields = [('provider','Provider',tuple(PROVIDERS)),('model','Exact model ID','entry'),('endpoint','Base URL (blank = provider default)','entry'),('key','API key (blank = keep saved key)','secret'),('key_env','Or API-key environment variable','entry'),('clear_key','Delete saved AI key','bool'),('executable','Codex CLI executable (.exe)','entry'),('allow_ai','Allow profile/resume data to selected AI','bool'),('enable_web','Enable Brave web research + AI','bool'),('search_key','Brave API key (blank = keep)','secret'),('search_key_env','Or Brave-key environment variable','entry'),('clear_search','Delete saved search key','bool')]
        def save(v):
            changed = old.get('provider') != v['provider']
            if changed and v['endpoint'] == old.get('endpoint'):
                v['endpoint'] = ''
            if changed and v['key_env'] == old.get('key_env'):
                v['key_env'] = ''
            v['endpoint'] = v['endpoint'].strip() or PROVIDERS[v['provider']]
            if v['provider'] != 'Codex CLI':
                validate_url(v['endpoint'])
            v['encrypted_key'] = protect(v.pop('key')) if v['key'] else ('' if changed or v['clear_key'] else old.get('encrypted_key',''))
            v['search_key'] = protect(v['search_key']) if v['search_key'] else ('' if v['clear_search'] else old.get('search_key',''))
            v.pop('key',None); v.pop('clear_key',None); v.pop('clear_search',None)
            self.store.put(self.pid,'settings',v,old.get('id'))
            self.refresh()
        values = dict(old,key='',search_key='')
        Form(self,'AI and search settings',fields,values,save)

    def test_ai(self):
        config = self.flow.config(self.pid)
        from .ai import generate
        self.background(lambda:generate(config,'You are a connection test.','Reply with: Connection successful.'),'Testing AI connection')

    def build_profile(self):
        p = self.pages['Profile']
        ttk.Label(p,text='Your search, anywhere',font=('Segoe UI',16,'bold')).pack(anchor='w',pady=8)
        self.profile_text = tk.StringVar()
        ttk.Label(p,textvariable=self.profile_text,wraplength=1050).pack(anchor='w',pady=10)
        self.button(p,'Edit profile and search preferences',self.profile_form)
        ttk.Label(p,text='Use comma-separated keywords and locations. Leave locations empty to search anywhere.\nSalary categories compare annual base salary in the same currency; bonuses and equity are excluded. Unknown salary stays unknown.',wraplength=1050).pack(anchor='w',pady=18)

    def profile_form(self,new=False):
        old = {} if new or not self.pid else self.store.profile(self.pid)
        fields = [('name','Profile name','entry'),('contact','Contact information (optional)','text'),('facts','Verified experience / qualifications','text'),('keywords','Role / industry keywords (comma-separated)','entry'),('locations','Locations (blank = anywhere)','entry'),('currency','Target currency code','entry'),('minimum_base','Minimum annual base salary','entry'),('search_query','Optional custom web search query','entry')]
        def save(v):
            name = v.pop('name')
            v['minimum_base'] = float(v['minimum_base'] or 0)
            if v['minimum_base'] < 0:
                raise ValueError('Minimum salary cannot be negative.')
            v['currency'] = v['currency'].upper().strip() or 'USD'
            self.pid = self.store.save_profile(name,v,old.get('id'))
            self.refresh_profiles()
        Form(self,'New profile' if new else 'Edit profile',fields,dict(currency='USD',**old) if 'currency' not in old else old,save)

    def build_activity(self):
        p = self.pages['Activity']
        ttk.Label(p,text='Workflow history',font=('Segoe UI',16,'bold')).pack(anchor='w',pady=8)
        self.runtree = self.tree(p,('Task','Status','Started','Completed'))
        self.runtree.bind('<<TreeviewSelect>>',self.run_detail)
        self.runtext = tk.Text(p,height=12,wrap='word',font=('Segoe UI',10),state='disabled')
        self.runtext.pack(fill='x')

    def run_detail(self,*args):
        try:
            run = self.selected(self.runtree,'run')
        except ValueError:
            return
        self.runtext.configure(state='normal'); self.runtext.delete('1.0','end')
        self.runtext.insert('1.0',json.dumps(run,indent=2,ensure_ascii=False)); self.runtext.configure(state='disabled')

    def refresh_profiles(self):
        self.people = self.store.profiles()
        self.profiles['values'] = [p['name'] + ' [' + p['id'][:6] + ']' for p in self.people]
        if self.people:
            self.pid = self.pid or self.people[0]['id']
            self.profiles.current(next(i for i,p in enumerate(self.people) if p['id'] == self.pid))
        self.refresh()

    def switch_profile(self,*args):
        self.pid = self.people[self.profiles.current()]['id']
        self.refresh()

    def refresh_jobs(self):
        if not hasattr(self,'jobtree'):
            return
        selection = self.jobtree.selection()
        self.jobtree.delete(*self.jobtree.get_children())
        if not self.pid:
            return
        query = self.query.get().casefold()
        for job in self.store.list(self.pid,'job'):
            if query not in ' '.join(str(job.get(k,'')) for k in ('company','title','location')).casefold():
                continue
            salary = f"{job.get('currency','')} {job.get('salary_min') or '?'}–{job.get('salary_max') or '?'} ({job.get('salary_basis','unknown')})"
            self.jobtree.insert('','end',iid=job['id'],values=(job['company'],job['title'],job.get('location',''),salary,job.get('status','discovered'),job.get('availability','unverified')))
        if selection and self.jobtree.exists(selection[0]):
            self.jobtree.selection_set(selection[0])

    def refresh(self):
        self.refresh_jobs()
        for tree in (self.doctree,self.feedtree,self.runtree,self.companytree):
            tree.delete(*tree.get_children())
        if not self.pid:
            self.profile_text.set('Welcome. Create a profile to start your job search. No personal data is preloaded.')
            self.settings_text.set('No AI connection configured.')
            self.schedule_text.set('No schedule configured.')
            return
        for kind in ('resume','draft'):
            for r in self.store.list(self.pid,kind):
                self.doctree.insert('','end',iid=kind + ':' + r['id'],values=(kind.title(),r['label'],r['created'][:19],r.get('provider','') + ' ' + r.get('model',''),'Reviewed' if r.get('reviewed') else 'Needs review' if kind == 'draft' else 'Source'))
        for r in self.store.list(self.pid,'feed'):
            self.feedtree.insert('','end',iid=r['id'],values=(r['company'],r['type'],r['board']))
        for r in self.store.list(self.pid,'company'):
            self.companytree.insert('','end',iid=r['id'],values=(r['name'],r.get('industry',''),r.get('location',''),r.get('url',''),r.get('notes','')))
        for r in self.store.list(self.pid,'run')[:200]:
            self.runtree.insert('','end',iid=r['id'],values=(r['task'],r['status'],r.get('started',r['created'])[:19],r.get('ended','')[:19]))
        profile = self.store.profile(self.pid)
        self.profile_text.set('\n\n'.join(f'{k.replace("_"," ").title()}: {v}' for k,v in profile.items() if k != 'id'))
        conf = self.flow.config(self.pid)
        self.settings_text.set(f"Provider: {conf.get('provider','Not configured')}\nModel: {conf.get('model','Not configured')}\nEndpoint: {conf.get('endpoint','')}\nAI sharing: {'Enabled' if conf.get('allow_ai') else 'Off'}\nWeb discovery: {'Enabled' if conf.get('enable_web') else 'Off'}")
        schedules = self.store.list(self.pid,'schedule')
        self.schedule_text.set('No schedule configured.' if not schedules else f"Schedule: {'Enabled' if schedules[0].get('enabled') else 'Disabled'} | {schedules[0].get('time')} {schedules[0].get('timezone')} | Next UTC: {schedules[0].get('next_run','')}\nAt most {schedules[0].get('limit',3)} AI jobs per run. Drafts require current job approval.")

    def background(self,fn,label):
        if self.busy:
            raise ValueError('A task is already running. Check Activity before starting another.')
        self.busy = True
        self.status.set(label + '… You can continue browsing.')
        def work():
            try:
                self.events.put(('done',fn()))
            except Exception as exc:
                self.events.put(('error',str(exc)))
        threading.Thread(target=work,daemon=True).start()

    def poll(self):
        try:
            kind,value = self.events.get_nowait()
            self.busy = False
            self.status.set(('Completed: ' if kind == 'done' else 'Failed: ') + str(value))
            self.refresh()
            if kind == 'error':
                messagebox.showerror('Task failed',str(value))
        except queue.Empty:
            pass
        self.after(200,self.poll)

    def tick(self):
        if not self.busy:
            for profile in self.store.profiles():
                rows = self.store.list(profile['id'],'schedule')
                if not rows:
                    continue
                schedule = rows[0]
                if schedule.get('enabled') and schedule.get('next_run','9999') <= now():
                    schedule['last_attempt'] = now()
                    schedule['next_run'] = next_due(schedule)
                    self.store.put(profile['id'],'schedule',schedule,schedule['id'])
                    self.background(lambda p=profile['id'],s=schedule:self.flow.run(p,s),'Scheduled workflow: ' + profile['name'])
                    break
        self.after(30000,self.tick)

    def startup(self):
        if os.name != 'nt' or not getattr(sys,'frozen',False):
            raise ValueError('This option is available in the packaged Windows EXE.')
        folder = Path(os.environ['APPDATA']) / 'Microsoft/Windows/Start Menu/Programs/Startup'
        target = folder / 'JobTracker.lnk'
        if target.exists():
            if messagebox.askyesno('Windows startup','Remove JobTracker from Windows sign-in startup?'):
                target.unlink()
        elif messagebox.askyesno('Windows startup','Start JobTracker when you sign in to Windows? The app will remain open for scheduled work.'):
            # A script file avoids interpolating user paths into a shell command.
            import subprocess, tempfile
            script = 'Set s=CreateObject("WScript.Shell")\nSet l=s.CreateShortcut(WScript.Arguments(0))\nl.TargetPath=WScript.Arguments(1)\nl.Save\n'
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'shortcut.vbs'; path.write_text(script,encoding='ascii')
                subprocess.run(['cscript.exe','//Nologo',str(path),str(target),sys.executable],check=True,creationflags=subprocess.CREATE_NO_WINDOW)
        self.status.set('Windows sign-in launch: ' + ('enabled' if target.exists() else 'disabled'))

    def close(self):
        if self.busy:
            messagebox.showinfo('Task is running','Wait for the current task to finish before closing the app.')
            return
        self.destroy()

def main():
    import tempfile
    smoke = '--smoke-test' in sys.argv
    temporary = tempfile.TemporaryDirectory(prefix='jobtracker-frozen-') if smoke else None
    store = Store(temporary.name) if smoke else Store()
    lock = open(store.root / 'application.lock','a+b')
    if os.name == 'nt':
        import msvcrt
        if os.fstat(lock.fileno()).st_size == 0:
            lock.write(b'0'); lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:
            root = tk.Tk(); root.withdraw()
            messagebox.showinfo('JobTracker is already open','Use the existing JobTracker window for this data directory.')
            root.destroy(); lock.close()
            return
    # Holding the OS lock proves no other instance owns this data directory.
    with store.db() as c:
        c.execute('DELETE FROM leases')
    for profile in store.profiles():
        for run in store.list(profile['id'],'run'):
            if run.get('status') == 'running':
                run.update(status='interrupted',ended=now(),error='The previous application session ended before completion. Retry manually or wait for the next schedule.')
                store.put(profile['id'],'run',run,run['id'])
    try:
        app = App(store)
        if smoke:
            def report():
                app.update_idletasks()
                target = Path(sys.argv[sys.argv.index('--smoke-test')+1])
                target.write_text(json.dumps(dict(version=__version__,tabs=len(app.tabs.tabs()),profiles=len(store.profiles()),width=app.winfo_width(),height=app.winfo_height(),frozen=bool(getattr(sys,'frozen',False)))))
                app.destroy()
            app.after(1500,report)
        app.mainloop()
    finally:
        lock.close()
        if temporary:
            temporary.cleanup()
