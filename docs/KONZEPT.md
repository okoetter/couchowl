# watchit – Konzept und Beschlüsse

> Interne Planungsgrundlage (Deutsch). Ändert sich ein Beschluss, wird er hier angepasst,
> ein Eintrag kommt unter „Änderungsprotokoll“.

## Änderungsprotokoll
- **2026-11-06 – Meilenstein 0:**
  - **Python 3.15:** Django 6.1 und alle Abhängigkeiten unterstützen 3.15 offiziell (geprüft).
  - **`collectstatic` beim Image-Build statt beim Containerstart:** Das Image bleibt unveränderlich, und die App braucht keine Schreibrechte in `/app`. `migrate` läuft weiterhin beim Start.
  - **E-Mail über das neue `MAILERS`-Setting** von Django 6.1, weil die alten `EMAIL_*`-Settings veraltet sind. `EMAIL_URL` wird intern umgerechnet (`config/mail.py`).
  - **tini als Prozess 1** im Container: leitet Signale weiter und räumt beendete Prozesse auf.
  - **Kompilierte Übersetzungen (`.mo`) werden mit eingecheckt**, damit niemand gettext installieren muss, der nur entwickelt oder das Image baut. gettext braucht nur, wer Übersetzungen ändert.
  - **`localhost` und `127.0.0.1` sind immer in `ALLOWED_HOSTS`**, damit der Docker-Healthcheck funktioniert.

- **2026-11-06 – TMDB-Zugang:** Statt des kurzen API-Schlüssels (`?api_key=` in der URL) nutzen wir den **„API-Token für Lesezugriff“** als `Authorization: Bearer`-Header. So taucht er nicht in URLs oder Logs auf. Variable: `TMDB_API_TOKEN` (ersetzt `TMDB_API_KEY`).

- **2026-11-06 – Meilenstein 1 (Konten):**
  - **Login-Pflicht für alle Seiten** über Djangos `LoginRequiredMiddleware`; öffentlich sind nur Login, Registrierung per Einladung, Passwort-Reset, Healthcheck und Manifest.
  - **Einladungen:** Nach dem Speichern im Admin wird der Link direkt angezeigt (zum Kopieren). Mit SMTP und eingetragener E-Mail geht er automatisch per Mail raus; per Admin-Aktion erneut versendbar. Gültigkeit über `INVITATION_EXPIRY_DAYS` (Standard 7).
  - **E-Mail-Adresse optional, aber eindeutig**, falls angegeben (sonst ginge eine Reset-Mail an mehrere Konten). Im Profil änderbar.
  - **TMDB-Sprache im Profil als Auswahlliste** gängiger Sprachen statt Freitext.
  - **Reset-Links** gelten `PASSWORD_RESET_TIMEOUT_HOURS` (Standard 24 h) und funktionieren auch ohne SMTP (Admin-Aktion).
  - **Drosselung „Passwort vergessen“:** 5 Anfragen pro Stunde und IP, über Djangos Cache. Der Cache liegt dafür als Dateicache in `DATA_DIR/cache`, damit alle gunicorn-Prozesse ihn teilen.
  - **Formularfelder** in der Reihenfolge Label → Feld → Fehler → Hilfetext (klein, grau), über ein eigenes Feld-Template (`core/templates/forms/field.html`). Alle Fehler stehen einheitlich im roten Kasten.
  - **E2E-Tests mit Playwright jetzt eingerichtet** (`e2e/`, Marker `e2e`): Ablauf Einladung → Registrierung → Login sowie Screenshots wichtiger Seiten (hell/dunkel, Desktop/Handy), damit Claude die Optik selbst prüfen kann, bevor Oliver testet.
  - **django-axes 9.0.0** (erste Version mit offiziellem Django-6.1-Support): sperrt die Kombination aus Nutzername **und** IP nach 5 Fehlversuchen für 60 Minuten. Nur nach IP zu sperren wäre hinter dem Reverse Proxy gefährlich, weil dort alle Anfragen dieselbe IP haben (echte Client-IP über Proxy-Header folgt in Meilenstein 7).

- **2026-11-07 – Listen und „Folgen“:**
  - **Listen** können beliebig viele angelegt werden und enthalten jeweils Filme **und** Serien gemischt.
  - **„Folgen“ statt „verfolgen“:** Der Button auf der Serienseite heißt „Folgen“ (aktiv: „Gefolgt“), englisch „Follow“/„Following“. „Folgen“ ist der gängige Begriff (wie bei sozialen Netzwerken), „verfolgen“ klingt nach Hinterherjagen.
  - **Systemliste „Gefolgte Serien“** („Followed shows“): erscheint unter „Listen“ automatisch, sobald der Nutzer mindestens einer Serie folgt, und zeigt alle gefolgten Serien. Sie wird nicht gespeichert, sondern per Abfrage berechnet, ist nicht löschbar oder umbenennbar und lässt sich im Profil ein- und ausblenden (Standard: an). Umsetzung mit Meilenstein 3/4.

- **2026-11-07 – Englisch zuerst, Region als Haupteinstellung:**
  - Standardsprache der Oberfläche ist **Englisch** (`DEFAULT_LANGUAGE=en`); Deutsch ist eine Übersetzung.
  - Nicht angemeldete Besucher bekommen ihre Browsersprache, wenn es eine Übersetzung gibt, sonst Englisch.
  - **Die Region bestimmt die Sprachen:** Oberfläche = Hauptsprache des Landes, falls übersetzt, sonst Englisch; TMDB-Sprache = Hauptsprache + Land (AT → `de-AT`, FR → `fr-FR`). Beide Sprachen sind im Profil unter „Erweitert“ überschreibbar, Standard „Automatisch“.
  - **Region neuer Nutzer:** beim ersten Seitenaufruf nach dem Login aus der Browsersprache abgeleitet und gespeichert (`de-AT` → AT, nur `de` → DE). Klappt das nicht: `DEFAULT_REGION`, sonst US. Gilt auch für per `createsuperuser` angelegte Admins.
  - Region im Profil oben als Länderauswahl mit übersetzten Namen. Länderdaten (Namen, Amtssprachen) kommen aus **Babel** (Unicode CLDR).
  - `DEFAULT_TMDB_LANGUAGE` entfällt (ergibt sich aus der Region).
  - Einladungsmails gehen in der Sprache des einladenden Admins raus.

- **2026-11-07 – Zeitraum der Ankündigungen konfigurierbar:**
  - Das Dashboard zeigt neue Staffeln gefolgter Serien für die nächsten `ANNOUNCEMENT_MONTHS` Monate (Umgebungsvariable, Standard 3). In Monaten statt Tagen, weil man so darüber denkt und es so auf dem Dashboard steht.
  - Später (Backlog) zusätzlich pro Nutzer im Profil überschreibbar (z. B. 1/3/6/12 Monate, leer = Serverstandard), nach demselben Muster wie Sprache und Region.
  - Die Seite „Demnächst“ zeigt weiterhin alle bekannten Termine ohne Zeitlimit; das Dashboard ist nur eine Vorschau.

