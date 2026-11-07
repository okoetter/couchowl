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
  5. **Ankündigungen auf dem Dashboard:** neue Staffeln gefolgter Serien in den nächsten 3 Monaten, sobald das Datum feststeht, mit Quelle (TMDB `networks`, z. B. Netflix oder ZDF, plus deutsche Streaming-Anbieter, soweit bekannt)
  6. **Menü „Demnächst“:** alle kommenden Staffeln gefolgter Serien mit bekanntem Datum
  7. **Filme als „gesehen“ markieren**; die Suche zeigt an, ob ein Titel schon gesehen wurde
  8. **Gesehen-Datum:**
     - Beim Abhaken einer Folge, einer Staffel oder eines Films wird das Datum gespeichert und angezeigt
     - Gespeichert wird **nur das letzte Datum**, ein erneutes Abhaken überschreibt es; keine Historie mehrfacher Sichtungen
     - Eine Staffel zeigt das Datum ihrer zuletzt gesehenen Folge
     - Abhaken rückgängig machen entfernt das Datum
     - Beim Abhaken wird sofort das heutige Datum gespeichert. Ein Klick aufs Datum öffnet die Bearbeitung: anderes Datum oder „unbekannt“ (`watched_at` leer, aber gesehen). Bei einer Staffel gilt die Änderung für alle Folgen dieser Staffel.
- **Datenschutz:**
  - Keine externen Ressourcen: HTMX, Pico, Alpine.js und Schriften werden selbst ausgeliefert, kein CDN
  - **Alles läuft über den Server, der Browser kontaktiert TMDB nie direkt:**
    - **Texte und Metadaten** (Titel, Beschreibungen, Staffeln, Folgen, Anbieter): Der Server fragt TMDB ab und speichert die Ergebnisse pro Sprache in der Datenbank; angezeigt wird immer aus der Datenbank
    - **Poster und Bilder:** Der Server lädt sie von TMDB und cacht sie auf der Platte (Volume, nur erlaubte Bildgrößen)
    - **Aktualisierung** über die drei Wege aus „TMDB-Datenabruf“: Der Button „Jetzt aktualisieren“ erneuert Texte **und** Poster eines Titels, „Alle aktualisieren“ und der tägliche Sync entsprechend für alle betroffenen Titel
  - Optionale Links zu Impressum und Datenschutzerklärung im Footer über `IMPRINT_URL` und `PRIVACY_URL`
- **Mehrsprachigkeit:**
  - keine hartkodierten Texte; Sprachdateien (gettext `.po`); zum Start Deutsch
  - Standardwerte per Umgebungsvariable: `DEFAULT_LANGUAGE`, `DEFAULT_TMDB_LANGUAGE`, `DEFAULT_REGION`
  - pro Nutzer im Profil einstellbar: UI-Sprache und TMDB-Sprache (z. B. `de-DE`); fehlt eine Beschreibung in der gewählten Sprache, wird die englische angezeigt
  - **Region** (Land für Streaming-Anbieter, Veröffentlichungsdaten, Altersfreigaben):
    - wird automatisch aus der TMDB-Sprache abgeleitet (`de-DE` → `DE`)
    - nur unter „Erweitert“ im Profil überschreibbar (z. B. deutsche Texte, aber österreichische Anbieter)
    - Feld `region` am User leer bedeutet „automatisch“
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
  - Rotation über `BACKUP_KEEP` (Standard 7)
  - `manage.py restore <datei>` stellt eine Sicherung wieder her
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
- `User` (eigenes User-Modell von Anfang an): `ui_language`, `tmdb_language`, `region`; ab Meilenstein 3/4 `show_followed_list` (Systemliste „Gefolgte Serien“ anzeigen, Standard an)
- `Invitation`: Token, E-Mail (optional), `created_by`, `expires_at`, `used_by`
- `Title`: `tmdb_id` + `media_type` (Film/Serie) sowie sprachneutrale Daten (Poster, Daten, Status, Networks)
- `TitleTranslation`: Titel, Sprache, Name, Beschreibung (Cache pro Sprache)
- `Season` und `Episode`: Nummer, Air-Date; sprachabhängige Texte jeweils in Übersetzungstabellen
- `UserList` (Nutzer, Name, Reihenfolge) und `ListItem` (Liste, Titel, hinzugefügt am)
- `UserSeries`: Nutzer, Serie, `following` (Button „Folgen“), Status (schaue gerade / pausiert / fertig); wird beim ersten Abhaken automatisch auf „schaue gerade“ gesetzt
- `WatchedEpisode`: Nutzer, Folge, `watched_at` (nullable = Datum unbekannt; eindeutig pro Nutzer und Folge; nur das letzte Datum)
- `WatchedMovie`: Nutzer, Film, `watched_at` (nullable; eindeutig pro Nutzer und Film; nur das letzte Datum)
- `TitleProvider`: Titel, Region, Anbieter, Typ (Abo/Kauf/kostenlos)
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
5. **Dashboard**
   - Serien, die ich gerade schaue, mit der nächsten Folge
   - Ankündigungen für die nächsten 3 Monate
