# Minors' Privacy and Personal Information Protection

**Last updated: 2026-06-21**
**Scope:** Global — applies to all users of Dunimd Services, with specific protections for minors.

This document describes how Dunimd protects the personal information of children and minors. It supplements the [Privacy Policy](PRIVACY.md), the [User Agreement](USER_AGREEMENT.md), and the [Content Guidelines](CONTENT_GUIDELINES.md).

If you are in the **People's Republic of China**, the PRC-specific counterpart at [`MINORS_PRIVACY_CN.md`](MINORS_PRIVACY_CN.md) supplements this one for the Chinese statutory framework.

---

## Table of Contents

1. [Why This Document Exists](#1-why-this-document-exists)
2. [Who Counts as a Minor](#2-who-counts-as-a-minor)
3. [What We Collect](#3-what-we-collect)
4. [Lawful Basis and Parental Consent](#4-lawful-basis-and-parental-consent)
5. [Where Data Is Stored](#5-where-data-is-stored)
6. [Security](#6-security)
7. [Sharing and Disclosure](#7-sharing-and-disclosure)
8. [Rights of Parents and Guardians](#8-rights-of-parents-and-guardians)
9. [Age-Appropriate Design](#9-age-appropriate-design)
10. [Breach Notification](#10-breach-notification)
11. [Updates](#11-updates)
12. [Contact](#12-contact)
13. [Definitions](#13-definitions)

---

## 1. Why This Document Exists

Minors are entitled to special protection under most privacy and data-protection regimes worldwide. This document explains what Dunimd does to meet that obligation.

It covers:

- The age threshold that triggers these protections.
- The categories of personal information Dunimd collects from minors.
- How Dunimd obtains verifiable parental consent where required.
- The enhanced rights parents and guardians hold over minor children's data.
- The additional safeguards applied to minor children's data.

Where Dunimd Services are not directed to minors, this document also explains what we do if we learn that a minor is using a Service without appropriate consent.

---

## 2. Who Counts as a Minor

The age threshold varies by jurisdiction. Dunimd applies the **highest applicable threshold** for each user:

| Jurisdiction | Age of digital consent |
|---|---|
| **PRC** | 14 (《个人信息保护法》 Art. 31) |
| **EU/EEA** (GDPR Art. 8) | 16 by default, member states may lower to 13 |
| **UK** | 13 (UK GDPR) |
| **United States — COPPA** | 13 |
| **United States — state laws** | 13–18 depending on state |
| **Canada (PIPEDA)** | 13 in most provinces |
| **Australia (Privacy Act)** | 15 (under the Online Safety standards) |
| **Japan (APPI)** | 18 (with consent rules for minors 13-17) |
| **South Korea (PIPA)** | 14 |
| **India (DPDPA)** | 18 |
| **Brazil (LGPD)** | 18 (with 13+ requiring parental consent for digital services) |
| **Other** | The applicable age of digital consent under local law |

When Dunimd cannot determine a user's age with reasonable certainty, we treat the user as a minor for protective purposes.

---

## 3. What We Collect

### 3.1 Information Dunimd Collects Directly

| Category | Examples | Why |
|---|---|---|
| **Account / Configuration** | Username, role, language | To operate the Service |
| **Customer Content** | Prompts, files, conversation history | To deliver the Service to the user |
| **Authentication** | API keys, tokens | To connect to configured AI backends |
| **Device / environment** | OS, app version, locale | Compatibility, security, support |
| **Usage** | Feature usage, session duration | Service improvement, billing |

### 3.2 What Dunimd Does NOT Collect

By default, Dunimd does not knowingly collect from minors:

- Real name, home address, school name, or contact information unless required for a specific Service (e.g. Enterprise).
- Biometric data.
- Precise geolocation.
- Browsing history outside Dunimd Services.
- Contacts, calendar, microphone, or camera content — unless a specific feature requires it and obtains separate consent.

### 3.3 Local-First Services

Most Encre features are **local-first**: prompts, files, and outputs stay on the user's device. Where this is true, Dunimd does not receive the minor's data at all. The protections in this document apply primarily to hosted features (Dunimd Cloud, hosted PiscesLx inference, etc.).

### 3.4 Sensitive Personal Information

Minor's personal information is treated as sensitive under most jurisdictions. Dunimd only processes it where there is a specific lawful purpose, with appropriate safeguards and (where required) parental consent.

---

## 4. Lawful Basis and Parental Consent

### 4.1 Lawful Basis

Where Dunimd processes minor's personal information, the lawful basis is one of:

- **Verifiable parental consent** (US COPPA, EU GDPR Art. 8, PRC PIPL Art. 31, etc.).
- **Vital interests** — protection of the minor's safety in an emergency.
- **Legal obligation** — compliance with applicable law.
- **Performance of a contract** requested by the parent/guardian.

For Services that are local-first or where Dunimd does not collect personal information from the minor, no parental consent is needed for the absent processing.

### 4.2 Verifiable Parental Consent Methods

Where parental consent is required, Dunimd uses at least one of the following methods to verify it:

- **Signed consent form** returned by the parent/guardian (electronic or physical).
- **Payment verification** — using a credit card or other payment method that reliably identifies the parent.
- **Government-ID verification** — only where strictly necessary and proportionate.
- **Video verification** — a recorded consent session.
- **Knowledge-based authentication** — answering questions that a parent would know.
- **Other method** that meets the FTC COPPA "verifiable parental consent" standard or equivalent in other jurisdictions.

For Services where the risk profile is low (e.g. local-only use, no personal data collection), Dunimd may rely on **notice-and-consent** rather than full verification.

### 4.3 Consent Withdrawal

Parents and guardians may withdraw consent at any time. Withdrawal is prospective — it does not undo processing already lawfully performed. After withdrawal, Dunimd will:

- Stop the minor's use of the hosted Service.
- Delete or anonymize the minor's personal information within the timeframes in [Privacy Policy §7](PRIVACY.md#7-data-retention).

### 4.4 Without Parental Consent

Where Dunimd cannot obtain parental consent (or the user is in a jurisdiction where the age threshold is below Dunimd's protected threshold):

- Dunimd will not knowingly collect personal information from the minor.
- If such data was collected inadvertently, Dunimd will delete it on discovery.

---

## 5. Where Data Is Stored

### 5.1 Local-First

For Encre used locally, the minor's data stays on the device. Dunimd does not receive it.

### 5.2 Hosted Services

For Dunimd Cloud, PiscesLx hosted inference, and Enterprise deployments, data is stored in the region selected at provisioning. Dunimd provides regions in major jurisdictions to support local-storage requirements.

### 5.3 Cross-Border Transfers

Where cross-border transfer is necessary for hosted Services, Dunimd applies the safeguards in [Privacy Policy §9](PRIVACY.md#9-international-data-transfers), including:

- EU SCCs, UK IDTA, Swiss-equivalent clauses.
- PRC CAC security assessment or standard contract, where applicable.
- APEC Cross-Border Privacy Rules where certified.

---

## 6. Security

Minor's personal information receives enhanced safeguards:

- **Encryption in transit**: TLS 1.2+ enforced.
- **Encryption at rest**: AES-256-GCM.
- **Access controls**: least-privilege principle; no engineer accesses minor's content without a documented support ticket and approval.
- **Logging**: all access to minor's data is logged and reviewable.
- **Retention**: shorter than general retention where possible; defaults to delete-on-account-closure.
- **Vendor vetting**: sub-processors that handle minor's data are vetted for COPPA / GDPR Art. 8 / PRC PIPL Art. 31 compliance.

---

## 7. Sharing and Disclosure

### 7.1 With Parents / Guardians

Dunimd shares the minor's personal information with their parents or guardians on verified request, in line with the rights in [§8](#8-rights-of-parents-and-guardians).

### 7.2 With Service Providers

Sub-processors may process minor's data only on documented instructions and only as needed to operate the Service. Each sub-processor is bound by data-processing terms equivalent to Dunimd's.

### 7.3 With Schools or Organizations

Where a minor uses Dunimd Services through an educational or organizational account, the organization may have rights over the data per its own policies and applicable law.

### 7.4 With Third Parties for Marketing or Advertising

**Never**. Dunimd does not sell, rent, or share minor's personal information for marketing or advertising purposes.

### 7.5 With Law Enforcement

Dunimd discloses minor's personal information to competent authorities only on valid legal process, in line with [Privacy Policy §6.2](PRIVACY.md#62-legal-requirements), and notifies the parent/guardian where lawful.

---

## 8. Rights of Parents and Guardians

Parents and guardians of a minor have enhanced rights over the minor's personal information:

- **Right to know** what data Dunimd has collected about the minor.
- **Right to access** the data in a portable format.
- **Right to correct** inaccurate data.
- **Right to delete** the data and the minor's account.
- **Right to limit** further processing.
- **Right to refuse** disclosure to third parties.
- **Right to withdraw consent** (prospective).
- **Right to review** any third-party sharing arrangements.
- **Right to be informed** of any breach affecting the minor's data.

These rights are exercised through the same channels as the general rights in [Privacy Policy §10](PRIVACY.md#10-your-rights-and-choices). Where a parent/guardian is acting on behalf of a minor, Dunimd verifies parental authority before fulfilling the request.

### 8.1 Response Time

We respond to parent/guardian requests within the shorter of:

- **15 business days** (PRC PIPL default), or
- The statutory response period in the parent's/guardian's jurisdiction.

### 8.2 Identity Verification

To protect the minor, Dunimd may require proof of parental authority. Acceptable proofs include birth certificate, court order, or government-issued ID matching the minor's record.

---

## 9. Age-Appropriate Design

Dunimd Services implement age-appropriate design principles:

- **No manipulative design**: no dark patterns designed to manipulate minors.
- **Transparent language**: privacy notices are written in plain language appropriate to the user's age.
- **Default privacy**: telemetry, AI training, and non-essential data collection are **off by default** for users we identify as minors.
- **No profiling for ads**: we do not build advertising profiles of minors.
- **No geolocation defaults**: precise geolocation is off by default.
- **No third-party tracking in products designed for minors**.

---

## 10. Breach Notification

If Dunimd becomes aware of a breach of security leading to accidental or unlawful destruction, loss, alteration, unauthorized disclosure of, or access to minor's personal information:

- Dunimd notifies the parent/guardian **without undue delay** and at the latest within the statutory window (e.g. **72 hours** under GDPR for breaches posing risk to individuals; same standard for minor's data).
- The notification describes the nature of the breach, likely consequences, measures taken, and recommended steps for the parent/guardian.
- Dunimd coordinates with competent authorities as required by law.

---

## 11. Updates

We may update this document. Material changes are communicated through the Services or by other appropriate means with reasonable prior notice (typically **30 days**). Where the change is material to the protection of minors, Dunimd will seek renewed parental consent where required.

---

## 12. Contact

| Channel | Address |
|---|---|
| Email | [dunimd@outlook.com](mailto:dunimd@outlook.com) |
| Website | [dunimd.com](https://dunimd.com) |
| Parental consent form | [minors.dunimd.com](https://minors.dunimd.com) *(pending activation)* |
| GitHub | [github.com/mf2023/Encre](https://github.com/mf2023/Encre) |
| Gitee mirror | [gitee.com/dunimd/encre](https://gitee.com/dunimd/encre) |

---

## 13. Definitions

- **Minor** — a natural person below the age of digital consent in their jurisdiction, as enumerated in [§2](#2-who-counts-as-a-minor).
- **Parent / Guardian** — a person with parental responsibility for the minor, including biological parents, adoptive parents, and court-appointed guardians.
- **Verifiable Parental Consent (VPC)** — a method, enumerated in [§4.2](#42-verifiable-parental-consent-methods), that meets the standard set by the FTC COPPA Rule, GDPR Art. 8(2), PRC PIPL Art. 31, or equivalent.
- **Minor's Personal Information** — any information relating to an identified or identifiable minor.
- **Age-Appropriate Design** — the principles enumerated in [§9](#9-age-appropriate-design).

---

*This document is provided for informational purposes and does not constitute legal advice. Consult qualified counsel in your jurisdiction to ensure your use of Dunimd Services and your treatment of minors' personal information complies with all applicable laws and regulations.*