# Data Processing Overview — Egypt / معالجة البيانات —— مصر

**Last updated：August 22, 2026** · **آخر تحديث：22 أغسطس 2026**

**Scope:** This overview explains how Dunimd processes data in its services for users in Egypt. Where local law requires an Arabic version, the Arabic version prevails. Sole applicable version for Egypt.

> Related documents: [Privacy Notice](PRIVACY.md) · [Terms of Service](TERMS.md) · [User Agreement](USER_AGREEMENT.md) · [Children's Privacy](MINORS_PRIVACY.md) · [Content Guidelines](CONTENT_GUIDELINES.md)

## Contents

1. [Local-First Declaration](#1-local-first-declaration)
2. [Data Flows](#2-data-flows)
3. [Per-Service Processing](#3-per-service-processing)
4. [Telemetry](#4-telemetry)
5. [International Transfers](#5-international-transfers)
6. [Security and Incident Reporting](#6-security-and-incident-reporting)
7. [Changes and Contact](#7-changes-and-contact)

---

## 1. Local-First Declaration

Agent definitions, prompts, responses, chat histories and integrations remain on your device by default. Telemetry is off by default; prompts/responses are not stored by default; no training without explicit consent.

## 2. Data Flows

| Data | Location | Duration |
|---|---|---|
| Agent configs, workflows | Device only | Until deletion |
| Conversation history | Device only | User-controlled |
| Third-party API keys | Encrypted on device | Until deletion |
| Cloud inference requests | Deleted after processing | Session only |
| Service metadata | Server-side | Max. 30 days |
| Telemetry (opt-in) | Server-side | Max. 90 days |
| Account data | Server-side | Until deletion |

## 3. Per-Service Processing

PiscesLx inference: TLS transport, in-memory processing, metadata max. 30 days then auto-deletion. Encre Agent Desktop/Framework: no server-side processing. Enterprise: contractual processing terms per agreement. Chat integrations: platform-side data governed by platform policies.

## 4. Telemetry

Strictly opt-in; disable anytime; collected telemetry deleted upon opt-out.

## 5. International Transfers

Core processing happens locally in Egypt. Any cross-border transfer of personal data follows Personal Data Protection Law No. 151 of 2020 requirements — including approval mechanisms administered by the competent authority as they become operational — plus contractual safeguards.

## 6. Security and Incident Reporting

TLS 1.2+, AES-256-GCM at rest, least privilege, logging, confidentiality undertakings. Breaches are reported without undue delay to affected individuals and the Personal Data Protection Center (MCIT), consistent with the PDPL and any timelines set by forthcoming executive regulations.

## 7. Changes and Contact

Announced ≥30 days ahead. Contact: dunimd@outlook.com · dunimd.com · Authority: PDPC/MCIT, mcit.gov.eg

للاستفسارات: dunimd@outlook.com

---

*Informational only; not legal advice.*
