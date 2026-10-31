# Privacy and data handling

JobTracker has no telemetry, hosted account, shared database, analytics or advertising. It does not read Gmail, browser sessions or other applications. New installs start empty.

Personal profiles, source resume text, AI drafts, application notes and workflow logs are stored in your local data directory. SQLite and document files are not encrypted; Windows account permissions and disk encryption protect them. Saved API keys are DPAPI-encrypted on Windows. Profile separation is an application feature, not a security boundary between people sharing a Windows account.

Enabling AI data sharing allows selected resume text, verified profile facts/contact details and job details to be sent to your configured provider for assessments and document drafts. The connection test sends only fixed test text. Cloud providers apply their own retention and billing terms. Ollama can keep inference local when its endpoint and model are local. Codex CLI runs through your separately installed executable and its supported sign-in/configuration.

Feed refresh contacts public Lever/Greenhouse APIs. Optional Brave web discovery sends your search query to Brave and search snippets to your AI provider. Search results are untrusted leads. No automatic application submission, mail sending or email sync is implemented.

Backups include personal data and encrypted keys. To remove your data, close JobTracker, remove any sign-in shortcut you enabled, and delete the data directory and its backups. Exported files and third-party provider data must be removed separately. Never attach real databases or credentials to public issues.
