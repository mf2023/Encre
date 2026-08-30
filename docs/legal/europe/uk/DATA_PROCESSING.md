# Data Processing Rules (United Kingdom)

**Last updated: 22 August 2026**
**Scope:** All Dunimd services — users in the United Kingdom
**Version:** This document is the sole applicable version. Where translated versions conflict, this English version prevails on matters governed by UK law.

> **Dunimd UK service documents (six-document set):**
> [Privacy Notice](PRIVACY.md) · [Terms of Service](TERMS.md) · [User Agreement](USER_AGREEMENT.md) · [Minors' Data Protection Rules](MINORS_PRIVACY.md) · [Content Guidelines](CONTENT_GUIDELINES.md) · [Data Processing Rules](DATA_PROCESSING.md)

---

## 1. Local-first declaration

Encre Agent keeps conversations, agent configurations, and generated content **on your device**. Cloud features are opt-in; without them we process only what is strictly necessary for accounts and licensing.

## 2. Data flow overview

| Flow | Destination | Default |
|---|---|---|
| Conversations and settings | Local device storage (AES-256-GCM) | Always local |
| Telemetry | Our infrastructure | **Off by default** |
| Hosted inference metadata | Our infrastructure | Only when hosted features are used |
| User-configured external AI providers | Directly from your device | Only if configured |

## 3. Per-service detail

- **Encre Agent desktop**: fully local unless cloud sync or hosted models are enabled
- **PiscesLx**: request metadata kept up to 30 days for abuse prevention, then deleted
- **Dunimd Enterprise/Cloud**: processing under a UK GDPR Art. 28-style processing agreement

## 4. Telemetry

Opt-in, documented, reviewable before activation; never includes prompt or response content. Cookies and similar storage technologies follow PECR as amended by the DUAA 2025 (which permits certain low-risk storage technologies without explicit consent); our non-essential cookies remain consent-based.

## 5. International transfers

Transfers use the ICO International Data Transfer Agreement (IDTA) or UK Addendum to EU SCCs, with transfer risk assessments, under the DUAA-simplified regime ("data protection test").

## 6. Security measures and retention

TLS 1.2+ in transit, AES-256-GCM at rest, least privilege, audit logging. Retention limited to purposes in the [Privacy Notice](PRIVACY.md). Breaches notified to the ICO within 72 hours where feasible.

## 7. Changes

Material changes announced at least **30 days** ahead via [dunimd.com](https://dunimd.com).

---

*These rules form part of the [User Agreement](USER_AGREEMENT.md). They are not legal advice.*
