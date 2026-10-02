# Giani source audit and verification notes

**Checked:** 3 October 2026. **Scope:** documentation review and external capability checks. No source-code audit, live account inspection, deployment, model execution or publish was performed.

## B0 — supplied project baseline

Source: `README(20261002-192238).md`, preserved unchanged as [BASELINE_README_2026-10-02.md](BASELINE_README_2026-10-02.md).

SHA-256: `49d9c9d496f8cae1a18ac49bc3074417aed59bcab19637116bdfc2ca6b85847a`

The update uses this attachment, not the earlier breast-pathology files in the conversation. Existing API/module names, workflows and configuration examples come from this baseline. Claims that tests passed or that an account was connected are reported historical results. They were not independently rerun here.

| Baseline section / original lines | Information retained | Qualification in updated README |
|---|---|---|
| Introduction, 1–18 | Giani, Mira, daily/weekly newsroom and separate Post Studio | Same product identity and two-pipeline framing |
| Included/status, 20–51 | React/FastAPI/SQLite, 77 backend and 11 frontend tests, connection and blockers | Source-reported implementation/status; not a new audit |
| Human control, 120–134 | Human editorial selection/angle, exact-revision review, video manual upload | Preserved as a non-negotiable product boundary |
| Research/video, 159–177 | RSS/HN, three-story daily/one-story deep dive, GPU handoff | Preserved; new features explicitly proposed |
| Posts/publishing, 197–241 | Current modules, placeholders, revision invalidation, database guard, capability media | Retained, with remote-timeout reconciliation proposed |
| Quick start and editorial rules, 282–352 | PowerShell commands and exact profile constraints | Retained; no migration of source code implied |
| Meta history, 393–435 | Account setup and historical token behavior | Marked historical; current Meta docs not successfully retrieved |
| Original test-post runbook, 457–490 | Raw API tunnel and reviewed first post | Replaced with a proposed media-only proxy example; original kept in archive |
| Deadlines, 492–501 | Token refresh estimate and stated Graph retirement date | Expiry/version must be checked; stated retirement date not independently verified |
| Tests/GPU/repository map, 503–556 | Test commands, T4/LatentSync caution and module paths | Retained with current upstream VRAM cross-check |

Line references describe the supplied source representation; the exact archived bytes are identified by the checksum above.

## Verified external sources

A successful documentation check is not an account entitlement, a license opinion, proof of compatibility, or a performance measurement. Sources establish only the scope stated below. Dates distinguish an explicit release entry from a page merely available at review time.

| Key | Primary source | Supported facts | Not established |
|---|---|---|---|
| E01 | [OpenAI API changelog][E01] | 8 September 2026 image-model releases; 29 September GPT-6.1 Sol API entry | Giani support, account access or newsroom accuracy |
| E02 | [OpenAI image-generation guide][E02] | Current image generation/editing model IDs and documented API roles | Perfect identity, typography, facts or endpoint compatibility with existing code |
| E03 | [Gemini API release notes][E03] | Dated TTS, text and image availability entries referenced in the model shortlist | User's quota, region access or measured cost/quality |
| E04 | [Gemini image-generation guide][E04] | Current image-model identifiers and reference/editing capabilities | Every model supports identical reference workflows or exact outputs |
| E05 | [AuK official repository][E05] | September 2026 release/deployment notes; speech generation/editing; MIT statement | Fits a specific laptop/T4, consistent voice identity or an unconditional speedup |
| E06 | [Qwen3-TTS official repository][E06] | January 2026 0.6B/1.7B release; voice-design/clone options; listed languages; Apache-2.0 repository license | Hindi/Punjabi support or rights to clone an arbitrary speaker |
| E07 | [IndicF5 model card][E07] | Hindi and Punjabi are explicitly supported; MIT metadata | Native-review quality, every accent or all upstream asset rights |
| E08 | [LatentSync repository][E08] | Official inference minimum: 18 GB for 1.6; 8 GB for 1.5 | Meets this project's complete worker memory/performance budget |
| E09 | [MuseTalk repository][E09] | Available lip-sync implementation and model documentation | Real-time speed or superior output on this deployment |
| E10 | [LangGraph persistence][E10] | Checkpoints/stores and persistent backends | Replaces application approvals or provides external exactly-once publication |
| E11 | [LangGraph interrupts][E11] | Pausing/resuming with saved state; pre-interrupt node code may run again | Human identity, authorization or replay-safe side effects without application controls |
| E12 | [C2PA specification 2.3][E12] | Signed provenance assertions, content bindings and trust model | Factual truth, platform retention or universal trust in self-signed credentials |
| E13 | [Remotion licensing][E13] | Organizational licensing distinction; page dated 2 October 2026 | Universally free use or this user's legal eligibility |
| E14 | [OpenTelemetry Python][E14] | Python telemetry instrumentation | Automatic provider billing, redaction or application-specific measurements |
| E15 | [pgvector repository][E15] | Vector search integrated with PostgreSQL | Better evidence retrieval for Giani without evaluation |
| E16 | [OWASP guidance][E16] | Indirect prompt-injection risks and layered defenses | Complete security from prompts, filters or a single guard model |
| E17 | [Docling documentation][E17] | Available document-conversion/processing toolkit | Accurate extraction of every uploaded paper, table or figure |
| E18 | [Caddy handle directive][E18]; [Caddy bind directive][E21] | Mutually exclusive routing/fallback semantics and explicit loopback binding | This example has been run, hardened or penetration-tested |
| E19 | [Cloudflare R2 guidance][E19] | Public delivery/custom-domain mechanisms and public-bucket implications | An automatically private entire bucket or successful Instagram fetch |
| E20 | [faster-whisper repository][E20] | Transcription implementation suitable for an existing caption/QA path | Error-free speech recognition or a full audio-quality certificate |