- **2026-11-07 – Meilenstein 2 (TMDB-Anbindung):**
  - **Neue App `catalog`** für alles rund um Filme und Serien (TMDB-Client, Suche, Poster, später Listen und Details).
  - **HTTP-Bibliothek `httpx`:** moderner Client; Tests ersetzen das Netzwerk über einen „Mock-Transport“, ganz ohne Zusatzpaket.
  - **Sprach-Fallback per Übersetzungsliste:** Die Detailabfrage holt mit `append_to_response=translations` alle Sprachen in einem Request. Fehlende Texte werden in dieser Reihenfolge aufgefüllt: exakte Sprache (`de-AT`) → Hauptland der Sprache (`de-DE`) → dieselbe Sprache, anderes Land → Englisch (`en-US`, dann andere) → Originaltitel bzw. leere Beschreibung. Hintergrund: Ein Live-Test zeigte, dass TMDB mit `de-AT` für viele Serien keine Beschreibung liefert, mit `de-DE` schon.
  - **Poster gehören zur Übersetzung,** nicht zum sprachneutralen Titel: TMDB liefert je nach Sprache ein anderes (lokalisiertes) Poster.
  - **Suchergebnisse werden nicht in der Datenbank gespeichert,** sondern 1 Stunde im Cache (pro Suchbegriff und Sprache). In die Datenbank kommen Titel erst, wenn sie gebraucht werden (Detailseite, Liste; ab Meilenstein 3). Die Suche zeigt Titel, Typ, Jahr, Poster und ggf. den Originaltitel, aber keine Beschreibung (die Suche liefert keinen Sprach-Fallback, und die Liste bleibt am Handy kompakt).
  - **Sortierung der Suchergebnisse:** zuerst exakte Titeltreffer (übersetzter oder Originaltitel; Groß-/Kleinschreibung, Akzente und Leerzeichen egal), darunter nach Jahr absteigend (Titel ohne Jahr ans Ende dieser Gruppe), z. B. „Dune“ 2021 vor 1984. Danach alle übrigen Treffer in der Reihenfolge von TMDB. TMDB sortiert nach Relevanz, die stark von der Popularität abhängt; so landete „Dark“ bei der Suche nach „dark“ nur auf Platz 4. Durchgehend nach Jahr zu sortieren wurde verworfen: Unter den 20 Treffern stünden dann oft unbekannte neue Titel vor den bekannten. Ein Umschalter „Relevanz / Neueste zuerst“ ist eine Option für später.
  - **Drosselung:** max. 20 TMDB-Anfragen pro Sekunde und Prozess; bei „429 Too Many Requests“ wartet der Client (höchstens 10 s) und versucht es bis zu zweimal erneut. Die Live-Suche wartet 300 ms nach dem letzten Tastendruck und ist auf 60 Suchen pro Minute und Nutzer begrenzt.
  - **Ist TMDB nicht erreichbar,** werden veraltete Daten aus der Datenbank angezeigt statt eines Fehlers.
  - **Poster-Proxy** unter `/posters/<größe>/<datei>`: nur Größen `w92`, `w185`, `w342`, `w500` und gültige TMDB-Dateinamen, nur für angemeldete Nutzer. Dateien liegen in `DATA_DIR/posters` und werden nie ungültig (neues Bild = neuer Dateiname); der Browser darf sie ein Jahr cachen. Aufräumen alter Poster: später (Backlog).
  - **Ohne `TMDB_API_TOKEN`** zeigt die Suche einen Hinweis statt eines Fehlers.
  - **Titel im Django-Admin** nur lesbar (Daten kommen von TMDB).
  - **TMDB-Logo** für die Attribution liegt lokal in `catalog/static/catalog/` (offizielles Logo von themoviedb.org/about/logos-attribution).

- **2026-11-07 – Meilenstein 3 (Listen und Filme):**
  - **Erste Liste „Watchlist“ automatisch:** Wer noch keine Liste hat, sieht im Menü „Zu Liste hinzufügen“ den Eintrag „Watchlist“; beim ersten Klick wird sie angelegt. Sie ist eine normale Liste (umbenennbar, löschbar). Auf der Seite „Listen“ wird nichts automatisch angelegt, sonst käme eine gelöschte Watchlist sofort zurück.
  - **Hinzufügen** über die Detailseite und zusätzlich über einen „+“-Button an jedem Suchergebnis. Das Menü zeigt alle Listen mit Häkchen (an/aus) und ein Feld „Neue Liste“. In der Suche wird es erst beim Öffnen geladen. Gibt es den Namen schon (Groß-/Kleinschreibung egal), wird die vorhandene Liste genommen.
  - **Listennamen** sind pro Nutzer eindeutig, unabhängig von Groß-/Kleinschreibung.
  - **Listen alphabetisch sortiert;** Sortieren per Ziehen kommt in den Backlog. Einträge einer Liste: zuletzt hinzugefügte zuerst.
  - **Einfache Serienseite schon jetzt** (Poster, Beschreibung, Status, „Zu Liste hinzufügen“); Staffeln und Folgen folgen in Meilenstein 4.
  - **Listen fragen TMDB nicht ab:** Sie zeigen die gespeicherten Texte, bei fehlender Sprache die nächstliegende gespeicherte (gleiche Reihenfolge wie der Sprach-Fallback, sonst irgendeine). Viele Titel auf einmal von TMDB zu laden wäre zu langsam. Beim Hinzufügen wird ein Titel bei Bedarf von TMDB geladen.
  - **Listenansicht** (Raster/kompakt) gilt pro Nutzer für alle Listen (Feld `list_layout`). Entfernen geht in der kompakten Ansicht per „×“ und überall über das Menü „Zu Liste hinzufügen“.
  - **Liste löschen** mit Bestätigungsseite; gesehene Filme bleiben gesehen.
  - **Gesehen-Datum** nur als Tag (ohne Uhrzeit), nicht in der Zukunft. Das Datum lässt sich auch ohne JavaScript ändern (aufklappbares `<details>`).
  - **Status von TMDB übersetzt** (z. B. „Released“ → „Veröffentlicht“, „Ended“ → „Beendet“).

- **2026-11-07 – Nachtrag Meilenstein 3 (Listenansicht):**
  - **Gesehen-Button direkt in der Liste** (für Filme): im Raster als runder Button im Poster-Eck, in der kompakten Ansicht neben „×“. Ein Klick setzt das heutige Datum, ein zweiter nimmt es zurück. War der Film schon gesehen, bleibt ein vorhandenes Datum erhalten.
    - Im Raster erscheint der leere Kreis (ungesehen) mit Maus nur beim Überfahren, damit das Raster ruhig bleibt; der grüne Haken ist immer sichtbar. Auf Touch-Geräten (kein Hover) bleibt der Kreis immer sichtbar, bei Tastaturbedienung erscheint er mit dem Fokus. Die kompakte Ansicht zeigt den Button weiterhin immer.
    - Der Kreis im Raster hat keinen Rand: Ungesehen ist er dunkel mit gedämpftem Haken, gesehen grün mit hellem Haken. Beim Überfahren wird er etwas größer und heller (ohne `transform: scale`, das macht die Kanten unscharf).
    - **Kleine htmx-Antworten statt ganzer Liste:** Gesehen-Button und Entfernen ersetzen nur den Button bzw. entfernen nur den Eintrag. Die ganze Liste neu zu laden baut alle Poster neu auf und lässt sie kurz aufblitzen. Nur wenn danach nichts mehr angezeigt wird, kommt der ganze Inhalt mit dem Hinweistext.
    - **Idiomorph** (htmx-Erweiterung vom htmx-Team, 0BSD, lokal ausgeliefert) für Live-Suche und Listenfilter: Statt das HTML auszutauschen, gleicht es alt und neu ab und ändert nur die Unterschiede. Einträge, die sichtbar bleiben, behalten ihr Poster und blitzen nicht. Einträge brauchen dafür eine feste `id`.
    - **Prüfung aller htmx-Stellen:** Gesehen-Button, Entfernen, Menü öffnen und „Gesehen“ auf der Detailseite ersetzen schon nur das Nötige. Der Ansichtswechsel ersetzt den ganzen Inhalt, weil sich das Layout komplett ändert. Ein Häkchen im Listen-Menü ersetzt das ganze (kleine, bilderlose) Menü; das bleibt bewusst so (vernachlässigbar, einfachere Fehleranzeige).
    - Das Menü „Zu Liste hinzufügen“ in der Suche wird bei jedem Öffnen neu geladen (kostet keine TMDB-Anfrage), damit es nach einer Aktualisierung der Ergebnisse immer stimmt.
  - **Filter** „Alle / Ungesehen / Gesehen“ und „Alle / Filme / Serien“. Sie stehen in der URL (`?status=unwatched&type=movie`): lesezeichenfähig, „Zurück“ funktioniert. Der Filter wird nicht gespeichert, jede Liste startet bei „Alle“. Aktionen (gesehen, entfernen, Ansicht) behalten den Filter; wer unter „Ungesehen“ etwas abhakt, sieht es verschwinden.
  - **Serien zählen bis Meilenstein 4 als ungesehen** und haben noch keinen Gesehen-Button.
  - **Mehrfachauswahl** mit Sammelaktionen (alle markieren, als gesehen markieren, entfernen) kommt in den Backlog: Mit dem Gesehen-Button ist der häufigste Fall abgedeckt, und am Handy bräuchte es einen eigenen Auswahlmodus. Neu bewerten, wenn Listen groß werden (z. B. nach dem JustWatch-Import).
  - **Für Meilenstein 4 beschlossen:**
    - Eine Serie gilt als **gesehen, wenn alle bereits ausgestrahlten Folgen gesehen sind** (ohne Specials/„Staffel 0“). Erscheint eine neue Folge, ist sie wieder ungesehen.
    - Der Button in der Liste zeigt bei Serien den **Fortschritt** (z. B. „12/20“). Ein Klick hakt die **nächste Folge** ab: die erste ungesehene, schon ausgestrahlte Folge ohne Specials. Dieselbe Regel nutzt das Dashboard („S2 E5 als Nächstes“, Meilenstein 5).
    - Da ein zweiter Klick die nächste Folge abhakt statt rückgängig zu machen, erscheint danach kurz **„S2 E5 gesehen · Rückgängig“**.

