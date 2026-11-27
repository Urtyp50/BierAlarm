# Sicherheit

## Unterstützte Versionen

Sicherheitsupdates gibt es nur für die **jeweils neueste Version** der Home-Assistant-Integration (Releases mit Tag `v*`). Bitte vor einer Meldung über HACS auf die neueste Version aktualisieren.

| Version | Unterstützt |
|---|---|
| neueste `v*`-Version | ✅ |
| ältere Versionen | ❌ |
| Android-App (`android-v*`) | ❌ eingestellt |

## Sicherheitslücke melden

Bitte **kein öffentliches Issue** anlegen. Stattdessen vertraulich über GitHub melden:

1. Im Repository auf **Security → Report a vulnerability** gehen
   (direkt: <https://github.com/Urtyp50/BierAlarm/security/advisories/new>)
2. Beschreiben, was passiert, wie man es nachstellt und welche Version betroffen ist

Was dann passiert:

- Eine erste Antwort gibt es in der Regel **innerhalb einer Woche**.
- Bestätigte Lücken werden so schnell wie möglich in einer neuen Version behoben. Danach wird die Meldung als Security Advisory veröffentlicht, auf Wunsch mit Nennung des Melders.
- Wenn eine Meldung abgelehnt wird, gibt es eine kurze Begründung.

## Was als Sicherheitslücke zählt

BierAlarm lädt Webseiten und PDF-Flugblätter von Supermärkten und zeigt die Daten im Home-Assistant-Dashboard an. Besonders interessant sind deshalb:

- Code- oder HTML-Einschleusung (XSS) über Daten aus Flugblättern, Webseiten oder der KI-Antwort
- Abstürze oder Hänger von Home Assistant durch manipulierte PDFs oder Antworten
- Weitergabe von Standort- oder anderen persönlichen Daten über das hinaus, was im README beschrieben ist
