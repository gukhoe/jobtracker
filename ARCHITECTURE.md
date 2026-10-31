# Architecture

`main.py` starts the native Tk event loop and holds a per-data-directory Windows file lock. There is no HTTP listener or fixed port.

- `store.py`: SQLite transactions, profile-scoped records, atomic job URL/source-key deduplication, job requirement hashes, immutable source resume versions, consistent database backups.
- `ai.py`: provider-independent `generate(config, system, prompt) -> str`, timeout/size-bounded HTTPS requests, redirect refusal, DPAPI storage, separate Codex executable adapter. Add a provider by adding its name/default endpoint and request/response mapping; add contract tests before enabling it.
- `research.py`: configurable company feeds, keyword/location matching, optional Brave discovery. Feed errors retain earlier records. No browser scraping or synthesized official-source verification.
- `workflow.py`: source collection, exact-source validation for AI research, document approval checks, generation deduplication, durable run history and a profile lease. It is injectable for tests. Source material is treated as untrusted data in prompts; AI output is never executed.
- `desktop.py`: English native forms, multi-profile UI, background worker queue, persistent timezone-aware scheduler. Tk widgets are touched only by the main thread. AI and networking run sequentially off the UI thread.

Research saves jobs before document work so partial results survive provider errors. Job approvals bind to the current requirements hash. Document identity includes task, profile, source version, job version and provider/model/endpoint. A new source version or changed job/profile creates another draft; completed drafts are not silently replaced. Scheduled processing skips already generated work to avoid starving later jobs.

The scheduler stores the next UTC occurrence calculated with IANA timezone data. It claims a due attempt before execution, advances to the next future occurrence, and records outcome separately. This prevents repeated catch-up on restart; failed attempts can be retried manually. Each profile has one schedule in the UI. Only one task runs per application instance. An OS lock prevents two packaged instances sharing a data directory; interrupted runs are marked on restart. This is a desktop scheduler, not a distributed job queue or Windows service.

No credentials, personal data or private legacy paths belong in this source tree. Future browser application adapters must add explicit review and final-submission confirmation and record actual receipt evidence. They must not reinterpret drafting approval as submission approval.
