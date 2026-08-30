# Dunimd Data Processing Overview — South Africa

**Last updated：August 22, 2026**

**Scope:** This overview describes how Dunimd processes data in its services for users located in the Republic of South Africa. For users in South Africa it is the sole applicable version.

> Related documents: [Privacy Notice](PRIVACY.md) · [Terms of Service](TERMS.md) · [User Agreement](USER_AGREEMENT.md) · [Minors' Privacy](MINORS_PRIVACY.md) · [Community Guidelines](CONTENT_GUIDELINES.md)

## Table of contents

1. [Local-first declaration](#1-local-first-declaration)
2. [Data flows](#2-data-flows)
3. [Processing by service](#3-processing-by-service)
4. [Telemetry](#4-telemetry)
5. [Cross-border transfers](#5-cross-border-transfers)
6. [Security and breach response](#6-security-and-breach-response)
7. [Changes and contact](#7-changes-and-contact)

---

## 1. Local-first declaration

Agent definitions, prompts, responses, chat history and integrations remain on your device. Telemetry is off by default. Prompts and responses are not stored by default. Processing beyond your device occurs only if you enable optional cloud services.

## 2. Data flows

| Data | Location | Retention |
|---|---|---|
| Agent configs, workflows | Device only | Until deletion |
| Conversation history | Device only | User-controlled |
| Third-party API keys | Encrypted on device | Until removal |
| Cloud inference requests | Server memory | Deleted after processing |
| Service metadata (timestamps, error codes) | Server-side | Up to 30 days |
| Telemetry (opt-in) | Server-side | Up to 90 days |
| Account data (cloud only) | Server-side | Until account deletion |

## 3. Processing by service

3.1 **PiscesLx (hosted LLM):** TLS-encrypted transport; requests processed in memory; metadata retained up to 30 days.

3.2 **Encre Agent Desktop/Framework:** no server-side processing.

3.3 **Dunimd Enterprise:** processing under an operator/processor agreement implementing POPIA s.20–21 duties.

## 4. Telemetry

Strictly opt-in. Disable anytime in settings; existing telemetry is deleted on opt-out.

## 5. Cross-border transfers

Transfers outside South Africa occur only under POPIA s.72 conditions: adequacy/binding rules/consent/necessity or other lawful grounds; special prior-authorisation cases under s.58 are respected.

## 6. Security and breach response

Technical measures: TLS 1.2+, AES-256-GCM at rest, least-privilege access. Organisational: confidentiality undertakings, access logging, periodic reviews.

**Breach notification:** where a compromise of personal information is likely to result in harm, we notify the **Information Regulator** and affected data subjects **as soon as reasonably possible** after discovery, with prescribed details (POPIA s.22); internal records of all security compromises are maintained for audit purposes.

## 7. Changes and contact

Changes are published at least 30 days before taking effect.

Contact: dunimd@outlook.com · dunimd.com · Regulator: Information Regulator (South Africa), inforegulator.org.za

---

*This document is provided for information purposes only and does not constitute legal advice.*
