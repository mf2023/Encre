# סקירת עיבוד נתונים – מדינת ישראל | Data Processing Overview – State of Israel

עודכן לאחרונה：22 באוגוסט 2026 | Last updated：August 22, 2026

**Scope:** How data flows in our services for users in Israel. Where local law requires a Hebrew version, that version prevails.

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
- **PiscesLx:** TLS-encrypted requests processed in memory; metadata auto-deleted within 30 days.
- **Dunimd Enterprise:** governed by a customer processing agreement.
- **Chat integrations:** platform privacy terms apply to platform-side data.

## 4. Telemetry

Strictly opt-in; deactivating telemetry stops collection and deletes prior data.

## 5. International transfers

Transfers outside Israel rely on adequate destination protections or appropriate safeguards consistent with Privacy Protection Authority positions; see our global transfer standards.

## 6. Security and breach response

Aligned with the baseline expectations of the Data Security Regulations 5777-2017: TLS 1.2+ in transit, AES-256-GCM at rest, least-privilege access controls, event logging, and staff confidentiality. Incidents likely to impair privacy are notified to the **PPA and affected individuals without undue delay**, with incident records maintained.

## 7. Changes and contact

Material changes will be announced at least 30 days before taking effect. Contact: dunimd@outlook.com · dunimd.com

---

*מסמך זה מיועד למידע בלבד ואינו מהווה ייעוץ משפטי | This document is provided for information only and does not constitute legal advice.*
