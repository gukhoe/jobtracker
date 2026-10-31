# JobTracker

<!-- impeccable:product-schema 1 -->

## Platform

Windows native desktop (the skill's web/ios/android taxonomy does not cover this platform).

## Stack

Confirmed by the user: Python native desktop application packaged as a Windows EXE. SQLite, Tkinter and standard-library networking minimize runtime dependencies. No localhost web server.

## Users

Individual job seekers in any location, industry or profession. Each user supplies their own profile, resumes, search preferences and AI connections.

## Product Purpose

Research and retain job opportunities, track applications and generate reviewable resume drafts from verified experience. Run these steps on a user-selected schedule with visible results and failures.

## Operating Context

Local Windows storage; public company feeds and optional web-search service; user-configured cloud or local AI. The app must be running for its scheduler. Optional Windows sign-in launch supports continued operation.

## Capabilities and Constraints

English interface and documentation. Multiple profiles. Provider adapters for OpenAI, Anthropic, Gemini, xAI, Ollama, OpenAI-compatible endpoints and existing Codex CLI. User approval gates resume generation; submitting an application requires a separate human action. Preserve source resumes and historical drafts. Never include the author's private tracker data in the public repository.

## Product Principles

- Local data belongs to the user.
- Sources and timestamps accompany opportunities.
- AI output is a draft, never employment evidence.
- Failed or interrupted work stays visible and is not reported as success.
