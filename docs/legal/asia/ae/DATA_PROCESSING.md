# نظرة عامة على معالجة البيانات – دولة الإمارات العربية المتحدة | Data Processing Overview – United Arab Emirates

آخر تحديث：22 أغسطس 2026 | Last updated：August 22, 2026

**Scope:** How data flows in our services for users in the United Arab Emirates. Where local law requires an Arabic version, that version prevails.

> Related documents: [Privacy Notice](PRIVACY.md) · [Terms](TERMS.md) · [User Agreement](USER_AGREEMENT.md) · [Minors Privacy](MINORS_PRIVACY.md) · [Content Guidelines](CONTENT_GUIDELINES.md)

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

Agent definitions, prompts, responses, history, and integration credentials stay on your device by default. Telemetry is opt-in only. Nothing is stored server-side by default.

## 2. Data flows

| Data | Location | Retention |
|---|---|---|
| Agent configs, workflows | Device only | Until deletion |
| Conversation history | Device only | User-controlled |
| API keys (third-party providers) | Encrypted on device | Until deletion |
| Cloud inference requests | Deleted after processing | Session |
| Service metadata | Server-side | Max 30 days |
| Telemetry (opt-in) | Server-side | Max 90 days |
| Account data | Server-side | Until account deletion |

## 3. Processing per service

- **Encre Agent Desktop/Framework:** no server-side processing.
- **PiscesLx:** TLS-encrypted requests processed in memory; metadata (timestamps, token counts, errors) auto-deleted within 30 days.
- **Dunimd Enterprise:** governed by a customer processing agreement.
- **Chat integrations:** platform privacy terms apply to platform-side data.

## 4. Telemetry

Strictly opt-in; deactivating telemetry stops collection and deletes prior data.

## 5. International transfers

Primary processing occurs outside the UAE only with appropriate safeguards recognized under the PDPL framework — principally standard contractual clauses and comparable contractual protections — described in detail in this document's global standards section.

## 6. Security and breach response

TLS 1.2+ in transit; AES-256-GCM at rest; least-privilege access controls; staff confidentiality. Breaches likely to cause risk are notified to the competent authority and affected individuals without undue delay.

## 7. Changes and contact

Material changes will be announced at least 30 days before taking effect. Contact: dunimd@outlook.com · dunimd.com

---

*هذا المستند لأغراض المعلومات فقط ولا يشكل استشارة قانونية | This document is provided for information only and does not constitute legal advice.*
