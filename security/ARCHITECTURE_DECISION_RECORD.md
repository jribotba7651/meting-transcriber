# Architecture Decision Record: Remove Audio Recording

**Decision ID:** ADR-001
**Date:** 2025-02-12
**Status:** Accepted
**Decider:** Juan Ribot (Developer/Owner)

---

## Context

A comprehensive security audit (Phase 1: Static Analysis, Phase 5: Compliance & Legal Review) identified **3 CRITICAL compliance gaps** directly tied to the audio recording feature (WASAPI loopback capture via `audio_capture.py`):

| Finding | Severity | Issue |
|---------|----------|-------|
| C-001 | CRITICAL | No recording consent mechanism — violates two-party consent laws (CA, CT, FL, IL, MD, MA, MT, NH, PA, WA) and 18 U.S.C. § 2511 (federal wiretap statute) |
| C-002 | CRITICAL | No data retention / auto-deletion for recordings — violates GDPR Article 5(1)(e), PIPEDA Principle 4.5 |
| C-003 | CRITICAL | No privacy notice or disclaimer — violates GDPR Article 13, CCPA § 1798.100 |

Additionally, the audio recording behavior (system audio capture, loopback recording) closely resembles malware patterns and would significantly complicate Arctic Wolf EDR whitelisting.

## Decision

**Remove all audio recording capability from the application.** Convert from a "Meeting Transcriber" (records + transcribes) to a "Meeting Notes Assistant" (transcribes uploaded files + AI overlay for notes).

### What was removed
- `audio_capture.py` — entire WASAPI loopback audio capture module (318 lines)
- `PyAudioWPatch` dependency — Windows audio capture library
- Recording UI — device selector, Start/Stop Recording button, real-time transcription loop
- `buffer_duration` config setting

### What was kept
- File upload transcription — users voluntarily upload audio/video files they already have permission to use
- AI Overlay — local Ollama chat, screenshot OCR, clipboard monitoring
- Save/Clear/Always-on-top UI functionality
- All Whisper transcription engine code (for file processing)

## Rationale

1. **Eliminates all CRITICAL compliance findings** — 3 CRITICAL → 0 CRITICAL, 1 HIGH → 0 HIGH
2. **Removes wiretapping law exposure** — no live audio capture means no two-party consent requirement
3. **Simplifies Arctic Wolf whitelisting** — recording-like behavior was the primary concern for EDR false positives
4. **Reduces deployment blockers from 3 to 0** — the app can be deployed without mandatory legal review of consent mechanisms
5. **Preserves core value** — users can still transcribe meetings by uploading recordings they obtained with proper consent through other tools (Zoom, Teams, etc.)
6. **Shifts consent responsibility** — the user is responsible for having permission to use files they upload, rather than the app silently recording without consent

## Consequences

### Positive
- Zero CRITICAL compliance findings
- No wiretapping/consent legal exposure
- Simpler Arctic Wolf whitelisting process
- Smaller attack surface (no audio APIs, no PyAudioWPatch dependency)
- Estimated remediation effort reduced from 4-5 days (mandatory) to 2 days (recommended)

### Negative
- Users cannot transcribe meetings in real-time — they must upload recordings after the meeting
- Depends on users having access to meeting recordings from other tools (Zoom cloud recordings, Teams recordings, etc.)
- The original "live transcription" differentiator is lost

### Neutral
- Screen capture (OCR) remains — this captures the user's own screen, not audio, so two-party consent for recording does not apply. Corporate AUP review recommended.
- Clipboard monitoring remains — captures text the user explicitly copies

## Commit Reference

`2671584` — `refactor: remove audio recording, convert to notes-only assistant`
