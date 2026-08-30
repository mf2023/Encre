# Data Processing – Australia

**Last updated：August 22, 2026**

**Applicability：** This notice describes how Dunimd processes data in its services. For Australian users, this document is the sole applicable version.

> Related documents：[Privacy Policy](PRIVACY.md) · [Terms of Service](TERMS.md) · [User Agreement](USER_AGREEMENT.md) · [Minors' Privacy](MINORS_PRIVACY.md) · [Content Guidelines](CONTENT_GUIDELINES.md)

## Table of Contents

1. [Local-First Declaration](#1-local-first-declaration)
2. [Data Flows](#2-data-flows)
3. [Processing per Service](#3-processing-per-service)
4. [Telemetry](#4-telemetry)
5. [Overseas Disclosure](#5-overseas-disclosure)
6. [Security and Breach Response (NDB Scheme)](#6-security-and-breach-response-ndb-scheme)
7. [Changes and Contact](#7-changes-and-contact)

---

## 1. Local-First Declaration

1.1 Encre Agent is designed to run locally: agent definitions, prompts, responses, history, and integrations stay on your device.

1.2 Telemetry is off by default; prompts and responses are not stored by default.

1.3 Processing beyond your device occurs only when you enable optional cloud services.

## 2. Data Flows

| Data | Location | Retention |
|---|---|---|
| Agent configs, workflows | device only | until deleted |
| Conversation history | device only | user-controlled |
| API keys (third parties) | encrypted on device | until deleted |
| Cloud inference requests | deleted after processing | session |
| Service metadata | server-side | max. 30 days |
| Telemetry (opt-in) | server-side | max. 90 days |
| Account data (cloud services only) | server-side | until account deletion |

## 3. Processing per Service

3.1 **PiscesLx (hosted LLM):** requests travel over TLS, are processed transiently; metadata (timestamps, token counts, errors) auto-deletes after at most 30 days.

3.2 **Encre Agent Desktop/Framework:** no server-side processing; all data stays local.

3.3 **Dunimd Enterprise:** processed under contractual service terms aligned with Australian Privacy Principles.

3.4 **Chat platform integrations:** platform-side data is governed by each platform's policy; we process only what integration requires.

## 4. Telemetry

4.1 Telemetry is strictly opt-in: no diagnostics are sent without your express consent.

4.2 Disable anytime in settings; existing telemetry data is then deleted.

## 5. Overseas Disclosure

5.1 Primary processing occurs outside Australia only where necessary for optional cloud features.

5.2 For overseas disclosure we take reasonable steps under APP 8 — contractual safeguards requiring recipients to handle personal information consistently with the APPs.

## 6. Security and Breach Response (NDB Scheme)

6.1 Technical measures: TLS 1.2+ transport encryption, AES-256-GCM encryption at rest, least-privilege access.

6.2 Organisational measures: confidentiality undertakings, access logging, periodic reviews.

6.3 **Notifiable Data Breaches：** suspected breaches are assessed within 30 days. Where an eligible data breach is likely to result in serious harm, we notify the OAIC and affected individuals as soon as practicable.

## 7. Changes and Contact

7.1 Changes will be announced at least 30 days before taking effect.

7.2 Contact: dunimd@outlook.com · dunimd.com · Regulator: OAIC, oaic.gov.au

---

*This document is provided for information only and does not constitute legal advice.*