- **2026-11-07 – Meilenstein 4 (Serien und Folgen):**
  - **Staffeln und Folgen werden zusammen mit der Serie geladen** (gleiche 24-h-Regel), gebündelt über `append_to_response=season/1,season/2,…` (höchstens 20 Staffeln pro Anfrage). Serien, die vor dem Update gespeichert wurden, gelten als veraltet und werden beim nächsten Aufruf samt Staffeln geladen.
  - **Sprach-Fallback für Folgen:** TMDB hat für Folgen keine Übersetzungsliste und liefert z. B. mit `de-AT` nur Platzhalter („Folge 1“, keine Beschreibung). Reihenfolge: exakte Sprache → reine Sprache (`de`, liefert die deutschen Texte) → `en-US`. Weitere Sprachen werden nur für Staffeln angefragt, in denen noch Folgenbeschreibungen fehlen. Name und Beschreibung einer Folge kommen immer aus derselben Sprache. Für `de-DE` reicht meist eine Anfrage, für `de-AT` zwei.
  - **Folgen, die TMDB nicht mehr kennt, werden gelöscht** (samt Gesehen-Markierung). Folgen sind über Staffel- und Folgennummer verknüpft.
  - **Nur ausgestrahlte Folgen** (Datum heute oder früher) lassen sich abhaken; kommende Folgen zeigen „Erscheint am …“ und einen gestrichelten Kreis.
  - **Seriendetailseite:** Fortschritt („12 von 26 Folgen gesehen · Als Nächstes: S2 E5 …“), Staffeln als aufklappbare Abschnitte. Offen ist die Staffel mit der nächsten Folge; die anderen laden ihre Folgen erst beim Aufklappen (htmx), damit Serien mit Hunderten Folgen schnell bleiben. Ohne JavaScript öffnet der Link `?season=N` die Staffel. Specials („Staffel 0“) stehen unten.
  - **Folgenbeschreibungen** sind wegen Spoilern eingeklappt und öffnen sich per Klick auf den Folgentitel.
  - **Gesehen-Datum einer Folge in derselben Zeile** wie Ausstrahlung und Laufzeit („01.12.2017 · 52 Min. · ✓ 20.01.2024“), damit die Zeile beim Abhaken nicht höher wird. Deshalb beide Daten im kurzen Format; ein Klick aufs Datum öffnet das Formular darunter. Der Einheitlichkeit halber zeigen auch die Staffeln ihre Daten kurz („zuletzt am 20.01.2024“).
  - **Staffel abhaken** markiert alle ausgestrahlten Folgen; schon gesehene behalten ihr Datum. **Rückgängig für eine ganze Staffel fragt vorher nach**, weil sonst ein Fehlklick alle Daten löscht. Das Datum einer Staffel lässt sich ändern, sobald sie komplett gesehen ist, und gilt dann für alle ihre Folgen.
  - **„Folgen“ legt `UserSeries` an;** der Status „schaue gerade“ wird beim ersten Abhaken gesetzt (für das Dashboard in Meilenstein 5). Folgen und Abhaken sind unabhängig voneinander.
  - **Systemliste „Gefolgte Serien“** unter `/lists/followed/`: nutzt dieselbe Listenansicht (Filter, Raster/kompakt, Fortschritts-Button), aber ohne Umbenennen, Löschen, Entfernen und Typ-Filter. Zuletzt gefolgte Serie zuerst. Im Profil ein-/ausblendbar.
  - **Fortschritts-Button in Listen:** im Raster eine Pille „12/25“ auf dem Poster (noch nicht angefangene Serien erscheinen mit Maus erst beim Überfahren, wie der Film-Kreis), komplett gesehen ein grüner Haken ohne Klickfunktion. Die Meldung „S2 E5 gesehen · Rückgängig“ erscheint unten als kleines Fenster („Toast“) und verschwindet nach 6 Sekunden. Rückgängig lädt den Listeninhalt per Idiomorph neu (der Eintrag kann den Filter inzwischen verlassen haben). Ohne JavaScript gibt es nur die Meldung, ohne Rückgängig.
  - **Fortschritts-Button nennt beim Überfahren die nächste Folge:** Statt „2/26“ steht dann „S1 E3“, damit klar ist, was ein Klick tut (auch bei Tastaturfokus). Beide Texte liegen übereinander, die Pille ändert ihre Breite nicht. Format wie überall „S1 E3“, nicht „S01E03“. Handys haben kein Hover; dort zeigt die kompakte Ansicht unter dem Titel „Als Nächstes: S1 E3“ (im Raster nicht, damit es ruhig bleibt).
  - **Suche** zeigt „✓ Gesehen“ auch für komplett gesehene Serien.
  - **Datumsformat nach Region:** Die aktive Sprache enthält jetzt auch das Land (`en-gb`, `de-at`). Texte kommen weiter aus der Übersetzung der Sprache, Datumsformate aus Djangos Formaten für das Land (`en-gb`: 01/12/2017, `en-us`: 12/01/2017). Gibt es für die Kombination kein eigenes Format (z. B. Englisch + Deutschland), gilt das der Sprache. Im HTML steht entsprechend `lang="de-de"`.
  - **Date-Picker bleibt der des Browsers** (`<input type="date">`): Anzeigeformat und Wochenanfang bestimmt das Gerät des Nutzers, nicht watchit. Ein eigener JavaScript-Kalender wurde verworfen (am Handy schlechter bedienbar, zusätzliche Bibliothek).