## Items deliberately left unresolved

### Meta / Instagram API

Attempts to retrieve the official Instagram Login/content-publishing documentation and Graph API version page returned fetch errors, including HTTP 429. The official Meta Postman surface returned a documentation shell, not substantive endpoint rules. These do not support a fresh verification of quota, token lifetime, format restrictions, current scopes or version-retirement dates.

Official URLs attempted, provided for operator verification:

- https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/content-publishing
- https://developers.facebook.com/docs/instagram-platform/content-publishing/
- https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/
- https://developers.facebook.com/docs/graph-api/changelog/versions

Accordingly, **100** remains a value reported by the application's 2 October status snapshot, not a universal or perpetual daily quota. The historical estimate around **18 October 2026** does not replace a live token-expiry check. The original **21 January 2027** Graph v21.0 retirement statement is retained only in the archive/history qualification, not asserted as verified.

### n8n scaling and FFmpeg filter details

The attempted queue-mode documentation path did not return a usable current guide. No new queue-mode configuration is prescribed. n8n's current preparation-only role comes from B0. The attempted FFmpeg filters page was also unavailable; this package retains the source-reported assembly path without introducing unverifiable filter-version claims or production command flags.

### Model and dependency licensing

Model-card or repository license labels are initial screening information. Inspect the precise checkpoint revision, code, tokenizer/vocoder/encoder dependencies, asset licenses, voice rights and hosting terms before commercial or organizational deployment. Remotion is not assumed universally free. The Giani repository's own license was not included and is not invented in this package.

### Source-code and account access

The three linked project specification files, actual Python/TypeScript source, dependency lockfiles, infrastructure configurations, account token and live services were not supplied. References to new tables/routes/configuration are proposals. The current source must be inspected before producing a migration or code patch.

## Change record for the generated documentation

The original README is preserved byte-for-byte. The replacement adds an audit-scope banner, proposed capabilities and target architecture, source-backed model candidates, explicit source-reported test/status language, a safer unexecuted media-only local-delivery example, and current verification caveats. It retains the existing editorial flows, commands, fictional-anchor identity and publishing boundaries.

The implementation plan and evaluation pack add design requirements, not claims that implementation has finished. JSON parsing and documentation-integrity checks on the generated package are distinct from running Giani's backend, frontend, rendering or publishing tests.

## Reference definitions

[E01]: https://developers.openai.com/api/docs/changelog "OpenAI API changelog"
[E02]: https://developers.openai.com/api/docs/guides/image-generation "OpenAI image-generation guide"
[E03]: https://ai.google.dev/gemini-api/docs/changelog "Gemini API release notes"
[E04]: https://ai.google.dev/gemini-api/docs/image-generation "Gemini image-generation guide"
[E05]: https://github.com/Tencent-Hunyuan/AuK "Tencent Hunyuan AuK repository"
[E06]: https://github.com/QwenLM/Qwen3-TTS "Qwen3-TTS repository"
[E07]: https://huggingface.co/ai4bharat/IndicF5 "AI4Bharat IndicF5 model card"
[E08]: https://github.com/bytedance/LatentSync "LatentSync official repository"
[E09]: https://github.com/TMElyralab/MuseTalk "MuseTalk official repository"
[E10]: https://docs.langchain.com/oss/python/langgraph/persistence "LangGraph persistence"
[E11]: https://docs.langchain.com/oss/python/langgraph/interrupts "LangGraph interrupts"
[E12]: https://spec.c2pa.org/specifications/specifications/2.3/specs/C2PA_Specification.html "C2PA specification 2.3, explicitly versioned reference"
[E13]: https://www.remotion.dev/docs/license/pricing "Remotion license and pricing"
[E14]: https://opentelemetry.io/docs/languages/python/ "OpenTelemetry Python documentation"
[E15]: https://github.com/pgvector/pgvector "pgvector official repository"
[E16]: https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html "OWASP prompt-injection prevention"
[E17]: https://docling-project.github.io/docling/ "Docling documentation"
[E18]: https://caddyserver.com/docs/caddyfile/directives/handle "Caddy handle directive"
[E19]: https://developers.cloudflare.com/r2/buckets/public-buckets/ "Cloudflare R2 public-bucket guidance"
[E20]: https://github.com/SYSTRAN/faster-whisper "faster-whisper official repository"

[E21]: https://caddyserver.com/docs/caddyfile/directives/bind "Caddy explicit listener binding"
