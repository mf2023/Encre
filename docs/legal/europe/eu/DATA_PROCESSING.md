# Data Processing Rules (European Union / EEA)

**Last updated: 22 August 2026**
**Scope:** All Dunimd services — users in the European Union and the European Economic Area (EEA)
**Version:** This document is the sole applicable version. Where translated versions conflict, this English version prevails on matters governed by EU law.

> **Dunimd EU/EEA service documents (six-document set):**
> [Privacy Notice](PRIVACY.md) · [Terms of Service](TERMS.md) · [User Agreement](USER_AGREEMENT.md) · [Minors' Data Protection Rules](MINORS_PRIVACY.md) · [Content Guidelines](CONTENT_GUIDELINES.md) · [Data Processing Rules](DATA_PROCESSING.md)

---

## 1. Local-first declaration

Encre Agent is designed so that conversations, agent configurations, and generated content remain **on your device**. Cloud features are opt-in. Unless you enable them, we process no personal data beyond what is strictly necessary to operate accounts and licensing.

## 2. Data flow overview

| Flow | Destination | Default |
|---|---|---|
| Conversations and settings | Local device storage (AES-256-GCM) | Always local |
| Telemetry | Our infrastructure | **Off by default** |
| Hosted inference metadata (timestamps, model ID, token counts, latency) | Our infrastructure | Only when hosted features are used; prompts/responses not stored by default |
| User-configured external AI providers | Directly from your device to that provider | Only if you configure them |

## 3. Per-service detail

- **Encre Agent desktop**: fully local unless cloud sync or hosted models are enabled
- **PiscesLx (LLM hosting)**: request metadata retained for up to 30 days for abuse prevention, then deleted
- **Dunimd Enterprise/Cloud**: processing under a data processing agreement per GDPR Art. 28

## 4. Telemetry

Telemetry is opt-in, documented, and reviewable before activation. It never includes prompt or response content.

## 5. Cross-border transfers

Transfers outside the EEA occur only with an adequacy decision (GDPR Art. 45) or Standard Contractual Clauses (Implementing Decision (EU) 2021/914) plus transfer impact assessments. Hosting locations are disclosed at point of collection where relevant.

## 6. Security measures and retention

- TLS 1.2+ in transit; AES-256-GCM at rest; least-privilege access control; audit logging
- Retention limited to the purposes of the [Privacy Notice](PRIVACY.md); billing records kept as long as tax law requires
- Breach notification within 72 hours to the competent supervisory authority (Art. 33)

## 7. Changes

Material changes are announced at least **30 days** in advance via [dunimd.com](https://dunimd.com).

---

*These rules form part of the [User Agreement](USER_AGREEMENT.md). They are not legal advice.*