- **2026-11-08 – Meilenstein 5 (Dashboard):**
  - **Das Dashboard fragt TMDB nie ab,** es zeigt nur, was in der Datenbank steht (wie die Listen). Neue Staffeln und Termine kommen beim nächsten Laden einer Serie (Detailseite, 24-h-Regel) und ab Meilenstein 6 über den täglichen Sync.
  - **„Weiterschauen“** zeigt Serien mit Status „schaue gerade“, die eine nächste Folge haben (erste ungesehene, schon ausgestrahlte Folge ohne Specials) und von denen mindestens eine Folge gesehen ist. Zuletzt geschaute Serie zuerst (spätestes Gesehen-Datum, bei gleichem oder unbekanntem Datum die zuletzt abgehakte Folge).
  - **Aufgeholte Serien verschwinden** aus „Weiterschauen“ (Status bleibt „schaue gerade“) und kommen zurück, sobald eine neue Folge ausgestrahlt ist. Serien ohne gesehene Folge (alles zurückgenommen, nur Specials gesehen) erscheinen nicht. „Pausiert“ und „fertig“ werden noch nirgends gesetzt; solche Serien würden nicht erscheinen.
  - **Karten mit Poster, „S2 E5 · Folgentitel“, Fortschrittsbalken und Haken-Button:** Ein Klick hakt die nächste Folge ab (heutiges Datum), danach erscheint wie in den Listen „S2 E5 gesehen · Rückgängig“. Ersetzt wird nur der Textteil der Karte (das Poster blitzt nicht); ist die Serie aufgeholt, verschwindet die Karte. Rückgängig lädt den Bereich per Idiomorph neu. Am Handy eine Karte pro Zeile, am Desktop mehrere nebeneinander; lange Titel brechen auf höchstens zwei Zeilen um.
  - **Ankündigungen:** Staffeln (ohne Specials) gefolgter Serien, die zwischen heute (einschließlich) und heute + `ANNOUNCEMENT_MONTHS` Monaten (einschließlich) starten; früheste zuerst. Eine Staffel startet mit ihrer ersten Folge (wie auf der Detailseite); das Staffeldatum von TMDB zählt nur, wenn noch keine Folge ein Datum hat. Beide weichen manchmal um einen Tag ab (z. B. „Die Ringe der Macht“ Staffel 3: Staffel 10.11., erste Folge 11.11.). Jede Zeile zeigt Poster, Serie, Staffelname, Sender und rechts Datum und „heute“/„morgen“/„in 12 Tagen“.
  - **Quelle = TMDB `networks`** (z. B. Netflix, ZDF), gespeichert als neues Feld `Title.networks` (Liste der Namen). Gespeicherte Serien gelten nach dem Update als veraltet und laden die Sender beim nächsten Aufruf. Streaming-Anbieter der Region kommen in Meilenstein 6 dazu.
  - **„Weiterschauen“ nur für gefolgte Serien:** „Folgen“ heißt jetzt „gehört auf mein Dashboard“, für beide Bereiche. Wer eine angefangene Serie nicht weiterschauen will, entfolgt ihr. Damit niemand das Folgen vergisst, **folgt das erste Häkchen einer Serie automatisch** (nur solange der Status noch leer ist, also beim ersten Mal). Nach bewusstem Entfolgen folgt weiteres Abhaken nicht erneut. Das ersetzt „Folgen und Abhaken sind unabhängig voneinander“ aus Meilenstein 4. Eine Migration folgt allen schon angefangenen Serien, sonst verschwänden sie vom Dashboard. Verworfen: ein eigener Button „Ausblenden“ (Status „pausiert“) und „Nicht mehr folgen“ direkt auf der Karte.
  - **Ankündigungen nur für gefolgte Serien,** nicht für Serien, die nur auf einer Liste stehen (wie im Konzept vorgesehen).
  - **Staffelnamen ohne Übersetzung:** Fehlt der Name in der gewünschten Sprache, schickt TMDB den englischen Platzhalter „Season 3“. Der wird als leer gespeichert, angezeigt wird dann der übersetzte Standardname („Staffel 3“). Bereits gespeicherte Platzhalter bereinigt eine Migration. Bei Folgen kommt das nicht vor (dort liefert TMDB „Folge 1“ in der angefragten Sprache).
  - **Leere Zustände** erklären, wie man den Bereich füllt (Folge abhaken bzw. Serien folgen). Die Überschrift „Dashboard“ ist nur für Screenreader da; sichtbar sind die Abschnittsüberschriften.
  - **Sprung zur nächsten Folge** („Als Nächstes: S1 E3“ auf der Detailseite): Die feste Navigation am Desktop verdeckt die Folge nicht mehr (`scroll-padding-top`). Die angesprungene Folge leuchtet kurz auf, weil der Browser am Seitenende (vor allem am Handy) nicht weiter scrollen kann und die Folge sonst mitten auf dem Bildschirm steht. Damit das auch beim zweiten Klick auf denselben Link klappt, startet die erste eigene JavaScript-Datei `core/static/core/watchit.js` die Animation neu.
- **2026-11-08 – Idee für den Backlog: Ankündigungen für Filme.** Kein eigenes „Folgen“ für Filme: Ein noch ungesehener Film auf einer Liste heißt schon „will ich sehen“. Angekündigt werden Kino- und (falls bekannt) Digitalstart für die Region des Benutzers; ein Film im Kino bleibt angekündigt, bis der Digitalstart vorbei ist. Details in `docs/ROADMAP.md`.

- **2026-11-08 – Meilenstein 6 (Sync und „Demnächst“):**
  - **Täglicher Sync `manage.py sync_tmdb`** um 03:30 UTC (supercronic, `docker/crontab`): lädt alle Serien neu, denen jemand folgt oder die jemand gerade schaut (Status „schaue gerade“, auch ohne Folgen). Details, Staffeln, Folgen, Termine und Anbieter, jeweils in den TMDB-Sprachen der betroffenen Nutzer. Serien, die in den letzten 6 Stunden geladen wurden (z. B. weil jemand sie geöffnet hat), werden übersprungen; `--force` lädt alle. Ein Fehler bei einer Serie bricht den Lauf nicht ab; am Ende steht eine Zusammenfassung im Log. Filme werden nicht synchronisiert (erst mit den Film-Ankündigungen aus dem Backlog).
  - **Streaming-Anbieter kosten keinen zusätzlichen Request:** Sie kommen per `append_to_response=watch/providers` mit der Detailabfrage. TMDB liefert dabei alle rund 130 Regionen; gespeichert werden nur die Regionen unserer Nutzer plus `DEFAULT_REGION`.
  - **Speicherung als JSON-Feld `Title.watch_providers`** (`{"DE": {"link": …, "flatrate": [{id, name, logo}], …}}`) statt der geplanten Tabelle `TitleProvider`: Anbieter werden immer zusammen mit dem Titel gelesen, nie titelübergreifend abgefragt. Eine Region ohne Angebote wird als `{}` gespeichert. Fehlt die Region des Nutzers ganz (z. B. nach einem Regionswechsel im Profil), lädt die Detailseite den Titel sofort neu.
  - **Anbieter auf den Detailseiten von Filmen und Serien:** „Verfügbar in Deutschland“ mit Logos, gruppiert nach Abo, Kostenlos (inkl. „mit Werbung“), Leihen, Kaufen; darunter „Quelle: JustWatch“ und ein Link zu allen Angeboten bei TMDB. Logos laufen über den Poster-Proxy (`w92`). JustWatch steht zusätzlich im Footer, weil die TMDB-Nutzungsbedingungen die Nennung verlangen und Anbieter auch auf Dashboard und „Demnächst“ erscheinen.
  - **Quelle in Ankündigungen und auf „Demnächst“:** Sender (`networks`) plus Abo- und Gratis-Anbieter der Region, ohne Leihen/Kaufen. Varianten eines schon genannten Namens fallen weg („Netflix Standard with Ads“ nach „Netflix“), „ZDFneo“ nach „ZDF“ bleibt (nur ganze Wörter).
  - **Seite „Demnächst“:** alle bekannten Staffelstarts gefolgter Serien ohne Zeitlimit, plus pro laufender Staffel (Start vor heute, noch Folgen mit Datum ab heute) die nächste Folge („S3 E4 · Folgentitel“). Nach Monaten gruppiert, früheste zuerst. Wie das Dashboard nur aus der Datenbank. Staffeln, die heute oder später starten, erscheinen nur einmal (mit ihrem Start). Das Dashboard bleibt bei Staffelstarts und verlinkt auf „Alle Termine“.
  - **„Alle aktualisieren“** auf „Demnächst“ lädt die gefolgten Serien des Nutzers in seiner Sprache neu, beendete und abgesetzte Serien ausgenommen (sie bekommen keine neuen Termine; der tägliche Sync lädt sie trotzdem, wegen der Anbieter). Läuft direkt im Request, höchstens einmal pro 5 Minuten und Nutzer. Der Button zeigt währenddessen einen Lade-Kreisel (`data-busy` in `watchit.js`).
  - **„Jetzt aktualisieren“** auf jeder Detailseite (Film und Serie) mit „Daten von TMDB, Stand …“; höchstens 10-mal pro Minute und Nutzer.
  - **Aufgeholte Serien bleiben in „Weiterschauen“, solange ihre Staffel läuft** (ersetzt „Aufgeholte Serien verschwinden“ aus Meilenstein 5): Sind alle ausgestrahlten Folgen gesehen und hat die nächste Folge einer schon gestarteten Staffel ein Datum in der Zukunft, bleibt die Karte mit dieser Folge stehen. Statt des Hakens zeigt sie Datum und „in 3 Tagen“. Solche wartenden Karten stehen nach den Serien, die man gerade schauen kann, früheste Folge zuerst. Ohne bekanntes Datum oder wenn die nächste Staffel noch gar nicht begonnen hat, verschwindet die Karte wie bisher; ein Staffelstart bleibt eine Ankündigung. Nach dem Abhaken der letzten ausgestrahlten Folge wird die Karte direkt zur wartenden Karte.

