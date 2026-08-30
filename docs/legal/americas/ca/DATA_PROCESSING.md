# Data Processing Overview — Canada

**Last updated: August 22, 2026**

**Scope:** How Dunimd services process data for users in Canada (PIPEDA + Quebec Law 25). Sole applicable version for Canadian users.

> Related documents: [Privacy Policy](PRIVACY.md) · [Terms of Service](TERMS.md) · [User Agreement](USER_AGREEMENT.md) · [Minors' Privacy](MINORS_PRIVACY.md) · [Content Guidelines](CONTENT_GUIDELINES.md)

## Table of contents

1. [Local-first declaration](#1-local-first-declaration)
2. [Data flows](#2-data-flows)
3. [Processing per service](#3-processing-per-service)
4. [Telemetry](#4-telemetry)
5. [International transfers](#5-international-transfers)
6. [Security and breach response](#6-security-and-breach-response)
7. [Changes and contact](#7-changes-and-contact)

---

## 1. Local-first declaration

Agent definitions, prompts, responses, history, and integrations stay on your device. Telemetry is opt-in only. Prompts/responses are not stored by default.

## 2. Data flows

| Data | Location | Retention |
|---|---|---|
| Agent configs, workflows | Device only | Until deleted |
| Conversation history | Device only | User-controlled |
| Third-party API keys | Encrypted on device | Until deleted |
| Inference requests (cloud) | Processed in memory | Session only |
| Service metadata (timestamps, error codes) | Server | Max 30 days |
| Telemetry (opt-in) | Server | Max 90 days |
| Account data (cloud services only) | Server | Until account deletion |

## 3. Processing per service

3.1 **PiscesLx:** TLS-encrypted requests processed in memory; metadata (timestamp, token counts, errors) auto-deleted after 30 days.

3.2 **Desktop/Framework:** No server-side processing.

3.3 **Enterprise:** Governed by customer agreements incorporating PIPEDA accountability terms; for Quebec customers, contract terms per P-39.1 s. 18 (mandatary duties).

3.4 **Chat integrations:** Platform policies govern platform-side data; we process only what integration requires.

## 4. Telemetry

Opt-in only; disable anytime in settings — new collection stops immediately and existing data is deleted.

## 5. International transfers

5.1 Primary processing occurs outside Canada only where you enable cloud features.

5.2 Before transferring personal information out of Quebec, we complete and document a **privacy impact assessment** (P-39.1 s. 17), considering sensitivity, purposes, receiving-jurisdiction protections, and contractual safeguards.

5.3 Processors abroad operate under contracts implementing PIPEDA accountability; where EEA/UK/Swiss rules attach to specific flows, SCCs/IDTA/adequacy instruments apply.

## 6. Security and breach response

6.1 Measures: TLS 1.2+, AES-256-GCM at rest, least privilege, staff confidentiality, access logging.

6.2 Breach procedure:

- assess **real risk of significant harm (RROSH)** using sensitivity + probability-of-misuse factors;
- if RROSH: report to OPC as soon as feasible; notify individuals as soon as feasible (directly where possible); notify other organizations able to mitigate harm;
- Quebec incidents with risk of injury: notify CAI and affected persons as quickly as possible;
- maintain a register of **all** breaches for 24 months (PIPEDA s. 10.2).

## 7. Changes and contact

Announced ≥30 days ahead. Contact: dunimd@outlook.com · dunimd.com

---

*This document is provided for information purposes only and does not constitute legal advice.*
