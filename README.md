# JobTracker

A local Windows desktop app for researching jobs, tracking applications and preparing AI-assisted application documents. Built for any profession, industry, country or company.

**[Download the Windows EXE](https://github.com/gukhoe/jobtracker/releases/latest)** · [MIT license](LICENSE) · [Privacy](PRIVACY.md)

## Overview

JobTracker brings job discovery, company research, application tracking and resume preparation into one personal desktop workspace. Instead of maintaining separate spreadsheets, folders and AI conversations, you can keep opportunities, source resumes, generated drafts and workflow history together on your own computer.

The application starts with an empty workspace. You define your profile, experience, target roles, locations and salary preferences, then connect the AI provider you want to use. There are no built-in assumptions about your employer, profession, industry or country, and you can maintain separate profiles for different searches.

## Key features

- **Personal job database:** save opportunities, source links, job descriptions, salary ranges, application notes and follow-up dates.
- **Company research:** maintain company records, industries, locations, careers links and research notes.
- **Flexible AI connections:** use OpenAI, Claude, Gemini, Grok, local Ollama, an OpenAI-compatible endpoint or your separately installed Codex CLI.
- **Repeatable research:** collect public Lever and Greenhouse postings, or enable optional Brave Search and AI classification to discover additional leads.
- **Scheduled workflows:** choose weekdays, execution time, timezone, source resume and the number of AI jobs processed per run.
- **Resume and cover-letter drafts:** generate documents from your verified experience and the selected job requirements while keeping source resumes unchanged.
- **Human review and approval:** approve a job before tailored document generation, review generated text and record actual application evidence separately.
- **Local storage and backups:** retain your data in SQLite, back up your workspace and save API keys with Windows account-bound encryption.

## How the workflow fits together

**Set your preferences → research opportunities → review and approve a job → generate documents → review and export → apply on the official website → track the outcome.**

Research and document preparation can run on a schedule while the app is open. Newly discovered jobs are saved for review; approval is tied to the current job requirements, so a changed listing needs approval again. Each workflow records its outcome and any errors in Activity. The app assists with preparation and organization; final applications remain a human action.

## Who it is for

JobTracker is designed for individual job seekers who want an editable, local workspace and the freedom to choose their AI provider. You can use it for a focused search in one city, a remote-job search, a career change or opportunities across multiple regions and industries. It is a personal desktop application, rather than a shared recruiting system or a hosted multi-user service.

## Start

1. Download `JobTracker.exe` from Releases and run it. Python and a web server are not required.
2. Create a profile. Enter your own verified experience, target keywords, locations, currency and minimum annual base salary. Leave locations blank to search anywhere.
3. Import a source resume (TXT, DOCX or text-based PDF). Review extracted text. Scanned PDFs need OCR outside this app. Source text is immutable; import a new version to update it.
4. Add jobs manually, add company Lever/Greenhouse board slugs, or enable web discovery in **AI settings**.
5. Run research, review the opportunities, and **Approve for drafting** on a selected job.
6. Generate a fit assessment, tailored resume or cover letter. Review factual claims and export the result as TXT. AI output includes supporting notes and questions and is not a submission-ready PDF.
7. Open the official listing to apply. Record submission evidence and status in the app. The app does not submit applications or send emails.

The EXE is unsigned. Download only from this repository's releases and compare the published SHA-256 checksum. This is an initial release; keep backups of important documents.

## AI connections

| Choice | Interface | What you provide |
| --- | --- | --- |
| OpenAI / ChatGPT models | OpenAI Responses API | API key, exact available model ID |
| Claude | Anthropic Messages API | API key, exact model ID |
| Gemini | Google generateContent | API key, exact model ID |
| Grok | xAI Responses API | API key, exact model ID |
| Ollama | Native `/api/chat` | Running local server, installed model name |
| OpenAI-compatible | Chat Completions | Compatible base URL, model, optional key |
| Codex CLI | Your installed `codex.exe` | Executable path, existing sign-in, model access |

Consumer chat subscriptions and API billing are separate. The app does not embed browser chat websites or reuse their cookies. Codex CLI uses its own supported local sign-in; no credentials are copied or bundled. Other local servers (such as LM Studio) can use the compatible interface. A service with a different protocol needs another adapter; “any AI” does not mean every proprietary interface is automatically compatible.

Base URL examples: `https://api.openai.com/v1`, `https://api.anthropic.com/v1`, `https://generativelanguage.googleapis.com/v1beta`, `https://api.x.ai/v1`, `http://127.0.0.1:11434` (Ollama), `http://127.0.0.1:1234/v1` (compatible local server). The app adds the provider-specific path. Enter a real model ID available on your account; no model is silently substituted. HTTP is permitted only on loopback; other endpoints require HTTPS.

Saved API keys use Windows DPAPI, bound to the current Windows account. Alternatively, specify an environment variable name and restart the app after setting it. Never put keys in a profile, resume, job description, source file or Git commit. Changing a provider discards its saved key. Use **Test AI connection** for a small request; it can incur provider charges. No live paid provider calls are made by the test suite.

## Research and schedules

**Company feeds:** choose Lever or Greenhouse and supply the company name and its board slug from its careers URL. There are no preselected employers or geography restrictions. The app filters by comma-separated profile keywords and locations. Public feed presence is recorded as open at the check time; absence is not treated as a rejection or proof of closure. Salary stays unknown unless you enter and verify a base salary range. `meets` means its lower bound meets your target, `overlaps` means only its upper bound does. Different currencies are not converted.

**Open-web discovery:** configure your own Brave Search API key (or environment variable), enable web research and AI sharing. Each run searches your profile's query, sends up to ten search snippets to the selected AI for classification, and saves potential jobs. Only exact URLs returned by search are accepted. These are **unverified leads**: the app does not claim it fetched or verified the complete official job page. Open the source and enter the verified job description and salary before approving resume generation. Search terms go to Brave; snippets go to the chosen AI. You can use Ollama for the AI step, but web search still uses Brave.

**Scheduled pipeline:** choose weekdays, a 24-hour time, IANA timezone, source resume and a limit of 1–10 AI jobs per run. Timezones use IANA data and honor daylight saving changes. A run collects matching opportunities, optionally assesses fit, then drafts resumes only for approved current job versions. Unapproved jobs can receive assessments, never application-document drafts. Changed requirements invalidate approval. Identical documents are reused; pending jobs advance on later runs. Submitted/interview/closed applications are excluded from automatic document preparation.

Schedules are off by default and require the app to remain open. Windows must be awake and signed in. The **Launch at Windows sign-in** option adds/removes a shortcut to this EXE; keep it in a stable folder. A missed run executes once when the app next runs, rather than replaying every missed occurrence. Runs are sequential, bounded and recorded in Activity as succeeded, partial, failed or interrupted. Failures are not marked complete. The next scheduled attempt remains scheduled; use **Run full workflow now** to retry sooner. Closing is blocked while a task runs. There is no background Windows service, automatic wake-up, or email monitor in this version.

AI can incur charges on every configured run. Explicit AI sharing consent and schedule settings authorize sending the selected profile, source resume and job to your provider. For private/local work use Ollama and disable web discovery. Output always needs human review. Approval is for document drafting, not final application submission.

## Storage and backups

- Default: `%LOCALAPPDATA%\JobTracker\tracker.sqlite3`.
- Immutable source text: `%LOCALAPPDATA%\JobTracker\documents\<profile-id>\`.
- AI drafts and run logs: the SQLite database.
- Backups: `%LOCALAPPDATA%\JobTracker\backups\` (automatic after a research workflow, or use **Back up database**).
- Optional `JOBTRACKER_DATA_DIR` overrides the complete storage directory. Each directory has a single-instance lock.

Backups contain personal data and DPAPI-encrypted keys; protect them as carefully as the live database. Keys cannot generally be decrypted on a different Windows account. Backups are not rotated automatically. To restore, close the app, preserve the current data folder, and replace `tracker.sqlite3` with your backup in a clean data folder (no old `-wal`/`-shm` files). Resume text also exists in the database; copy `documents/` if you need the original internal TXT files. Profiles isolate records within the app; they are not Windows security accounts or encryption boundaries.

The earlier personal web tracker is separate. This public app neither discovers nor imports a user's private legacy database automatically. No resume, application history, email, private database or credentials are included in this repository or release.

## Develop and build

Windows x64, Python 3.11:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe main.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/collect_licenses.py
.\scripts\build.ps1
```

Output: `dist/JobTracker.exe`. GitHub Actions runs tests and builds an EXE artifact. The test suite uses synthetic data and fake providers. See [architecture](ARCHITECTURE.md) for extension points. Do not check a real database, provider key, resume, `.env` or build environment into Git. Exports are intentional local user actions.

## License

Application source: MIT, copyright 2026 gukhoe. MIT is a license the copyright holder applies, not a certificate to obtain. Keep its copyright and permission notice with redistributed copies. Third-party runtimes retain their licenses; [notices](THIRD_PARTY_NOTICES.txt) and `licenses/` accompany the EXE. PyInstaller's bootloader exception permits bundling this MIT application. No AI SDKs, weights or provider accounts are distributed. Third-party services, job content and user documents are outside the application's MIT license.