- **2026-11-08 – Nachfrage „Frühere Folgen auch abhaken?“** (eigener Commit zwischen Meilenstein 6 und 7, kein eigener Meilenstein): Wird auf der Serienseite eine Folge abgehakt und sind davor ausgestrahlte Folgen (ohne Specials) noch ungesehen, fragt ein Hinweis unten: „S3 E5 gesehen. Davor sind noch 12 Folgen offen.“ mit [Nur Staffel 3 (4)] [Alle (12)] [Nein]; „Nur Staffel …“ nur, wenn auch ältere Staffeln Lücken haben, sonst ein Button „Ja, abhaken“. Beim Abhaken einer ganzen Staffel fragt er nach den älteren Staffeln. Erst abhaken, dann fragen (kein modaler Dialog vorher: wer bewusst Folgen überspringt, soll nicht jedes Mal angehalten werden). Die Frage hat **kein Timeout**, sie bleibt bis zur Antwort oder bis zur nächsten Aktion, die sie ersetzt; die Antwort zeigt „12 Folgen gesehen · Rückgängig“ mit dem üblichen Timeout. Die früheren Folgen bekommen **„Datum unbekannt“** (man hat sie ja nicht heute gesehen); schon gesehene behalten ihr Datum. Dashboard und Listen fragen nie: Sie haken immer die nächste Folge ab, dort gibt es keine Lücke. Ohne JavaScript erscheint die Frage nach dem Neuladen.

- **2026-11-11 – TMDB-Bewertungen** (eigener Commit vor Meilenstein 7): `vote_average` und `vote_count` kommen ohnehin mit der Detail- und Suchanfrage; gespeichert als `Title.vote_average`/`vote_count`. Anzeige „★ 8,4“ in Suche und Listen (Raster und kompakt) neben dem Jahr, auf der Detailseite mit Stimmenzahl („★ 8,4 (32.000 Stimmen)“). In Suche und Listen erst ab 10 Stimmen (`MIN_VOTES`), weil „10,0 aus 2 Stimmen“ wenig sagt; auf der Detailseite ab 1 Stimme, dort steht die Anzahl dabei. Zahlen im Format der Region (8,4 / 8.4). Aktualisiert wird die Bewertung wie alle Titeldaten (24-h-Regel beim Öffnen, „Jetzt aktualisieren“, Sync für Serien); Filme auf Listen bleiben bis zum nächsten Öffnen auf altem Stand, das ist bei Bewertungen vertretbar. Die Migration markiert alle gespeicherten Titel als veraltet. Sortieren nach Bewertung kommt mit dem Listen-Sortieren aus dem Backlog. Eigene Bewertungen gestrichen (nicht gebraucht).

- **2026-11-13 – Planung Meilenstein 7:**
  - **Aufgeteilt in 7a (Betrieb), Namenssuche, 7b (Open Source) und 7c (CI und Release).** Der Projektname „watchit“ ist nur ein Platzhalter. 7a hängt nicht am Namen; 7b und 7c schon (Repo, Image-Name, Über-Seite, README, Lizenz). Umbenennen ist jetzt billig (fast nur Texte, die Django-Apps heißen `core`, `accounts`, `catalog`), wird aber teuer nach öffentlichem Repo und Image und nach dem NAS-Deployment (Volume-Name, installierte PWA, Lesezeichen). Deshalb steht der Name vor 7b fest.
  - **Lizenz AGPL-3.0:** Copyleft auch für Webdienste (wer eine veränderte Version betreibt, muss den Code offenlegen), üblich bei Self-Hosted-Apps. Die Über-Seite verlinkt deshalb den Quellcode.
  - **Images auf GHCR** (GitHub Container Registry, Login über das automatische `GITHUB_TOKEN`).
  - **Reverse Proxy generisch:** watchit funktioniert ohne, mit einem oder mit mehreren Proxys, mit IPv4 und IPv6; die Doku bleibt herstellerneutral. Oliver nutzt den Synology-Proxy, sein Zugang (neuer Anschluss, evtl. nur IPv6) ist noch offen.
  - **Backup: Die App liefert nur eine stimmige Kopie,** das eigentliche Sichern (externe Platte, Cloud, Versionen) macht der Host, z. B. Hyper Backup. Grund: Eine laufende SQLite-Datei einfach zu kopieren kann eine kaputte Kopie ergeben; nur die App kann über die SQLite-Backup-API sicher kopieren. **Kein `restore`-Befehl:** Wiederherstellen heißt Container stoppen und die Datei zurückkopieren, das steht in der Doku. `BACKUP_KEEP` Standard 3 statt 7, die Versionen verwaltet der Host.
  - **Erst `1.0.0-rc.1`:** CI baut das Image, Oliver installiert es auf dem NAS; `1.0.0` folgt erst, wenn es dort läuft.
  - **Content Security Policy ins Backlog:** Die Standardversion von Alpine.js braucht `unsafe-eval`, eine strenge Policy erst mit der CSP-Version von Alpine.

## Context
Oliver will im leeren Ordner `/home/oliver/Projekte/watchit` zusammen mit Claude per Vibe-Coding eine Webapp bauen. Es ist sein erstes Vibe-Coding-Projekt. Er arbeitet mit EndeavourOS und VSCodium, ist ein erfahrener Programmierer (JavaScript) und lernt gerade Python.

watchit ist eine selbst gehostete Watchlist für Filme und Serien. Sie läuft in Docker auf seiner Synology DS218+, ist aus dem Internet erreichbar und soll später als Open Source veröffentlicht werden.

## Beschlüsse

### Produkt
- **Nutzer:** mehrere Konten, **nur auf Einladung** (keine offene Registrierung); die App ist aus dem Internet erreichbar
- **Datenquelle:** TMDB-API. JustWatch scheidet aus: keine offizielle API, und die Nutzungsbedingungen verbieten die inoffizielle Nutzung. Streaming-Anbieter kommen über TMDB `/watch/providers` (Daten von JustWatch, mit Attribution).
- **MVP-Features:**
  1. **Eigene Listen (immer privat):** beliebig viele, z. B. „Meine Watchlist“ oder „Mit Familie sehen“; jede Liste kann Filme und Serien gemischt enthalten, hinzugefügt über die TMDB-Suche
     - zusätzlich die **Systemliste „Gefolgte Serien“**: automatisch, sobald man mindestens einer Serie folgt; nicht löschbar; im Profil ein-/ausblendbar (Standard: an)
  2. **Serien-Dashboard:** Serien, die ich gerade schaue, jeweils mit der nächsten Folge (z. B. „S2 E5 als Nächstes“)
  3. **Folgen-Tracking:** jede Folge einzeln abhaken oder eine ganze Staffel auf einmal als gesehen markieren
  4. **„Folgen“** pro Serie (Button „Folgen“/„Gefolgt“)
  5. **Ankündigungen auf dem Dashboard:** neue Staffeln gefolgter Serien in den nächsten 3 Monaten (über `ANNOUNCEMENT_MONTHS` einstellbar), sobald das Datum feststeht, mit Quelle (TMDB `networks`, z. B. Netflix oder ZDF, plus deutsche Streaming-Anbieter, soweit bekannt)
  6. **Menü „Demnächst“:** alle kommenden Staffeln gefolgter Serien mit bekanntem Datum
  7. **Filme als „gesehen“ markieren**; die Suche zeigt an, ob ein Titel schon gesehen wurde
  8. **Gesehen-Datum:**
     - Beim Abhaken einer Folge, einer Staffel oder eines Films wird das Datum gespeichert und angezeigt
     - Gespeichert wird **nur das letzte Datum**, ein erneutes Abhaken überschreibt es; keine Historie mehrfacher Sichtungen
     - Eine Staffel zeigt das Datum ihrer zuletzt gesehenen Folge
     - Abhaken rückgängig machen entfernt das Datum
     - Beim Abhaken wird sofort das heutige Datum gespeichert. Ein Klick aufs Datum öffnet die Bearbeitung: anderes Datum oder „unbekannt“ (`watched_at` leer, aber gesehen). Bei einer Staffel gilt die Änderung für alle Folgen dieser Staffel.
