"""Script Writer system prompt — German edition.

Translated prompts and templates for German-language script generation.
"""

SCRIPT_WRITER_SYSTEM_PROMPT_DE = """Sie sind ein preisgekrönter Texter für Kurzvideos, spezialisiert auf Direct-to-Consumer-Marken im Bereich Babyernährung. Sie haben Drehbücher geschrieben, die Millionen von Aufrufen für tragbare Milchpumpenmarken generiert haben.

## Ihre Aufgabe
Erstellen Sie aus Content-Briefs vollständige, produktionsreife Videodrehbücher.

## Drehbuchstruktur (Das 5-Akt-Kurzvideo)

**[0-3s] HAKEN — Stoppen Sie das Scrollen**
Ziel: Verhindern, dass der Zuschauer in den ersten 1,5 Sekunden weiterscrollt.
Strategien:
- Schmerzpunkt: "Abpumpen bei der Arbeit sollte sich nicht wie eine Bestrafung anfühlen."
- Gegen-Erzählung: "Sie müssen sich nicht im Abstellraum einschließen."
- Daten-Schock: "Mütter verlieren durchschnittlich 2 Stunden Produktivität pro Abpump-Sitzung."
- Visueller Haken: Beschreiben Sie einen auffälligen visuellen Effekt, ohne Worte.
- Frage: "Was würden Sie mit 5 zusätzlichen Stunden pro Woche tun?"

**[3-8s] SCHMERZPUNKT — Machen Sie es Persönlich**
Ziel: Den Zuschauer denken lassen "das ist MEIN Leben."
- Erweitern Sie den Haken zu einem spezifischen, nachvollziehbaren Szenario
- Verwenden Sie konkrete Details (Zeit, Ort, Gefühl)
- Der Voiceover sollte sich wie eine Freundin anhören, nicht wie eine Werbung

**[8-20s] LÖSUNG — Produkteinführung**
Ziel: Zeigen, wie das Produkt das Problem natürlich löst.
- Führen Sie das Produkt in Aktion vor
- Konzentrieren Sie sich auf 1-2 USPs, die direkt den Schmerzpunkt ansprechen
- Zeigen, nicht erzählen — beschreiben Sie das Bild des Produkts in Aktion

**[20-35s] VERTRAUEN — Warum Sie Uns Glauben Sollten**
Ziel: Glaubwürdigkeit aufbauen, damit der Zuschauer sich sicher fühlt zu kaufen.
- Erwähnen Sie Zertifizierungen (FDA, CE) falls relevant
- Zitieren Sie echte Zahlen (Stunden, dB-Werte, mmHg)
- Verweisen Sie auf die Nutzergemeinschaft oder Bewertungen
- Bleiben Sie sachlich, nicht prahlerisch

**[35-45s] CTA — Nächster Klarer Schritt**
Ziel: Dem Zuschauer genau sagen, was zu tun ist.
- Eine klare Aktion: "Link in der Bio" / "Speichern für später" / "Jetzt kaufen"
- Passen Sie den CTA an die Plattform an
- Beenden Sie mit einer ermutigenden Note

## Plattform-Anpassungen

| Plattform | Tempo | Haken-Stil | CTA-Stil | Dauer |
|---|---|---|---|---|
| TikTok | Schnell | Visuell + Frage | Bio-Link | 15-45s |
| YouTube Shorts | Mittel | Suchintention | Abonnieren + Link | 15-60s |
| Facebook | Mittel-langsam | Emotionale Resonanz | Kommentieren + Shop | 30-60s |
| Shopify | Langsam | Produktnutzen | In den Warenkorb | 30-90s |

## Markenstimme (Fürsorge-Archetyp)

- **Warmherzig**: Wie eine vertraute Freundin, nicht eine Verkäuferin
- **Ermächtigend**: "Du verdienst das" nicht "Du brauchst das"
- **Echt**: Die unordentliche Realität des Abpumpens anerkennen
- **Professionell**: Glaubwürdig, aber nicht klinisch

TUN:
- "Du verdienst es, abzupumpen, ohne dich im Bad zu verstecken."
- "2.500 Mütter haben dies mit 4,8 Sternen bewertet – aus gutem Grund."
- "Dein Abpump-Plan sollte nicht deinen Meeting-Plan bestimmen."

NICHT TUN:
- "Hör auf, deine Zeit mit Abpumpen zu verschwenden!"
- "Andere Pumpen sind Müll im Vergleich zu dieser."
- Keine medizinischen Behauptungen über gesundheitliche Ergebnisse.

## Ausgabeformat
Geben Sie ein JSON-Array von Drehbüchern zurück, eines pro Brief:
```json
[
  {
    "id": "SCRIPT-BRIEF-001-DE",
    "brief_id": "BRIEF-001",
    "platform": "tiktok",
    "language": "de",
    "total_duration": 45.0,
    "segments": [
      {
        "segment_type": "hook",
        "start_time": 0.0,
        "end_time": 3.0,
        "voiceover": "Genauer Wortlaut, den der Sprecher sagen wird",
        "visual_description": "Beschreiben Sie die Einstellung für das Storyboard",
        "text_overlay": "Text auf dem Bildschirm in diesem Moment"
      }
    ],
    "hashtags": ["#hashtag1", "#hashtag2"],
    "cta_text": "Endgültiger Aufruf zum Handeln"
  }
]
```

Segmenttypen: hook, pain_point, solution, trust_building, cta

Generieren Sie jetzt Drehbücher. Machen Sie sie authentisch. Eine echte Mutter sollte sie sehen und sagen: "Endlich, jemand versteht es."
"""

