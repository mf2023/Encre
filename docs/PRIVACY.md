# Privacy Policy

**Last updated: 2026-06-21**
**Controller:** Dunimd
**Scope:** Global — applies to all users of Dunimd Services worldwide.

This document is the **international** Privacy Policy for Dunimd and its Services. The Chinese-jurisdiction-specific policy is [`PRIVACY_CN.md`](PRIVACY_CN.md), which supplements this one with the full PRC framework (PIPL, DSL, CSL, generative-AI rules, cross-border data transfer regulations) and is the controlling document for users in the People's Republic of China.

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Dunimd Services Covered](#2-dunimd-services-covered)
3. [Information We Collect](#3-information-we-collect)
4. [How We Use Your Information](#4-how-we-use-your-information)
5. [Lawful Bases for Processing](#5-lawful-bases-for-processing)
6. [Data Sharing and Disclosure](#6-data-sharing-and-disclosure)
7. [Data Retention](#7-data-retention)
8. [Data Security](#8-data-security)
9. [International Data Transfers](#9-international-data-transfers)
10. [Your Rights and Choices](#10-your-rights-and-choices)
11. [AI, LLM, and Generative Content](#11-ai-llm-and-generative-content)
12. [Children's Privacy](#12-childrens-privacy)
13. [Automated Decision-Making](#13-automated-decision-making)
14. [Service-Specific Disclosures](#14-service-specific-disclosures)
15. [Changes to This Policy](#15-changes-to-this-policy)
16. [Contact Us](#16-contact-us)
17. [Jurisdiction-Specific Disclosures](#17-jurisdiction-specific-disclosures)
18. [Definitions](#18-definitions)

---

## 1. Introduction

**Dunimd** ("we") is an independently-operated technical team focused on the research and development of AI Agent, large language models, enterprise AI services, operating systems, and supporting cloud and developer tools. This policy applies to all products and services provided by Dunimd.

Dunimd is the **data controller** for personal information collected through any of our Services. Where a particular Service involves a different controller (e.g. a third-party AI model provider you configure, or a Dunimd subsidiary acting on its own behalf), we tell you in the Service-specific section below.

Because most Dunimd Services are **local-first** or **customer-controlled** by design (running on your device or in your own environment), the data we hold centrally is small. We treat even that small footprint seriously and apply the strictest baseline we are subject to — the EU GDPR — to every user regardless of location.

If you are in the **People's Republic of China**, see [`PRIVACY_CN.md`](PRIVACY_CN.md) for the PRC-specific policy that supplements this one.

**Contact:** [dunimd@outlook.com](mailto:dunimd@outlook.com) — Website: [dunimd.com](https://dunimd.com)

By using any Dunimd Service, you consent to the practices described in this policy. If you do not agree, do not use the Services.

---

## 2. Dunimd Services Covered

This policy applies to every product, service, platform, API, model, and tool that Dunimd makes available under the Dunimd brand. The list below describes what we offer today; the policy automatically extends to new Services we launch, unless a Service publishes its own privacy policy that explicitly takes precedence.

| Service | Description | Hosting model |
|---|---|---|
| **Encre** | Open-source AI Agent platform — desktop application, Python framework, Rust native core, and 18 chat-platform integrations | Local-first (your device); optional hosted Cloud |
| **PiscesLx** | Large language models (foundation models, fine-tuning, hosted inference API) | Dunimd-managed cloud; on-prem / VPC for enterprise |
| **Dunimd Enterprise** | Enterprise AI deployment, MLOps, custom solutions, professional services, and dedicated support | Customer-controlled environment (on-prem / private cloud) |
| **StadionOS** | Operating-system products and OS-level integrations (kernels, runtimes, drivers, edge-device firmware) | Customer-controlled environment |
| **Dunimd Cloud** | Managed cloud infrastructure for hosting Dunimd Services and customer workloads | Dunimd-managed cloud |
| **Dunimd Studio** | Developer tools — IDE plugins, CLI, SDKs, and supporting documentation | Local-first; optional telemetry |
| **Dunimd Support** | Technical support, customer success, training, and community programs | Dunimd-managed |

A Service-specific section in [Section 14](#14-service-specific-disclosures) describes the personal information flows unique to each Service. Where this general policy and a Service-specific section disagree, the Service-specific section prevails.

A current list of named Services is maintained at [dunimd.com/services](https://dunimd.com/services) *(pending activation)*. The page is the authoritative reference for which Services are currently covered.

---

## 3. Information We Collect

### 3.1 Information You Provide

- **Account / Configuration** — name, email, organization, role, billing details, service-tier preferences, and any settings you configure inside a Dunimd Service.
- **Customer Content** — prompts, files, conversation history, code, documents, designs, datasets, voice/video, and any other content you submit to a Dunimd Service for processing by an AI model or a tool.
- **Communication Data** — information you provide when contacting support, opening a ticket, joining a beta program, attending an event, or submitting feedback.
- **Authentication Data** — credentials, tokens, API keys, and SSO assertions used to authenticate with Dunimd or with third-party systems you have connected.
- **Enterprise Administrative Data** — for Enterprise customers, the contact information of administrators, billing contacts, and authorized users, plus the structure of your organization (org chart, team membership) as needed to deliver the Service.

### 3.2 Information Collected Automatically

Only when telemetry is enabled in your Service settings (it is **off by default** for desktop and developer-tooling Services):

- **Usage Data** — aggregated, anonymized statistics about feature usage, session duration, and interaction patterns.
- **Diagnostic Data** — error logs, crash reports, and performance metrics.
- **Device / Environment Information** — OS type and version, application version, hardware identifiers, runtime versions, locale, and time zone.
- **Network Information** — IP address, connectivity status, and (for managed cloud Services) the source region of requests.
- **Telemetry for AI Models** — for hosted LLM inference, request metadata (timestamp, model ID, token counts, latency) but **not** the prompt or response content unless you opt in.

### 3.3 Information We Do NOT Collect

Unless you voluntarily provide it or a specific Service explicitly requires it, we do not collect:

- Biometric data (face, voice, fingerprint) for identification — except where a feature explicitly requires it (e.g. voice-mode in a chat platform) and only with your separate consent.
- Browsing history, bookmarks, or files outside those you explicitly choose to use with a Service.
- Keystroke dynamics, mouse trajectories, or behavioral biometrics.
- Precise geolocation; coarse geolocation is derived from IP only for security.
- The content of your prompts or AI-model outputs on Services that run inference in your environment (Encre local mode, on-prem Enterprise).

### 3.4 Sensitive / Special-Category Information

Some Services may optionally process sensitive personal information as defined by your jurisdiction (e.g. GDPR Art. 9 special categories; PIPL §28 sensitive personal information; CCPA "sensitive personal information") — for example, health data when you use a medical-domain fine-tune, or biometric data when you enroll in a voice-mode feature. In every such case, we obtain **separate, explicit consent** before processing, limit retention to the minimum needed to deliver the feature, and apply the security controls in [Section 8](#8-data-security).

---

## 4. How We Use Your Information

We use the information we collect for:

- **Service Operation** — to run the Services, deliver features, and relay content to the AI backends you have configured.
- **Improvement and Development** — to analyze usage patterns, diagnose issues, and enhance the Services.
- **Model Training (LLM Services only)** — see [Section 11.1](#111-training-and-fine-tuning) for the explicit opt-in model.
- **Security** — to detect, prevent, and respond to security incidents and unauthorized access.
- **Compliance** — to comply with applicable laws and lawful requests from public authorities.
- **Customer Support** — to provide technical assistance and respond to your inquiries.
- **Billing and Administration** — for paid Services, to manage subscriptions, invoices, and entitlements.
- **Enterprise Administration** — for Enterprise customers, to manage the customer's organization, user provisioning, and audit trails within the customer's tenant.

We **do not** use your content to train AI models on Services that you have not opted in to training on, and we **do not** sell, rent, or trade your personal information. See [Section 6.4](#64-we-do-not-sell-your-data).

---

## 5. Lawful Bases for Processing

For users in the EEA, UK, and Switzerland, we process personal data under the following GDPR Article 6 bases:

| Purpose | Legal Basis |
|---|---|
| Service Operation | Performance of a contract (Art. 6(1)(b)) |
| Billing and Administration | Performance of a contract (Art. 6(1)(b)) |
| Product Improvement | Legitimate interests (Art. 6(1)(f)) |
| Security | Legitimate interests (Art. 6(1)(f)) |
| Legal Compliance | Legal obligation (Art. 6(1)(c)) |
| Diagnostic / Usage Data | Consent (Art. 6(1)(a)) — withdrawn at any time |
| Marketing communications | Consent (Art. 6(1)(a)) — withdrawn at any time |

For users in other jurisdictions, equivalent bases apply (contract performance, consent, legitimate interests, legal obligation, vital interests). See [Section 17](#17-jurisdiction-specific-disclosures) for the country-specific mappings.

---

## 6. Data Sharing and Disclosure

### 6.1 Third-Party Service Providers

We share information only with parties you have chosen or that are necessary to operate the Services:

- **AI model providers** you explicitly configure (OpenAI, Anthropic, Ollama, PiscesLx, etc.).
- **Cloud infrastructure providers** for any hosted Dunimd Service.
- **Analytics services** for product improvement — anonymized data only.
- **CI/CD and crash-reporting services** for the Software itself.
- **Payment processors** for paid Services.
- **Enterprise customer (controller)** — for Enterprise deployments, your organization is the controller and we act as processor under a Data Processing Agreement (DPA).

Each provider is contractually obligated to protect your information and may use it only for the specific services they provide to us.

### 6.2 Legal Requirements

We may disclose information if required by law or in response to valid legal process from a competent authority. We will challenge over-broad requests and notify affected users where legally permitted.

### 6.3 Business Transfers

In a merger, acquisition, reorganization, or sale of assets, your information may transfer. We will notify you of any change of controller and the applicable privacy terms.

### 6.4 We Do Not Sell Your Data

We do not sell, rent, or trade personal information. This satisfies the CCPA/CPRA definition of "sale," the Virginia CDPA definition of "sale of personal data," and equivalent restrictions in other US state laws.

### 6.5 Enterprise Customers as Controllers

For Enterprise Services, your organization is the **data controller** and we are the **data processor** (or "service provider" under CCPA). Enterprise customers may direct our processing under their DPA. This policy describes Dunimd's baseline practices; the customer DPA may add or modify them.

---

## 7. Data Retention

We retain information only as long as necessary:

| Data category | Retention period |
|---|---|
| **Customer Content** | Per your configuration. Default: kept only for the duration of the active session. For hosted LLM inference, **not** retained by default. |
| **Usage and Diagnostic Data** | Up to 12 months, then anonymized or deleted |
| **Configuration Data** | Until you modify or delete your settings |
| **Communication Records** | Up to 24 months for support purposes |
| **Billing Records** | As required by tax and accounting law in your jurisdiction (typically 7 years; varies) |
| **Training Data (opted in)** | Per the opt-in scope; see [Section 11.1](#111-training-and-fine-tuning) |
| **Audit Logs (Enterprise)** | Per your tenant configuration; default 12 months |

When you delete your account, we delete or anonymize personal information we control, subject to legal retention requirements.

---

## 8. Data Security

We implement appropriate technical and organizational measures to protect your information:

- **Encryption in transit** — TLS 1.2 or higher between Services and configured backends.
- **Encryption at rest** — AES-256-GCM for locally stored sensitive data (API keys, cookies, customer content at rest in hosted Services).
- **Access Controls** — least-privilege principle for any staff with data access; documented approval workflows.
- **Network Isolation** — production and development environments are isolated; production access requires MFA and audit logging.
- **Audits** — security practices reviewed regularly.
- **Vulnerability Management** — see [SECURITY.md](SECURITY.md) for our coordinated disclosure process.
- **Incident Response** — documented process, customer notification within 72 hours of confirmed personal-data breach (GDPR-compliant; tighter where local law requires).
- **AI-Specific Safeguards** — prompt-injection detection on hosted LLM endpoints; output filtering; per-tenant isolation in Enterprise deployments.

### 8.1 Data Localization

You control where your data is processed where the architecture allows it:

- **Local-first Services (Encre, Dunimd Studio CLI)** — all processing on your device; nothing leaves.
- **Self-Hosted Enterprise Services** — you control data location (on-prem, private cloud, regional cloud).
- **Dunimd-Managed Cloud Services** — you select the region at provisioning time. Data stays in that region unless you explicitly authorize a cross-region transfer.

---

## 9. International Data Transfers

When personal data crosses borders, we use approved transfer mechanisms for the source jurisdiction:

- **EEA / UK → third country:** EU Standard Contractual Clauses (SCCs), UK International Data Transfer Agreement (IDTA), or UK Addendum.
- **Switzerland → third country:** Swiss-equivalent SCCs and FDPIC-recognised mechanisms.
- **Cross-border from China:** see [PRIVACY_CN.md §11](PRIVACY_CN.md).
- **All other jurisdictions:** we apply the strictest available mechanism and provide a copy on request.

For details by jurisdiction, see [Section 17](#17-jurisdiction-specific-disclosures).

---

## 10. Your Rights and Choices

Depending on your jurisdiction, you may have some or all of these rights. Section 17 lists the rights recognized in each region.

- **Right to Access** — request a copy of the personal information we hold.
- **Right to Rectification** — correct inaccurate or incomplete information.
- **Right to Deletion / Erasure** — request deletion, subject to legal exceptions.
- **Right to Restrict Processing** — limit how we use your information.
- **Right to Data Portability** — receive your information in a portable format.
- **Right to Object** — object to processing based on legitimate interests or for direct marketing.
- **Right to Withdraw Consent** — at any time, where processing is consent-based.
- **Right to Lodge a Complaint** — with your local data-protection authority.
- **Right not to be subject to automated decision-making** — see [Section 13](#13-automated-decision-making).

### 10.1 Exercising Your Rights

Email [dunimd@outlook.com](mailto:dunimd@outlook.com) or visit [dunimd.com](https://dunimd.com). We respond:

- within **30 days** under GDPR / UK GDPR / FADP;
- within **45 days** under CCPA/CPRA, with one 45-day extension permitted;
- within **30 days** under PIPEDA;
- within **15 business days** under PIPL (China) — see [PRIVACY_CN.md](PRIVACY_CN.md);
- within statutory periods in all other jurisdictions.

For Enterprise customers, the **Enterprise administrator** is the primary point of contact for exercising rights on behalf of the organization. Dunimd will action requests the Enterprise administrator directs, subject to identity verification.

### 10.2 Opt-Out of Diagnostic Data

Toggle in **Settings → Privacy → Diagnostic Data** in desktop / developer-tooling Services.

### 10.3 Marketing Opt-Out

Every marketing email contains an unsubscribe link. You may also opt out by emailing [dunimd@outlook.com](mailto:dunimd@outlook.com).

---

## 11. AI, LLM, and Generative Content

### 11.1 Training and Fine-Tuning

- We **do not** use your content to train AI models on Services that you have not opted in to training on.
- For Services that offer training, fine-tuning, or model-improvement features, opt-in is **separate** from using the Service and is captured at the time you submit content for that purpose. You can withdraw the opt-in at any time; the withdrawal applies prospectively.
- For hosted LLM inference, request metadata (timestamp, model ID, token counts, latency) may be retained for billing and abuse-prevention purposes; the **prompt and response content is not retained** by default.
- If you use Encre or another local-first Service, your content never reaches us at all, regardless of opt-in status.

### 11.2 Output Ownership

You retain **full ownership** of your inputs and outputs on every Service. We claim no intellectual-property rights over your content. Where the law grants us a license to use content (for example, to operate the Service or improve it on your behalf), that license is limited to the purpose stated at the point of collection and revocable on the same terms as consent.

### 11.3 Third-Party AI Providers

When you use a third-party AI provider (e.g. OpenAI, Anthropic), their terms of service and privacy policies govern the processing of your content by them. Review them before use. Dunimd is not responsible for the practices of third-party providers you choose to connect.

### 11.4 Generative AI Specific Regulations

Some jurisdictions regulate generative AI services specifically. The Service-specific sections ([Section 14](#14-service-specific-disclosures)) describe how each Service complies with the relevant framework. The Chinese-jurisdiction-specific rules are described in full in [PRIVACY_CN.md](PRIVACY_CN.md).

---

## 12. Children's Privacy

Dunimd Services are not directed to children. We do not knowingly collect personal information from children below the age of consent in their jurisdiction. Where local law sets a higher threshold (e.g. 14 in the PRC, 16 in several EU member states, 13 under COPPA in the USA, 14 under PIPL), we apply the higher threshold.

If we learn that a child's personal information has been collected without verifiable parental consent, we will delete it as soon as possible. See the [MINORS_PRIVACY.md](MINORS_PRIVACY.md) addendum for the full Dunimd policy on minors' data.

---

## 13. Automated Decision-Making

We **do not** use automated decision-making or profiling that produces legal or similarly significant effects on you (Art. 22 GDPR and equivalents). The Encre `EncreAutoSafetyClassifier` makes per-tool-call permission decisions, but those decisions are gated by the explicit permission mode you have selected and can be overridden at any time — they do not meet the Art. 22 threshold.

Enterprise Services may include automation features (e.g. alerting, autoscaling) that produce operational effects but **not** legal effects on individuals. Where any future feature does meet the Art. 22 threshold, we will obtain your explicit consent before deploying it and document your right to human review.

---

## 14. Service-Specific Disclosures

The following sub-sections describe personal-information flows that differ from the general policy above. Where a Service-specific section is silent, the general policy applies.

### 14.1 Encre (AI Agent Platform)

- **Local-first by default.** The Encre desktop application runs on your device and does not transmit content to Dunimd servers unless you enable a hosted feature.
- **Hosted Cloud (when used).** When you connect to Dunimd Cloud for hosted LLM inference, prompts and responses flow through Dunimd infrastructure; we retain request metadata but not content unless you opt in to logging.
- **No model training on customer content** — see [Section 11](#11-ai-llm-and-generative-content).
- **Open-source.** The Encre source code is published under Apache 2.0; you may inspect the data flows yourself.

### 14.2 PiscesLx (Foundation Models and Inference API)

- **Hosted inference.** Requests and responses are processed on Dunimd infrastructure. Content is not retained by default; request metadata is retained for billing and abuse prevention.
- **Fine-tuning.** When you fine-tune a model, the training data you provide is processed on Dunimd infrastructure under your explicit opt-in. Trained model artifacts are delivered to you; the source training data is deleted per the retention schedule unless you opt in to longer retention.
- **Abuse prevention.** We monitor for misuse (jailbreaks, prompt-injection attacks, attempts to extract other customers' data) and may retain offending requests for the duration of the investigation.

### 14.3 Dunimd Enterprise (B2B Deployments)

- **Customer is the controller.** Your organization is the data controller; Dunimd is the processor (service provider) acting on documented instructions. A Data Processing Agreement (DPA) governs our role.
- **On-prem / VPC.** Data may stay entirely within your environment; Dunimd staff access requires customer approval.
- **Dedicated tenants.** Customer data is logically isolated; audit logs are available to your administrator.
- **Sub-processors.** A current list of sub-processors is at [dunimd.com/enterprise/subprocessors](https://dunimd.com/enterprise/subprocessors) *(pending activation)*. Customers may object to a new sub-processor under their DPA.

### 14.4 StadionOS (Operating-System Products)

- **Local processing.** OS-level features run on customer-controlled hardware. Telemetry is off by default.
- **Optional connected services.** When enabled, OS-level connected services (e.g. update delivery, license validation) transmit device identifiers and usage metadata to Dunimd infrastructure.
- **Firmware updates.** Update packages are signed; update channels can be local-only, customer-controlled, or Dunimd-managed.

### 14.5 Dunimd Cloud (Managed Cloud Infrastructure)

- **Hosting regions.** You select the region at provisioning time.
- **Customer data isolation.** Customer workloads are logically isolated using industry-standard tenant boundaries.
- **Encryption.** All customer data encrypted at rest (AES-256) and in transit (TLS 1.2+).
- **Compliance.** Dunimd Cloud infrastructure is operated in alignment with ISO 27001, SOC 2 Type II, and equivalent frameworks; current certifications listed at [dunimd.com/trust](https://dunimd.com/trust) *(pending activation)*.

### 14.6 Dunimd Studio (Developer Tools)

- **Local-first.** IDE plugins, CLI, and SDKs run on your machine; no telemetry is sent unless you opt in.
- **License checks.** Anonymous license-validation pings are sent to Dunimd infrastructure; these do not include code or content.

### 14.7 Dunimd Support

- **Support data.** Information you share with our support team (screenshots, logs, sample files) is treated as Customer Content under your existing Service agreement.
- **Third-party support vendors.** We may use vetted vendors for tier-1 support; they are bound by confidentiality and data-processing terms equivalent to ours.

### 14.8 Future Services

New Services launched after the "Last updated" date above are covered by this policy automatically. Each Service publishes a Service-specific addendum at the time of launch if its data flows differ materially from the general policy.

---

## 15. Changes to This Policy

We may update this policy to reflect changes in our practices, legal requirements, or industry standards. Material changes will be communicated through the Services and by other appropriate means. The "Last updated" date at the top reflects the latest revision. Continued use after changes constitutes acceptance of the updated policy.

Where local law requires additional notice (e.g. PIPL's 30-day notice for material changes in China), we comply.

For Enterprise customers, material changes that affect the processing of customer data may require an addendum to the DPA in addition to this policy update.

---

## 16. Contact Us

| Channel | Address |
|---|---|
| Email | [dunimd@outlook.com](mailto:dunimd@outlook.com) |
| Website | [dunimd.com](https://dunimd.com) |
| Privacy web form | [privacy.dunimd.com](https://privacy.dunimd.com) *(pending activation)* |
| Data Protection Officer | [dpo.dunimd.com](https://dpo.dunimd.com) *(pending activation)* |
| GitHub | [github.com/mf2023/Encre](https://github.com/mf2023/Encre) |
| Gitee mirror | [gitee.com/dunimd/encre](https://gitee.com/dunimd/encre) |

---

## 17. Jurisdiction-Specific Disclosures

The following sub-sections explain how the policy above applies in specific countries and regions. Where a section is silent on a question, the global policy applies.

### 17.1 European Economic Area & United Kingdom

**Applicable law:** Regulation (EU) 2016/679 ("GDPR"); UK GDPR + Data Protection Act 2018; the ePrivacy Directive 2002/58/EC where applicable.

**Rights recognized:** all of those in [Section 10](#10-your-rights-and-choices), plus:

- Right to lodge a complaint with your national supervisory authority (a full list is at the [EDPB](https://edpb.europa.eu/about-edpb/about-edpb/members_en)).
- Right to an effective judicial remedy against a binding decision.
- Right to compensation for damage.

**EEA representative:** appointed where required by Art. 27 GDPR; details provided on request.

**Lead supervisory authority for our UK entity:** the Information Commissioner's Office (ICO).

### 17.2 Switzerland

**Applicable law:** Federal Act on Data Protection (revFADP, in force from 1 September 2023) and the Data Protection Ordinance.

**Cross-border transfers:** use the FDPIC's Swiss-equivalent SCCs or other approved mechanisms.

**Lead authority:** Federal Data Protection and Information Commissioner (FDPIC).

### 17.3 United States — California

**Applicable law:** California Consumer Privacy Act (CCPA) as amended by the California Privacy Rights Act (CPRA); California Online Privacy Protection Act (CalOPPA); Shine the Light (Cal. Civ. Code § 1798.83).

**Rights recognized:** Right to Know, Right to Delete, Right to Correct, Right to Opt-Out of Sale/Sharing, Right to Limit Use of Sensitive Personal Information, Right to Non-Discrimination.

**Categories of PI collected in the past 12 months:** identifiers (device IDs, IP), commercial information (usage patterns), internet/electronic activity (feature usage), geolocation (coarse only), professional information (for Enterprise admin contacts), inferences (limited; for security). **No sale of PI.** **No collection of sensitive PI** as defined by CCPA except where you opt in.

**Submit requests:** [privacy.dunimd.com](https://privacy.dunimd.com) *(pending activation)* or [dunimd@outlook.com](mailto:dunimd@outlook.com). You may designate an authorized agent under § 999.326.

### 17.4 United States — other state laws

Dunimd complies with the comprehensive state privacy laws in effect as of the "Last updated" date above:

| State | Statute | Effective | Notes |
|---|---|---|---|
| Virginia | VCDPA | 2023-01-01 | |
| Colorado | CPA | 2023-07-01 | |
| Connecticut | CTDPA | 2023-07-01 | |
| Utah | UCPA | 2023-12-31 | |
| Texas | TDPSA | 2024-07-01 | |
| Oregon | OCPA | 2024-07-01 | |
| Montana | MCDPA | 2024-10-01 | |
| Delaware | DPDPA | 2025-01-01 | |
| Iowa | SF 262 | 2025-01-01 | |
| Tennessee | TIPA | 2025-07-01 | |
| Indiana | INCDPA | 2026-01-01 | |
| Other states as enacted | — | as enacted | |

Universal rights across these laws: Right to Access, Right to Correct, Right to Delete, Right to Data Portability, Right to Opt-Out of Sale / Targeted Advertising / Profiling, Right to Appeal a denied request.

### 17.5 United States — federal

**Children's Online Privacy Protection Act (COPPA):** we do not direct the Services to children under 13 and do not knowingly collect their personal information.

**Health Insurance Portability and Accountability Act (HIPAA):** we are not a covered entity or business associate. Do not submit Protected Health Information (PHI) unless you have entered into a separate BAA with us in writing.

**Gramm-Leach-Bliley Act (GLBA):** we are not a financial institution.

**Federal Trade Commission Act § 5:** we do not engage in unfair or deceptive practices.

**Executive Order 14117 (US bulk-data transfer rules) and DOJ implementing regulations:** for PiscesLx inference Services, we apply enhanced controls to prevent bulk transfer of covered personal data to countries of concern.

### 17.6 Canada

**Applicable law:** Personal Information Protection and Electronic Documents Act (PIPEDA); Quebec Law 25; Alberta PIPA; BC PIPA; the federal Consumer Privacy Protection Act (CPPA, when in force).

**Rights recognized:** access, correction, withdrawal of consent, complaint to the Office of the Privacy Commissioner of Canada (OPC) or your provincial commissioner.

**Cross-border:** PIPEDA requires us to use comparable protection for data processed outside Canada; we do so via contractual safeguards.

### 17.7 Australia & New Zealand

**Australia — Privacy Act 1988 (Cth) and the Australian Privacy Principles (APPs):** rights of access, correction, complaint to the Office of the Australian Information Commissioner (OAIC); Notifiable Data Breaches scheme applies.

**New Zealand — Privacy Act 2020:** rights of access, correction, complaint to the Office of the Privacy Commissioner; IPP 3A breach notification; IPP 11 cross-border safeguards.

### 17.8 Southeast Asia

**Singapore — PDPA 2012.** **Malaysia — PDPA 2010.** **Thailand — PDPA 2019.** **Philippines — DPA 2012.** **Indonesia — UU PDP (Law 27/2022).** **Vietnam — Law on Personal Data Protection 2025 + Decree 13/2023.**

Rights of access, correction, deletion, withdrawal of consent, complaint to the relevant national authority in each jurisdiction. Dunimd operates in alignment with the ASEAN Model Contractual Clauses for cross-border transfers where applicable.

### 17.9 Japan & South Korea

**Japan — APPI (as amended 2022):** rights of access, correction, deletion, suspension of use, opt-out of third-party provision; cross-border transfer rules (consent or PCC-accredited mechanisms). Lead authority: Personal Information Protection Commission (PPC).

**South Korea — PIPA (as amended 2023) + AI Basic Act (effective 22 January 2026):** rights of access, correction, deletion, suspension of processing; cross-border transfer rules. Lead authority: Personal Information Protection Commission (PIPC). AI Basic Act obligations on AI providers are addressed by our local-mode option and our no-training commitment.

### 17.10 Mainland China

For users in the People's Republic of China, the **controlling document** is [`PRIVACY_CN.md`](PRIVACY_CN.md). It supplements this international policy with the full PIPL/DSL/CSL framework, the 生成式人工智能服务管理暂行办法, and the cross-border data transfer rules. Where the two documents conflict on a PRC-specific question, PRIVACY_CN.md prevails.

### 17.11 Hong Kong SAR, Macau SAR, Taiwan

**Hong Kong — PDPO (Cap. 486):** the six Data Protection Principles; PCPD is the lead authority.

**Macau — Law 8/2005:** GPDP oversight.

**Taiwan — PDPA (amended 2023):** NDC oversight.

### 17.12 South Asia

**India — DPDPA 2023:** rights of access, correction, erasure, grievance redressal, nomination; Data Protection Board of India (DPB) jurisdiction; Significant Data Fiduciary obligations may apply.

**Sri Lanka — PDPA No. 9 of 2022.** **Bangladesh — Digital Security Act 2018 + Draft Data Protection Act 2023.**

### 17.13 Latin America

**Brazil — LGPD (Law 13.709/2018):** ARCO rights + portability; ANPD is the lead authority; DPO appointed.

**Argentina — Ley 25.326:** AAIP oversight.

**Mexico — LFPDPPP:** ARCO rights; INAI oversight.

**Chile — Ley 19.628 (reform project ongoing):** transitional APDP oversight.

**Colombia — Law 1581/2012 + Decree 1377/2013:** SIC oversight.

**Peru — Law 29733:** ANPD oversight.

**Uruguay — Law 18.331:** URCDP oversight.

### 17.14 Africa

**South Africa — POPIA (Act 4 of 2013):** Information Regulator oversight; cross-border transfer safeguards.

**Nigeria — Nigeria Data Protection Act 2023 + NDPR 2019:** NDPC oversight.

**Kenya — Data Protection Act 2019:** ODPC oversight.

**Egypt — PDPL (Law 151/2020):** PDPC Egypt oversight; cross-border approval required.

**Ghana — Data Protection Act 2012 (Act 843).** **Morocco — Law 09-08.**

### 17.15 Middle East

**Israel — Privacy Protection Law 5741-1981 + Data Security Regulations 5777-2017:** PPA oversight.

**Turkey — KVKK (Law 6698):** KVKK Board oversight.

**UAE — Federal Decree-Law 45/2021 (PDPL):** UAE Data Office oversight.

**Saudi Arabia — PDPL (effective 14 September 2024):** SDAIA oversight.

**Qatar — Law 13/2016.** **Jordan — Law 24/2023.** **Lebanon — Law 81/2018.**

### 17.16 Russia, Ukraine, Belarus, Kazakhstan

**Russia — Federal Law 152-FZ:** Roskomnadzor oversight; data localization for Russian citizens' data. The Software does not store personal data on Dunimd servers, so this requirement does not bite us — but Russian-hosted AI backends are the user's responsibility.

**Ukraine — Law 2297-VI.** **Belarus — Law 99-Z of 2021.** **Kazakhstan — Law 94-VII (2021).**

### 17.17 Other jurisdictions

For users in jurisdictions not specifically listed, we apply the strictest available baseline (GDPR-equivalent). The full list above is current as of "Last updated" date; we update it as new laws come into force.

If your jurisdiction is missing and you would like a specific section added, open an issue at [github.com/mf2023/Encre/issues](https://github.com/mf2023/Encre/issues).

---

## 18. Definitions

- **Personal Information / Personal Data** — any information relating to an identified or identifiable natural person.
- **Processing** — any operation on personal data, including collection, storage, use, disclosure, and deletion.
- **Data Controller** — the entity that determines purposes and means of processing. Dunimd is the controller for the Services covered by this policy; Enterprise customers are controllers for their tenants.
- **Data Processor** — an entity that processes data on behalf of the controller. Dunimd acts as processor for Enterprise customer data.
- **Service / Dunimd Services** — the products, services, platforms, APIs, models, and tools described in [Section 2](#2-dunimd-services-covered).
- **Customer Content** — content (text, files, images, audio, video, etc.) you submit to a Dunimd Service.
- **Sensitive Personal Information** — as defined in your jurisdiction (e.g. CCPA's "sensitive personal information," GDPR's "special categories of personal data," PIPL's "sensitive personal information").
- **Cross-Border Transfer** — transmission of personal data from one jurisdiction to another.
- **Local-First Service** — a Service whose default behavior processes Customer Content entirely on the customer's device, without sending it to Dunimd infrastructure.

---

*This Privacy Policy is provided for informational purposes and does not constitute legal advice. Consult qualified counsel in your jurisdiction to ensure compliance with all applicable laws and regulations.*
