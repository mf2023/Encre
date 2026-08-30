# Datenverarbeitung – Schweiz

**Letzte Aktualisierung：22. August 2026**

**Geltungsbereich：** Dieses Dokument beschreibt die Datenverarbeitung in den Dunimd-Diensten. Für die Schweiz ist dieses Dokument die allein anwendbare Fassung.

> Zugehörige Dokumente：[Datenschutzerklärung](PRIVACY.md) · [Nutzungsbedingungen](TERMS.md) · [Nutzervereinbarung](USER_AGREEMENT.md) · [Minderjährigenschutz](MINORS_PRIVACY.md) · [Inhaltsrichtlinien](CONTENT_GUIDELINES.md)

## Inhaltsverzeichnis

1. [Local-first-Erklärung](#1-local-first-erklärung)
2. [Datenflüsse](#2-datenflüsse)
3. [Verarbeitung je Dienstleistung](#3-verarbeitung-je-dienstleistung)
4. [Telemetrie](#4-telemetrie)
5. [Internationale Weitergabe](#5-internationale-weitergabe)
6. [Sicherheit und Meldepflichten](#6-sicherheit-und-meldepflichten)
7. [Änderungen und Kontakt](#7-änderungen-und-kontakt)

---

## 1. Local-first-Erklärung

1.1 Encre Agent ist lokal konzipiert：Agentendefinitionen, Prompts, Antworten, Verläufe und Integrationen bleiben auf Ihrem Gerät.

1.2 Telemetrie ist standardmässig deaktiviert; Prompts und Antworten werden standardmässig nicht gespeichert.

1.3 Eine Verarbeitung über Ihr Gerät hinaus findet nur statt, wenn Sie Cloud-Dienste (z. B. PiscesLx-Inference oder Synchronisation) aktiv einschalten.

## 2. Datenflüsse

| Daten | Ort | Dauer |
|---|---|---|
| Agentenkonfigurationen, Workflows | nur Gerät | bis zur Löschung |
| Konversationsverläufe | nur Gerät | Nutzersteuerung |
| API-Schlüssel (Drittanbieter) | verschlüsselt auf dem Gerät | bis zur Löschung |
| Cloud-Inference-Anfragen | nach Verarbeitung gelöscht | Sitzung |
| Dienstmetadaten (Zeitstempel, Fehlercodes) | serverseitig | max. 30 Tage |
| Telemetrie (Opt-in) | serverseitig | max. 90 Tage |
| Kontodaten (nur Cloud-Dienste) | serverseitig | bis zur Löschung des Kontos, vorbehaltlich gesetzlicher Aufbewahrung |

## 3. Verarbeitung je Dienstleistung

3.1 **PiscesLx (gehostetes LLM)：** Anfragen werden TLS-verschlüsselt übermittelt und im Arbeitsspeicher verarbeitet; Metadaten (Zeitstempel, Tokenzahl, Fehlerstatus) werden nach spätestens 30 Tagen automatisch gelöscht.

3.2 **Encre Agent Desktop/Framework：** keine serverseitige Verarbeitung; alle Daten bleiben lokal.

3.3 **Dunimd Enterprise：** Verarbeitung kraft Auftragsbearbeitungsvertrag (Art. 21 DSG).

3.4 **Chat-Plattform-Integrationen：** auf Plattformseite gelten die jeweiligen Datenschutzbestimmungen; wir verarbeiten nur das für die Integration Nötige.

## 4. Telemetrie

4.1 Telemetrie erfolgt strikt als Opt-in：ohne Ihre ausdrückliche Zustimmung werden keinerlei Diagnosedaten gesendet.

4.2 Sie können die Telemetrie jederzeit in den Einstellungen deaktivieren; bestehende Datensätze werden gelöscht.

## 5. Internationale Weitergabe

5.1 Die Verarbeitung erfolgt vorrangig in der Schweiz.

5.2 Soweit internationale Weitergaben nötig sind, erfolgen sie gestützt auf die vom EDÖB anerkannten Standardvertragsklauseln (Ausgabe 2021), Bundesrats-Adäquanzentscheide oder andere geeignete Garantien (Art. 16 ff. DSG).

## 6. Sicherheit und Meldepflichten

6.1 Technische Massnahmen：Transportverschlüsselung (TLS 1.2+), Verschlüsselung im Ruhezustand (AES-256-GCM), minimale Zugriffe.

6.2 Organisatorische Massnahmen：Vertraulichkeitsverpflichtungen, Zugriffsprotokollierung, regelmässige Reviews.

6.3 **Meldepflicht bei Datenschutzverletzungen：** Bei einer wahrscheinlichen hohen Gefährdung der betroffenen Personen melden wir den Vorfall umgehend dem Eidg. Datenschutz- und Öffentlichkeitsbeauftragten (EDÖB) (Art. 24 DSG); wo erforderlich informieren wir zudem die betroffenen Personen.

## 7. Änderungen und Kontakt

7.1 Änderungen dieses Dokuments werden mindestens 30 Tage vorher angekündigt.

7.2 Kontakt：dunimd@outlook.com · dunimd.com · Aufsichtsbehörde：EDÖB, edoeb.admin.ch

---

*Dieses Dokument dient ausschliesslich der Information und stellt keine Rechtsberatung dar.*