- **Datenschutz:**
  - Keine externen Ressourcen: HTMX (mit Idiomorph), Pico, Alpine.js und Schriften werden selbst ausgeliefert, kein CDN
  - **Alles läuft über den Server, der Browser kontaktiert TMDB nie direkt:**
    - **Texte und Metadaten** (Titel, Beschreibungen, Staffeln, Folgen, Anbieter): Der Server fragt TMDB ab und speichert die Ergebnisse pro Sprache in der Datenbank; angezeigt wird immer aus der Datenbank
    - **Poster und Bilder:** Der Server lädt sie von TMDB und cacht sie auf der Platte (Volume, nur erlaubte Bildgrößen)
    - **Aktualisierung** über die drei Wege aus „TMDB-Datenabruf“: Der Button „Jetzt aktualisieren“ erneuert Texte **und** Poster eines Titels, „Alle aktualisieren“ und der tägliche Sync entsprechend für alle betroffenen Titel
  - Optionale Links zu Impressum und Datenschutzerklärung im Footer über `IMPRINT_URL` und `PRIVACY_URL`
- **Mehrsprachigkeit:**
  - keine hartkodierten Texte; Sprachdateien (gettext `.po`); Quelltexte Englisch, **Englisch ist Standard**, Deutsch die erste Übersetzung
  - **Region** (Land für Streaming-Anbieter, Veröffentlichungsdaten, Altersfreigaben) ist die Haupteinstellung:
    - neue Nutzer: beim ersten Login aus der Browsersprache abgeleitet (`de-AT` → AT, `de` → DE), sonst `DEFAULT_REGION`, sonst US
    - im Profil oben als Länderauswahl änderbar
  - **Sprachen folgen der Region**, unter „Erweitert“ im Profil überschreibbar (leer = automatisch):
    - Oberfläche: Hauptsprache des Landes, falls übersetzt, sonst Englisch
    - TMDB-Sprache: Hauptsprache + Land (z. B. `de-AT`); fehlt eine Beschreibung in dieser Sprache, wird die englische angezeigt
  - nicht angemeldete Besucher: Browsersprache, falls übersetzt, sonst `DEFAULT_LANGUAGE` (Standard `en`)
- **Später, nicht im MVP:** siehe Abschnitt „Backlog (ToDo)“

### Konten und E-Mail
- **„Passwort vergessen“** über Djangos eingebauten Reset-Ablauf (Link per Mail, zeitlich begrenztes Token)
  - Die Antwort verrät nicht, ob eine E-Mail-Adresse existiert
  - Anfragen werden gedrosselt
- **E-Mail ist optional:**
  - **Ohne SMTP-Konfiguration** wird der Link „Passwort vergessen“ ausgeblendet und durch „Wende dich an den Administrator“ ersetzt. Der Admin kann im Django-Admin per Aktion einen Reset-Link bzw. Einladungslink erzeugen und z. B. per Messenger weitergeben.
  - **Mit SMTP** werden Einladungen und Reset-Links zusätzlich per Mail verschickt
- **SMTP-Konfiguration über `.env`, nicht im Admin-Bereich:**
  - `EMAIL_URL`, z. B. `smtp+tls://user:pass@mail.example.com:587`, plus `DEFAULT_FROM_EMAIL`
  - Begründung: Secrets bleiben außerhalb der Datenbank; das ist Docker-Standard; es funktioniert schon vor dem ersten Login; kein Zusatzcode nötig
  - Befehl `manage.py sendtestemail` (in Django eingebaut) zum Prüfen
  - lokal: Console-Backend, Mails erscheinen im Terminal

### Optik und Bedienung
- **Seiten:**
  - Dashboard (Start)
  - Listen
  - Demnächst
  - Suche (Suchfeld immer sichtbar, Live-Ergebnisse)
  - Detailseiten für Filme und Serien (Staffeln und Folgen abhaken, „Folgen“, „Aktualisieren“, „Zu Liste hinzufügen“)
  - Profil
  - Django-Admin für Nutzer und Einladungen
- **Navigation:** auf dem Handy eine Leiste unten (Dashboard, Listen, Demnächst, Suche, Profil), auf dem Desktop oben
- **Listenansicht** per Schalter umschaltbar zwischen Poster-Raster und kompakter Liste; die Wahl wird pro Nutzer gespeichert
- **Farbschema:** folgt dem System (hell/dunkel), im Profil überschreibbar
- **PWA ab der ersten Version:** Web-App-Manifest, App-Icon, Vollbildmodus; erfordert HTTPS (in Produktion über den Reverse Proxy, lokal reicht `localhost`)

### Technik
- **Django (aktuelle 6.x) + HTMX**, Python: die neueste Version, die Django und alle Abhängigkeiten offiziell unterstützen (voraussichtlich 3.14; in Meilenstein 0 prüfen; Wechsel auf 3.15, sobald unterstützt), Paketverwaltung mit `uv`
  - Endpoints liefern HTML-Fragmente über Django-Template-Partials
  - punktuell Alpine.js, wo Logik im Browser nötig ist
- **CSS:** Pico CSS (klassenlos, ohne Build-Schritt; responsiv für die Nutzung am Handy)
- **TMDB-Datenabruf (drei Wege):**
  1. **Bei Bedarf:** beim Öffnen einer Film- oder Seriendetailseite und beim Hinzufügen zu einer Liste werden die Daten von TMDB geladen, wenn sie fehlen oder älter als 24 h sind
  2. **Täglich automatisch:** für alle gefolgten und gerade geschauten Serien (neue Staffeln/Folgen, Air-Dates, Anbieter)
  3. **Manuell erzwungen:**
     - Button „Jetzt aktualisieren“ auf der Detailseite (eine Serie)
     - Button „Alle aktualisieren“ (z. B. auf „Demnächst“)
     - Befehl `manage.py sync_tmdb` für die Kommandozeile
     - Buttons pro Nutzer kurz gedrosselt, um das TMDB-Kontingent zu schonen
- **Datenbank:** SQLite als Standard (schont die 2 GB RAM des NAS), PostgreSQL optional über `DATABASE_URL`
- **Konfiguration:** ausschließlich über Umgebungsvariablen (`django-environ`); Secrets nie im Repository
- **Betrieb: ein einziger Container** (Compose-Datei mit einem Dienst `watchit`)
  - Prozessmanager **honcho** (`Procfile`) startet zwei Prozesse:
    - `web`: gunicorn mit whitenoise für statische Dateien
    - `cron`: supercronic, startet täglich `manage.py sync_tmdb` und `manage.py backup`
  - Stirbt ein Prozess, beendet honcho den Container, und Docker startet ihn per `restart: unless-stopped` neu; dazu ein Healthcheck auf den Webserver
  - Logs beider Prozesse gemeinsam in `docker logs` (Präfix `web |` bzw. `cron |`)
  - PostgreSQL ist optional ein zweiter Container (auskommentiert in der Compose-Datei); Standard ist SQLite
  - Images für amd64 und arm64
  - **Image:** Basis `python:3.x-slim` (Debian), Multi-Stage-Build
    - Builder-Stage: uv installiert die Abhängigkeiten (ohne Dev-Abhängigkeiten) in ein venv und kompiliert Bytecode vor
    - Finale Stage: nur slim + venv + Code + supercronic; kein uv, kein Compiler, kein Cache
    - läuft als Nicht-Root-Nutzer
    - Ziel: ca. 60 MB komprimiert
    - Alpine verworfen (musl, Wheel-Probleme); Distroless verworfen (keine Shell, Python-Version an Debian gebunden)
  - Beim Containerstart laufen automatisch `migrate` und `collectstatic`
- **Backups:**
  - `manage.py backup` sichert konsistent im laufenden Betrieb (SQLite-Backup-API) nach `/data/backups`
  - Rotation über `BACKUP_KEEP` (Standard 3); das eigentliche Sichern dieses Ordners macht der Host
  - kein `restore`-Befehl: Wiederherstellen = Container stoppen, Datei zurückkopieren (dokumentiert)
  - Bei PostgreSQL wird auf `pg_dump` verwiesen
- **Versionen und Updates:**
  - Semantic Versioning (1.2.3), `CHANGELOG.md` im Format „Keep a Changelog“
  - Docker-Tags `1.2.3`, `1.2` und `latest`
  - Ein Update besteht aus neuem Image und Neustart; Migrationen laufen beim Start
  - Version im Footer und im Healthcheck sichtbar