6. **Sync und „Demnächst“**
   - `sync_tmdb`-Befehl für gefolgte und gerade geschaute Serien, eingebunden über supercronic im Container
   - Streaming-Anbieter pro Region
   - Seite „Demnächst“
7. **Produktionsreife und Open Source**
   - Security-Settings hinter dem Reverse Proxy, Healthcheck
   - `backup`/`restore`-Befehle mit Rotation, eingebunden über supercronic
   - `IMPRINT_URL` und `PRIVACY_URL`
   - README und `docs/deployment.md` (allgemeines Docker-Deployment), Lizenz
   - GitHub Actions: Tests (Matrix Ubuntu/macOS/Windows), E2E-Tests, Multi-Arch-Images mit Versions-Tags
   - Release `1.0.0`

## Backlog (ToDo, nach dem MVP)
Wird in Meilenstein 0 als `docs/ROADMAP.md` angelegt.
- **JustWatch-Import (CLI, kein GUI):** `manage.py import_justwatch <datei> --user <name> [--dry-run]`
  - übernimmt Watchlist(s), gesehene Filme und Folgen sowie gefolgte Serien
  - Abgleich mit TMDB über IMDb-ID (TMDB `/find`) oder sonst über Titel und Jahr
  - nicht zuordenbare Einträge landen in einem Bericht
  - Vorher klären: wie Oliver seine Daten aus JustWatch bekommt. JustWatch hat keine offizielle Export-Funktion; möglich sind eine DSGVO-Datenauskunft (Art. 15/20), ein Export über Drittanbieter-Tools oder das eigene Profil. Format erst prüfen, wenn ein echter Export vorliegt.
- Datenexport als JSON und Konto selbst löschen; später Import aus Trakt, TV Time oder Letterboxd (gemeinsame Import-Infrastruktur mit dem JustWatch-Import)
- Listen-Komfort:
  - Sortieren und Filtern (Hinzufügedatum, Titel, Jahr, Film/Serie)
  - in der Suche „ist schon auf Liste X“ anzeigen
  - Notiz pro Listeneintrag
- Barrierefreiheit gezielt prüfen und verbessern (Labels, Tastatur, Kontrast, Screenreader bei HTMX-Updates)
- Bewertungen
- Benachrichtigungen per E-Mail oder Push bei neuen Staffeln
- Öffentliche JSON-API (z. B. django-ninja)
- Weitere UI-Sprachen (zuerst Englisch)

## Später zu entscheiden
- Open-Source-Lizenz (z. B. MIT oder AGPL-3.0) → spätestens bei Meilenstein 7
- Zugang aus dem Internet: Synology-Reverse-Proxy mit Let's Encrypt oder Cloudflare Tunnel → bei Meilenstein 7

## Verifikation
- Pro Meilenstein:
  - `uv run pytest` muss grün sein
  - `uv run manage.py runserver` lokal starten; Oliver prüft die Funktion im Browser
- Ab Meilenstein 0: `docker compose up --build` lokal; die Startseite unter `http://localhost:8000` muss laden
- Mehrsprachigkeit: im Profil die Sprache auf Englisch stellen → UI und TMDB-Texte wechseln (sobald eine englische `.po`-Datei existiert)
- Sync: `manage.py sync_tmdb` manuell ausführen → Ankündigungen erscheinen auf dem Dashboard
- Zum Abschluss: Deployment auf der DS218+ über den Container Manager und Zugriff über die eigene Domain
