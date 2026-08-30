# Data Processing Notice — New Zealand

**Last updated：22 August 2026**

**Scope:** How Dunimd processes data across its services for New Zealand users. This is the sole applicable version.

> Related documents: [Privacy Statement](PRIVACY.md) · [Terms of Service](TERMS.md) · [User Agreement](USER_AGREEMENT.md) · [Minors' Privacy](MINORS_PRIVACY.md) · [Content Guidelines](CONTENT_GUIDELINES.md)

## Contents

1. [Local-First Declaration](#1-local-first-declaration)
2. [Data Flows](#2-data-flows)
3. [Processing by Service](#3-processing-by-service)
4. [Telemetry](#4-telemetry)
5. [Offshore Transfers](#5-offshore-transfers)
6. [Security and Breach Response](#6-security-and-breach-response)
7. [Changes and Contact](#7-changes-and-contact)

---

## 1. Local-First Declaration

1.1 Encre Agent keeps agent definitions, prompts, responses and history on your device by default.

1.2 Telemetry is off by default; prompts and responses are not stored server-side unless a cloud feature requires it.

## 2. Data Flows

| Data | Location | Retention |
|---|---|---|
| Agent configs, workflows | device only | until deletion |
| Conversation history | device only | user-controlled |
| API keys (third-party providers) | encrypted on device | until deletion |
| Cloud inference requests | deleted after processing | session |
| Service metadata (timestamps, error codes) | server-side | max 30 days |
| Telemetry (opt-in only) | server-side | max 90 days |
| Account data (cloud only) | server-side | until account deletion, plus legal holds |

## 3. Processing by Service

3.1 **PiscesLx (hosted LLM):** TLS-encrypted requests processed in memory; metadata retained up to 30 days then purged automatically.

3.2 **Encre Agent Desktop/Framework:** no server-side processing at all.

3.3 **Chat-platform integrations:** each platform's own policy governs platform-side data; we process only what integration requires.

3.4 **Enterprise:** processing under a written processor agreement with the customer.

## 4. Telemetry

4.1 Opt-in only. You can disable telemetry at any time in settings; existing records are deleted on disable.

## 5. Offshore Transfers

5.1 Where information must be sent offshore, we take reasonable steps to ensure the recipient is subject to comparable safeguards consistent with IPP12 of the Privacy Act 2020, including contractual commitments aligned with recognised international frameworks.

## 6. Security and Breach Response

6.1 Technical measures: TLS 1.2+ in transit, AES-256-GCM at rest, least-privilege access.

6.2 Organisational measures: confidentiality undertakings, access logging, periodic reviews.

6.3 **Notifiable breaches:** where a privacy breach causes serious harm or is likely to do so, we notify the Office of the Privacy Commissioner and affected individuals as soon as practicable, following the Privacy Act 2020 Part 6 assessment framework; internal incident records are maintained for review.

## 7. Changes and Contact

7.1 Material changes are published at least 30 days before they take effect.

7.2 Contact: dunimd@outlook.com · dunimd.com · Regulator: Office of the Privacy Commissioner, privacy.org.nz

---

*This document is provided for information only and does not constitute legal advice.*