- **Sicherheit:**
  - Django-Standards (CSRF, sichere Cookies, HSTS hinter dem Proxy)
  - `django-axes` gegen Brute-Force-Angriffe
  - Einladungstokens mit Ablaufdatum
- **Tests:** pytest-django
- **Ablage der Beschlüsse:**
  - `docs/KONZEPT.md`: zum Nachlesen für Oliver
  - `CLAUDE.md`: Stack und Konventionen für Claude
  - Git ab dem ersten Schritt

## Datenmodell (Entwurf)
- `User` (eigenes User-Modell von Anfang an): `region`, `ui_language`, `tmdb_language` (leer = aus Region), `theme`, `list_layout` (Raster/kompakt); ab Meilenstein 3/4 `show_followed_list` (Systemliste „Gefolgte Serien“ anzeigen, Standard an)
- `Invitation`: Token, E-Mail (optional), `created_by`, `expires_at`, `used_by`
- `Title`: `tmdb_id` + `media_type` (Film/Serie) sowie sprachneutrale Daten (Poster, Daten, Status, Networks)
- `TitleTranslation`: Titel, Sprache, Name, Beschreibung (Cache pro Sprache)
- `Season` und `Episode`: Nummer, Air-Date; sprachabhängige Texte jeweils in Übersetzungstabellen
- `UserList` (Nutzer, Name; alphabetisch sortiert, Name pro Nutzer eindeutig) und `ListItem` (Liste, Titel, hinzugefügt am)
- `UserSeries`: Nutzer, Serie, `following` (Button „Folgen“), Status (schaue gerade / pausiert / fertig); wird beim ersten Abhaken automatisch auf „schaue gerade“ gesetzt
- `WatchedEpisode`: Nutzer, Folge, `watched_at` (nullable = Datum unbekannt; eindeutig pro Nutzer und Folge; nur das letzte Datum)
- `WatchedMovie`: Nutzer, Film, `watched_at` (nullable; eindeutig pro Nutzer und Film; nur das letzte Datum)
- Streaming-Anbieter: JSON-Feld `Title.watch_providers` pro Region (Anbieter, Logo, Art: Abo/kostenlos/Werbung/Leihen/Kaufen), nur für die Regionen der Nutzer
- Ankündigungen werden per Abfrage berechnet (kommende `Season.air_date` gefolgter Serien), nicht gespeichert.

## Arbeitsweise
- **Ablauf pro Meilenstein:**
  1. Claude erklärt kurz, was gebaut wird
  2. Claude setzt um und schreibt Tests dazu
  3. Claude führt die Tests aus
  4. Claude nennt konkrete Testschritte für den Browser
  5. Oliver testet und prüft den Diff in VSCodium (Quellcodeverwaltung)
  6. Commit erst nach Olivers OK
- **Tests:**
  - Jedes Feature bekommt Tests (pytest-django), Schwerpunkt auf der Logik:
    - nächste Folge, Ankündigungen und Zeitfenster
    - Staffel abhaken
    - Einladungen und Zugriffsschutz (niemand sieht fremde Listen)
    - Sprach-Fallback
  - TMDB wird in Tests nie live aufgerufen, sondern mit gespeicherten Beispielantworten (Fixtures) gemockt
  - Claude führt die Tests nach jeder Änderung aus, bevor Oliver testen soll
  - Zusätzlich verhindert ein Git-pre-commit-Hook (Framework `pre-commit`: ruff für Lint und Format, dann pytest) jeden Commit mit roten Tests, auch Olivers eigene
  - Später (Meilenstein 7) zusätzlich GitHub Actions, die nach Olivers Push laufen
  - **Testebenen:**
    1. **Unit-Tests:** reine Logik (z. B. Berechnung der nächsten Folge) → pre-commit
    2. **Integrationstests** mit dem Django-Test-Client: Request → View → Datenbank → Template, inkl. Zugriffsrechte und HTMX-Fragmente → pre-commit; der größte Teil der Tests
    3. **End-to-End-Tests** mit Playwright (pytest-playwright, Chromium) für wenige Kernabläufe:
       - Einladung → Registrierung → Login
       - Suchen → zu Liste hinzufügen
       - Folge/Staffel abhaken → Dashboard aktualisiert sich
       - laufen am Ende jedes Meilensteins und später in CI, nicht im pre-commit (zu langsam)
    4. **Optionaler Live-Check gegen TMDB:** manuell mit echtem Key, erkennt Änderungen an der TMDB-API (Marker `live`, standardmäßig übersprungen)
    5. **Docker-Smoke-Test** in Meilenstein 7: Image bauen, starten, Healthcheck prüfen
- **Zwei Umgebungen, derselbe Code; Unterschiede nur über `.env`:**
  - **Lokal (Entwicklung):**
    - `uv run manage.py runserver` auf `http://localhost:8000`
    - automatisches Neuladen bei Codeänderungen und ausführliche Fehlerseiten (`DEBUG=True`)
    - eigene SQLite-Datei im Projektordner (per `.gitignore` ausgeschlossen)
    - TMDB-Sync bei Bedarf manuell per Befehl
  - **Live (NAS):**
    - ein Docker-Container (gunicorn + supercronic unter honcho), `DEBUG=False`, whitenoise
    - SQLite in einem Docker-Volume
  - **Zwischenschritt:** vor einem Deployment `docker compose up --build` auch lokal ausführen, um produktionsnahe Unterschiede (statische Dateien, `DEBUG=False`, Security-Settings) vorab zu erkennen
- **Dokumentation im Repo** (Englisch, außer `docs/KONZEPT.md`):
  - `README.md`: für Nutzer und Self-Hoster (was ist watchit, Screenshots, Schnellstart mit Docker Compose, Konfiguration über Umgebungsvariablen)
  - `CONTRIBUTING.md`: Entwicklungsumgebung für **Linux, macOS und Windows**, Tests ausführen, Code-Stil, neue Übersetzung anlegen
  - `docs/deployment.md`: allgemeine Docker-Anleitung, unabhängig vom Host (Compose-Datei, Volumes und Backup, Updates, Betrieb hinter einem beliebigen Reverse Proxy mit HTTPS, nötige Proxy-Header); keine herstellerspezifischen Anleitungen
  - `docs/administration.md`: für Admins
    - ersten Admin anlegen (`docker compose exec web python manage.py createsuperuser` oder einmalig über `DJANGO_SUPERUSER_*`-Variablen)
    - Einladungen erstellen und verschicken
    - Nutzer deaktivieren
    - Passwort-Reset ohne E-Mail
    - E-Mail-Versand einrichten und testen
  - `docs/KONZEPT.md` (Deutsch): Beschlüsse und Begründungen für Oliver
  - `docs/ROADMAP.md`: Backlog bzw. ToDo-Liste (siehe unten), bei Erledigung abhaken
  - `CHANGELOG.md`
  - Teil der Definition of Done jedes Meilensteins: Ändert sich das Setup, wird `CONTRIBUTING.md` bzw. `README.md` im selben Commit angepasst
- **Plattformunabhängigkeit:**
  - Keine Bash-only-Skripte; alle Entwicklerbefehle laufen über `uv run …`, das unter Linux, macOS und Windows gleich funktioniert
  - Python-Version über `.python-version` festgelegt (uv installiert sie automatisch)
  - `.gitattributes` (einheitliche Zeilenenden, wichtig für Windows) und `.editorconfig`
  - Docker: unter macOS/Windows über Docker Desktop (Windows auch per WSL2)
  - Geprüft wird das in Meilenstein 7 per GitHub-Actions-Matrix (Ubuntu, macOS, Windows) für Unit- und Integrationstests, weil Claude lokal nur unter Linux testen kann
- **Voraussetzungen auf Olivers Rechner (EndeavourOS):**
  - `git` und `uv` (`sudo pacman -S git uv`)
  - Docker (`sudo pacman -S docker docker-compose docker-buildx`, `sudo systemctl enable --now docker`, Nutzer in die Gruppe `docker`)
  - für E2E-Tests installiert `playwright install chromium` einen Browser im Nutzerverzeichnis
  - Claude prüft zu Beginn von Meilenstein 0, was schon vorhanden ist
- **Wissen sichern:**
  - Ändern sich Beschlüsse, wird `docs/KONZEPT.md` aktualisiert
  - Neue Konventionen landen in `CLAUDE.md`
  - Neue Claude-Sitzungen können so jederzeit nahtlos weitermachen (eine frische Sitzung pro Meilenstein hält den Kontext schlank)
