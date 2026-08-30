# Dunimd Data Processing Overview — United States

**Last updated: August 22, 2026**

**Scope:** This overview describes how Dunimd processes data across its services for U.S. users. This is the sole applicable version for U.S. users.

> Related documents: [Privacy Notice](PRIVACY.md) · [Terms of Service](TERMS.md) · [User Agreement](USER_AGREEMENT.md) · [Minors' Privacy](MINORS_PRIVACY.md) · [Content Guidelines](CONTENT_GUIDELINES.md)

## Table of Contents

1. [Local-First Declaration](#1-local-first-declaration)
2. [Data Flows](#2-data-flows)
3. [Processing per Service](#3-processing-per-service)
4. [Telemetry](#4-telemetry)
5. [International Transfers and EO 14117](#5-international-transfers-and-eo-14117)
6. [Security and Breach Response](#6-security-and-breach-response)
7. [Changes and Contact](#7-changes-and-contact)

---

## 1. Local-First Declaration

1.1 Encre Agent is designed to run locally: agent definitions, prompts, responses, chat history, and integration credentials stay on your device.

1.2 Telemetry defaults to off. Prompts and responses are not stored by us by default.

## 2. Data Flows

| Data | Location | Retention |
|---|---|---|
| Agent configs, workflows | Device only | Until deletion |
| Conversation history | Device only | User-controlled |
| Third-party API keys | Encrypted device storage | Until deletion |
| Cloud inference requests | Server memory | Deleted after response |
| Service metadata (timestamps, errors) | Server-side | Max 30 days |
| Telemetry (opt-in) | Server-side | Max 90 days |
| Account data (cloud only) | Server-side | Until account deletion, plus statutory holds |

## 3. Processing per Service

3.1 **PiscesLx:** requests travel over TLS and are processed in memory; metadata (timestamp, token count, error status) auto-deletes within 30 days.

3.2 **Encre Agent Desktop/Framework:** no server-side processing; all data stays local.

3.3 **Enterprise deployments:** governed by a data processing agreement reflecting CCPA service-provider terms (Cal. Civ. Code § 1798.140(ag)) and state equivalents.

3.4 **Chat-platform integrations:** each platform's privacy policy governs platform-side data; we process only what integration requires.

## 4. Telemetry

4.1 Opt-in only: no diagnostic data leaves your device before explicit consent.

4.2 Disable anytime in settings; previously collected telemetry is deleted on request.

## 5. International Transfers and EO 14117

5.1 Primary processing occurs in the United States.

5.2 Consistent with Executive Order 14117 and 28 C.F.R. Part 202, we screen against covered data transactions involving bulk U.S. sensitive personal data with countries of concern and structure vendor relationships accordingly.

5.3 EU/UK data flows rely on SCCs (Decision (EU) 2021/914) or UK IDTA; see regional notices in this repository.

## 6. Security and Breach Response

6.1 Technical measures: TLS 1.2+ transport encryption; AES-256-GCM storage encryption; least-privilege access controls.

6.2 Organizational measures: confidentiality obligations, access logging, periodic reviews; vulnerability disclosure per SECURITY.md at the repository root.

6.3 **Breach notification:** we notify affected individuals without unreasonable delay and within the shortest applicable state deadline (states impose outer limits from ~30 days, e.g., Colorado and Florida, up to 90 days elsewhere, with attorney-general notification at various thresholds).

## 7. Changes and Contact

7.1 Changes are announced at least 30 days before taking effect.

7.2 Contact: dunimd@outlook.com · dunimd.com.

---

*This document is provided for information only and does not constitute legal advice.*