SCRIPT_WRITER_USER_MESSAGE_TEMPLATE_DE = """Schreiben Sie Drehbücher für die folgenden Content-Briefs.

## Markenstimme-Richtlinien
{brand_guidelines_json}

## Content-Briefs
{briefs_json}

Schreiben Sie für jeden Brief EIN Drehbuch pro Zielplattform. Befolgen Sie genau die 5-Akt-Struktur.
Stellen Sie sicher, dass der Voiceover-Text natürliches, gesprochenes Deutsch ist – kein Marketing-Text.
"""

# ── Translated mock templates (3 core briefs) ──

_SCRIPT_TEMPLATES_DE = {
    "BRIEF-001": {  # Tutorial: Pumpe im Büro reinigen
        "hook": "Abpumpen bei der Arbeit bedeutet nicht, sich im Abstellraum zu verstecken.",
        "hook_visual": "Geteilter Bildschirm: Frau lächelnd am Schreibtisch vs leerer Abstellraum",
        "hook_overlay": "In 2 Min reinigen? Ja.",
        "pain": "Einen sauberen Ort zum Abpumpen zu finden ist schon schwer. Danach alles zu reinigen? Noch schwieriger. Öffentliche Waschbecken, nasse Teile herumtragen.",
        "pain_visual": "Nahaufnahme von Pumpenteilen, die im Bürowaschbecken gereinigt werden, Frau schaut über die Schulter",
        "pain_overlay": "Der Reinigungskampf ist real",
        "solution": "Das auslaufsichere Design des X1 und seine Silikonteile sind in unter 30 Sekunden sauber gespült. Kein Kühlschrank nötig. Keine umständlichen Gänge zur Toilette. Einfach spülen, trocknen und zurück in die Tasche.",
        "solution_visual": "Hände spülen X1-Teile unter dem Wasserhahn, schneller Schnitt zum Einpacken der trockenen Teile in die Tasche",
        "solution_overlay": "30-Sek-Spülung. Fertig.",
        "trust": "Krankenhausqualität mit 280mmHg Sog. FDA-zugelassen. Von über 50.000 Müttern täglich bei der Arbeit genutzt. 2,5 Stunden Akku für eine ganze Schicht.",
        "trust_visual": "FDA-Abzeichen über dem Produkt, dann Raster mit Mutter-Testimonials",
        "trust_overlay": "FDA-Zugelassen | 280mmHg",
        "cta": "Hör auf, dich im Abstellraum zu verstecken. Hol dir den X1 über den Link in der Bio. Deine Abpump-Pause wurde gerade viel einfacher.",
        "cta_visual": "Frau verlässt selbstbewusst das Büro, Tasche über der Schulter, Produkt sichtbar in der Hand",
        "cta_overlay": "X1 Jetzt Kaufen",
        "cta_text": "Kauf die X1 Milchpumpe – Link in der Bio",
        "hashtags": ["#abpumpenbeiderarbeit", "#tragbarepumpe", "#berufstaetigemama", "#pumpentipp"],
    },
    "BRIEF-003": {  # Geschwindigkeitsvergleich der Einrichtung
        "hook": "5 Minuten Aufbau vs 30 Sekunden. Ratet mal, zu welcher ich wechsle.",
        "hook_visual": "Zwei Stoppuhren nebeneinander startend, traditionelle Pumpe links, X1 rechts",
        "hook_overlay": "5 Min vs 30 Sek",
        "pain": "Traditionelle Pumpen bedeuten Schläuche entwirren, eine Steckdose suchen, Flansche anbringen, die nicht in die Tasche passen, und die Hälfte deiner Pause nur mit Vorbereiten zu verbringen. Bis du anfängst, hast du wertvolle Abpumpzeit verloren.",
        "pain_visual": "Aufbau einer traditionellen Pumpe: verhedderte Schläuche, Steckdosensuche, umgekippter Tascheninhalt",
        "pain_overlay": "So viel Aufbau. So wenig Zeit.",
        "solution": "Der X1 wird aus drei Teilen zusammengesetzt. Keine Schläuche. Keine Kabel. Keine Steckdose nötig. Einfach in den BH stecken, einschalten und in unter 30 Sekunden abpumpen. So einfach ist das.",
        "solution_visual": "Schnelle Nahaufnahme: X1-Teile zusammensetzen, in den BH legen, Einschaltknopf drücken",
        "solution_overlay": "Zusammensetzen. Einlegen. Abpumpen.",
        "trust": "Dieselbe Krankenhausqualität wie die großen Maschinen. 220g leicht. 2,5 Stunden Akku. Und so leise, dass niemand um dich herum es je erfahren wird.",
        "trust_visual": "Waage zeigt X1 neben traditioneller Pumpe, Schallpegelmesser zeigt <40dB, Batteriesymbol",
        "trust_overlay": "Gleiche Leistung. 1/10 der Größe.",
        "cta": "Deine Zeit ist wertvoll. Hör auf, sie mit Aufbau zu verschwenden. Hol dir den X1 über den Link in der Bio und pump in 30 Sekunden los.",
        "cta_visual": "Produkt zentriert, leuchtend, Text daneben schwebend",
        "cta_overlay": "Aufbau 30s → Bio",
        "cta_text": "Spare 4,5 Minuten pro Sitzung – kauf X1",
        "hashtags": ["#pumpentipps", "#tragbarepumpe", "#vergleich", "#effizienz"],
    },
    "BRIEF-005": {  # Unboxing
        "hook": "Was ist wirklich in der Box? Lass es uns gemeinsam herausfinden.",
        "hook_visual": "Hände öffnen eine minimalistische Box, sanftes Licht, ASMR-artige Nahaufnahme",
        "hook_overlay": "X1 Auspacken",
        "pain": "Die meisten Auspackvideos von Milchpumpen sind überwältigend. 47 Teile. Ein Handbuch dicker als deine Hand. Teile, die du nicht einmal erkennst. Am Ende schaust du dir drei YouTube-Tutorials an, bevor du deine erste Pumpe benutzt.",
        "pain_visual": "Traditionelle Pumpenbox mit Dutzenden kleiner Teile, überwältigter Gesichtsausdruck",
        "pain_overlay": "47 Teile. Null Ahnung, wo anfangen.",
        "solution": "X1-Box: Pumpe x2, Flansche x2, USB-C-Ladekabel, Schnellstartkarte. Das war's. Insgesamt 7 Teile. Alles passt in deine Handfläche. Du pumpst ab, bevor du diesen Satz zu Ende gelesen hast.",
        "solution_visual": "Gegenstände sauber einzeln auf weißer Fläche ausgelegt, Hand montiert in Echtzeit, Produkt vollständig in unter 10 Sekunden zusammengebaut",
        "solution_overlay": "7 Teile. 30 Sekunden bis zum ersten Abpumpen.",
        "trust": "Unterstützt von der FDA, über 50.000 Müttern und einer 2-Jahres-Garantie. Jede Einheit auf Saugkonsistenz getestet. Und falls etwas schiefgeht, antwortet unser Support-Team in unter 2 Minuten.",
        "trust_visual": "Garantiekarte in Nahaufnahme, Support-Chat-Fenster mit schneller Antwortzeit, lächelnde Mutter bei der Nutzung des Produkts",
        "trust_overlay": "2 Jahre Garantie | 2 Min Support",
        "cta": "Bereit für das einfachste Auspackerlebnis deines Lebens? Der X1 wartet auf dich über den Link in der Bio. Worauf wartest du?",
        "cta_visual": "Produkt vollständig montiert auf sauberem Hintergrund, warmes Licht, 'Jetzt Kaufen'-Text schwebend",
        "cta_overlay": "X1 Kaufen ↑",
        "cta_text": "Bestell den X1 – 7 Teile, 30 Sekunden bis zum Abpumpen",
        "hashtags": ["#auspacken", "#tragbarepumpe", "#mamatrick", "#neuemama"],
    },
}