- **Erklärungen:** Django- und Python-Konzepte erklärt Claude beim ersten Auftreten kurz (Oliver lernt Python)
- **Sprache im Repo:** Code, Kommentare, Commit-Messages und README auf Englisch; die Diskussion mit Oliver auf Deutsch; Oberfläche Deutsch über Sprachdateien
- **Git:** nur lokal, Commits direkt auf `main`. **Claude pusht niemals und legt keine Remotes an, das macht ausschließlich Oliver.** (Regel kommt in `CLAUDE.md`.)
- **Berechtigungen:** Claude Code im Standardmodus, d. h. Oliver bestätigt Dateiänderungen und Befehle einzeln
- **Secrets:** TMDB-API-Key (kostenloser TMDB-Account nötig) nur in `.env`, die per `.gitignore` ausgeschlossen ist; `.env.example` dokumentiert alle Variablen

## Umsetzung in Meilensteinen
Jeder Meilenstein wird einzeln umgesetzt, getestet und committet.

0. **Projektgerüst**
   - `git init` und `.gitignore`; `docs/KONZEPT.md` und `CLAUDE.md` aus diesem Plan anlegen
   - Django-Projekt mit `uv`, eigenem User-Modell und Settings aus Umgebungsvariablen
   - i18n-Grundgerüst (LocaleMiddleware + Middleware für die Nutzersprache, `locale/de`)
   - Basis-Template mit HTMX und Pico (lokal ausgeliefert, kein CDN), Navigation (Leiste unten auf dem Handy), Farbschema, PWA-Manifest und Icon
   - `Dockerfile` (Entrypoint mit `migrate` und `collectstatic`), `docker-compose.yml`, `.env.example`, pytest, pre-commit
   - Versionsnummer `0.1.0`, `CHANGELOG.md`, `docs/ROADMAP.md`
1. **Konten**
   - Einladungslinks (über das Django-Admin erstellen)
   - Registrierung per Einladung, Login und Logout
   - Profilseite mit Sprache und TMDB-Sprache, Region unter „Erweitert“
   - Passwort ändern; „Passwort vergessen“ (nur sichtbar, wenn SMTP konfiguriert ist)
   - Admin-Aktion „Reset-/Einladungslink erzeugen“
   - E-Mail-Versand über `EMAIL_URL`
   - `docs/administration.md`
   - django-axes
2. **TMDB-Anbindung**
   - Client mit Caching, Sprach-Fallback und Rate-Limit
   - Live-Suche mit HTMX
   - Poster-Proxy mit Cache
   - TMDB-Attribution im Footer
3. **Listen und Filme**
   - Listen anlegen, umbenennen und löschen
   - Titel aus der Suche hinzufügen und entfernen
   - Listenansicht (Poster-Raster oder kompakte Liste)
   - Filmdetailseite mit „gesehen“ und Datum
4. **Serien und Folgen**
   - Seriendetailseite mit Staffeln und Folgen
   - Folge bzw. Staffel abhaken per HTMX, mit Anzeige des Gesehen-Datums
   - „Folgen“ (Flag pro Serie) und Systemliste „Gefolgte Serien“
   - Serien in Listen: Fortschritt und „nächste Folge gesehen“ per Klick (mit „Rückgängig“), Serien im Gesehen-Filter
5. **Dashboard**
   - Serien, die ich gerade schaue, mit der nächsten Folge
   - Ankündigungen für die nächsten 3 Monate (`ANNOUNCEMENT_MONTHS`)
6. **Sync und „Demnächst“**
   - `sync_tmdb`-Befehl für gefolgte und gerade geschaute Serien, eingebunden über supercronic im Container
   - Streaming-Anbieter pro Region
   - Seite „Demnächst“
7. **Produktionsreife und Open Source** (aufgeteilt, siehe Änderungsprotokoll 2026-11-13)
   - **7a – Betrieb:** Security-Settings hinter dem Reverse Proxy (ohne, einer oder mehrere Proxys; IPv4 und IPv6), echte Client-IP für Brute-Force-Schutz und Drosselung, `backup`-Befehl mit Rotation, eingebunden über supercronic
   - **Namenssuche** und Umbenennung vor 7b
   - **7b – Open Source:** Über-Seite (Version, Lizenz, Link zum Quellcode, TMDB-Logo und -Hinweis, JustWatch), `IMPRINT_URL` und `PRIVACY_URL`, Lizenz AGPL-3.0, README und `docs/deployment.md` (allgemeines Docker-Deployment)
   - **7c – CI und Release:** GitHub Actions (Tests mit Matrix Ubuntu/macOS/Windows, E2E-Tests, Docker-Smoke-Test), Multi-Arch-Images auf GHCR mit Versions-Tags, `1.0.0-rc.1`; `1.0.0` nach erfolgreichem NAS-Deployment

## Backlog (ToDo, nach dem MVP)
Wird in Meilenstein 0 als `docs/ROADMAP.md` angelegt.
- **JustWatch-Import (CLI, kein GUI):** `manage.py import_justwatch <datei> --user <name> [--dry-run]`
  - übernimmt Watchlist(s), gesehene Filme und Folgen sowie gefolgte Serien
  - Abgleich mit TMDB über IMDb-ID (TMDB `/find`) oder sonst über Titel und Jahr
  - nicht zuordenbare Einträge landen in einem Bericht
  - Vorher klären: wie Oliver seine Daten aus JustWatch bekommt. JustWatch hat keine offizielle Export-Funktion; möglich sind eine DSGVO-Datenauskunft (Art. 15/20), ein Export über Drittanbieter-Tools oder das eigene Profil. Format erst prüfen, wenn ein echter Export vorliegt.
- Datenexport als JSON und Konto selbst löschen; später Import aus Trakt, TV Time oder Letterboxd (gemeinsame Import-Infrastruktur mit dem JustWatch-Import)
- Listen-Komfort:
  - Sortieren (Hinzufügedatum, Titel, Jahr, TMDB-Bewertung); Filter nach gesehen/ungesehen und Film/Serie gibt es seit Meilenstein 3
  - Mehrfachauswahl mit Sammelaktionen: alle markieren/entmarkieren, auf einmal als gesehen markieren oder von der Liste entfernen
  - in der Suche „ist schon auf Liste X“ anzeigen
  - Listen per Ziehen sortieren (bis dahin alphabetisch)
  - Notiz pro Listeneintrag
- Barrierefreiheit gezielt prüfen und verbessern (Labels, Tastatur, Kontrast, Screenreader bei HTMX-Updates)
- Content Security Policy (braucht die CSP-Version von Alpine.js)
- Benachrichtigungen per E-Mail oder Push bei neuen Staffeln
- Öffentliche JSON-API (z. B. django-ninja)
- Zeitraum der Ankündigungen pro Nutzer im Profil einstellbar (1/3/6/12 Monate, leer = `ANNOUNCEMENT_MONTHS`)
- Weitere UI-Sprachen
- Poster-Cache aufräumen (Poster, die kein gespeicherter Titel mehr nutzt)

## Später zu entscheiden
- ~~Open-Source-Lizenz~~ → entschieden: AGPL-3.0 (2026-11-13)
- Zugang aus dem Internet: watchit bleibt generisch (mit oder ohne Reverse Proxy); Olivers eigener Weg (Synology-Proxy, neuer Anschluss evtl. nur IPv6) ist noch offen
- Endgültiger Projektname („watchit“ ist ein Platzhalter) → vor Meilenstein 7b

## Verifikation
- Pro Meilenstein:
  - `uv run pytest` muss grün sein
  - `uv run manage.py runserver` lokal starten; Oliver prüft die Funktion im Browser
- Ab Meilenstein 0: `docker compose up --build` lokal; die Startseite unter `http://localhost:8000` muss laden
- Mehrsprachigkeit: im Profil die Region oder die Sprache ändern → UI und TMDB-Texte wechseln
- Sync: `manage.py sync_tmdb` manuell ausführen → Ankündigungen erscheinen auf dem Dashboard
- Zum Abschluss: Deployment auf der DS218+ über den Container Manager und Zugriff über die eigene Domain
