# Data Processing Rules (India)

**Last updated: 22 August 2026**
> Parent: [Privacy Policy](PRIVACY.md)

## 1. Local-First Declaration

**Encre Agent is local-first:** conversations, prompts, AI outputs, session history, settings, skills, memory and indexes are stored **entirely on your device**. In **pure local mode** (no cloud backend configured), **no data ever passes through Dunimd servers**. Apache-2.0 source lets you audit this.

## 2. Data Flow

| Data | Default location | Leaves device when |
|---|---|---|
| Prompts / chats / AI output | Device | Only if you configure a cloud backend (direct to it) |
| Settings / skills / memory / indexes | Device | Never |
| API keys | Encrypted on device (AES-256-GCM) | Only to the key issuer |
| Telemetry / crash logs | **Off by default** | Sent to Dunimd only after opt-in |
| Account info | Chosen Dunimd Cloud region | At signup/billing |
| Hosted-inference metadata | Dunimd infra | PiscesLx use; content not retained by default |

## 3. Per Service

Encre Agent (device) · PiscesLx (our cloud or customer environment) · Enterprise (customer environment) · StadionOS (customer hardware, telemetry off) · Cloud (chosen workloads) · Studio (local, anonymous licence ping) · Support (only what you submit).

## 4. Telemetry

Desktop & dev tools collect nothing by default; explicit consent before enabling; no keystrokes/screen/clipboard/history.

## 5. Transfers

Pure local mode = none. Offshore model providers receive content directly from your device at your choice. Any Dunimd-initiated transfer complies with DPDP §16 and Rule restrictions as they commence.

## 6. Security & Retention

TLS 1.2+, AES-256-GCM, least privilege. Retention: local data = yours; inference content = none by default; metadata ≤12 months anonymised; support records ≤24 months; billing per tax law.

## 7. Changes

30-day notice if local-first defaults ever change.
