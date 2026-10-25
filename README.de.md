# PLENTICORE MCP

[![CI](https://github.com/NemoN/plenticore-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/NemoN/plenticore-mcp/actions/workflows/ci.yml)
[![Lizenz: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

[English](README.md) · Deutsch

MCP-Server für KOSTAL PLENTICORE-Wechselrichter. Er liest Leistungswerte,
Energiezähler und Ereignisse, zeigt Einstellungen an und ändert Parameter,
die dem Anlagenbetreiber über die lokale REST-API zugänglich sind.
Die Verbindung verwendet [pykoplenti](https://github.com/stegm/pykoplenti)
und das [offizielle MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk).

Getestet mit einem PLENTICORE plus 8.5, Firmware `01.30.12092`, API `0.2.0`.
Andere Modelle und Firmwareversionen wurden noch nicht getestet. Messwerte und
Einstellungen ermittelt der Server am verbundenen Gerät.

## Einrichtung

Voraussetzungen sind [uv](https://docs.astral.sh/uv/getting-started/installation/)
und Python ab Version 3.11.

```bash
git clone https://github.com/NemoN/plenticore-mcp.git
cd plenticore-mcp
uv sync --frozen
cp .env.example .env
chmod 600 .env
```

In `.env` die Geräteadresse und das Anlagenbetreiber-Passwort der lokalen
Weboberfläche eintragen:

```dotenv
PLENTICORE_URL=http://plenticore.example
PLENTICORE_PASSWORD=replace-locally
PLENTICORE_TIMEOUT=20
PLENTICORE_VERIFY_SSL=true
PLENTICORE_READ_ONLY=true
```

Die URL enthält keinen `/api/v1`-Anhang. Das Beispiel startet mit Schreibsperre.
Für Änderungen `PLENTICORE_READ_ONLY=false` setzen. Ohne diese Variable ist der
Code-Standard `false`; Änderungsaufrufe liefern zunächst eine Vorschau.

Anmeldung und Messwerte prüfen:

```bash
uv run --frozen plenticore-mcp --check
```

Der Check liest Status und Messwerte, ohne Einstellungen zu ändern. Exit-Code 0
bedeutet Erfolg, 1 einen Verbindungs- oder API-Fehler und 2 eine ungültige
Konfiguration. Ohne `--check` wartet der Prozess auf einen MCP-Client.

## MCP-Client verbinden

Für Clients mit `mcpServers`-JSON beide absoluten Pfade ersetzen:

```json
{
  "mcpServers": {
    "plenticore": {
      "command": "uv",
      "args": [
        "run", "--frozen", "--directory", "/absolute/path/plenticore-mcp",
        "plenticore-mcp", "--env-file", "/absolute/path/plenticore.env"
      ]
    }
  }
}
```

Die Konfigurationsdatei kann die `.env` im Checkout oder eine separate private
Datei sein. Falls der Client `uv` nicht findet, den vollständigen Programmpfad
angeben. Der Client startet den stdio-Prozess bei Bedarf. Standardausgabe ist
für das MCP-Protokoll reserviert.

Unter [examples/](examples/) stehen JSON- und Codex-TOML-Beispiele. Die
[Konfigurationsanleitung](docs/configuration.md) beschreibt Umgebungsvariablen,
HTTPS und Verbindungen von anderen Rechnern.

### Streamable HTTP

```bash
uv run --frozen plenticore-mcp --transport streamable-http --port 8001
```

Die MCP-Adresse lautet `http://127.0.0.1:8001/mcp`. Der Listener bindet an
Loopback und besitzt keine MCP-Authentifizierung. Für einen entfernten Client
einen SSH-Tunnel verwenden.

## Werkzeuge

Alle Namen beginnen mit `plenticore_`. Die [Werkzeugreferenz](docs/tools.md)
enthält Argumente und Standardwerte.

| Werkzeug ohne Präfix | Funktion |
| --- | --- |
| `status` | API- und Firmwareversion, Sitzung, Schreibsperre |
| `list_modules` | Vom Wechselrichter angebotene Module |
| `list_process_data` | Messwert-IDs suchen, mit Pagination |
| `read_process_data` | Ausgewählte Messwerte lesen |
| `overview` | Energiefluss, AC, PV-Strings, Batterie und Netzzähler, soweit vorhanden |
| `battery` | Verfügbare Batteriemesswerte |
| `energy` | Energiestatistik für `Day`, `Month`, `Year` oder `Total` |
| `events` | Letzte Ereignisse auf Deutsch oder Englisch |
| `list_settings` | Einstellungs-IDs, Typen, Einheiten, Rechte und Grenzen |
| `read_settings` | Ausgewählte aktuelle Einstellungen lesen |
| `update_settings` | Änderungen prüfen, als Vorschau zeigen oder schreiben und rücklesen |

Beispielaufträge an einen verbundenen Assistenten:

> Zeige den Ertrag von heute und diesem Monat sowie die aktuelle AC-Leistung.

> Lies die Batterieeinstellungen und ihre aktuellen Werte. Zeige eine Vorschau
> der von mir gewünschten Änderung, bevor du sie anwendest.

## Messwerte und Einheiten

Werte und Vorzeichen bleiben so erhalten, wie der Wechselrichter sie liefert.
Manche Firmwareversionen geben ein leeres `unit` zurück. Das bedeutet nicht,
dass der Wert dimensionslos ist. `Dc_P` kann Batterieleistung enthalten.
Für die Solarleistung die einzelnen PV-Strings heranziehen.

Energieperioden folgen der Geräteuhr. Der Server speichert keine Messwerthistorie
und bietet keine Abfrage beliebiger Zeiträume. Fehlende Messwerte erscheinen
unter `missing`, nicht endliche Zahlen als JSON-`null`. Ein vorhandener
Batterie-Datenpunkt bestätigt keine physisch angeschlossene Batterie.

## Einstellungen ändern

Zuerst `list_settings` und `read_settings` abfragen. Neue Werte als Zeichenketten
in den nativen Geräteeinheiten übergeben. `update_settings` verwendet zunächst
`dry_run=true` und zeigt bestehende und geplante Werte. Mit `dry_run=false`
schreibt der Server die Änderung und liest anschließend die Werte zurück.

Er prüft die gemeldeten Schreibrechte, unterstützte Datentypen und numerische
Grenzen. Unbekannte IDs, nicht unterstützte Typen und nur schreibbare Parameter
werden abgewiesen. Passwort- und Token-Einstellungen, die er anhand ihrer IDs
erkennt, sind ausgeschlossen. Der Wechselrichter setzt die Berechtigungen des
Anlagenbetreibers durch. Installateurzugang ist nicht implementiert.

Schreibzugriffe sind nicht atomar. Nach einem Fehler können einzelne Änderungen
bereits angewendet sein. Vor einem erneuten Versuch die aktuellen Werte lesen.
Das Ergebnis meldet `verification` als `matched`, `mismatch` oder `unavailable`.
Es gibt keinen automatischen Rollback. `PLENTICORE_READ_ONLY=true` sperrt
Schreibzugriffe; Vorschauen funktionieren weiter.

Weitere Hinweise stehen in [SECURITY.md](SECURITY.md).

## Docker

```bash
docker build -t plenticore-mcp .
docker run --rm -i --env-file .env plenticore-mcp
```

Für stdio `-i` ohne `-t` verwenden. Der Container muss den Wechselrichter
erreichen können. Das Image läuft ohne Root-Rechte und installiert die mit
Hashes festgeschriebenen Laufzeitabhängigkeiten aus `requirements.lock`.
Ein vorgebautes Container-Image ist nicht veröffentlicht.

## Entwicklung

```bash
uv sync --frozen
uv run --frozen pytest -q
uv run --frozen ruff check src tests scripts
uv run --frozen ruff format --check src tests scripts
uv run --frozen python scripts/generate_tool_reference.py --check
uv build
uv run --frozen python scripts/check_artifacts.py dist/*.whl dist/*.tar.gz
```

Die Tests verwenden einen lokalen Wechselrichter-Emulator mit Anmeldung sowie
echte MCP-Verbindungen über stdio und HTTP. Ein physisches Gerät ist nicht
erforderlich. Am realen Wechselrichter wurden alle elf Werkzeuge geprüft,
das Änderungswerkzeug als Vorschau. Tatsächliche Schreibzugriffe und Fehler beim
Rücklesen sind bisher ausschließlich gegen den Emulator getestet.

Siehe [CONTRIBUTING.md](CONTRIBUTING.md) und [CHANGELOG.md](CHANGELOG.md).

## Projekt

MIT-Lizenz. Unabhängiges Projekt ohne Verbindung zu KOSTAL Solar Electric.
Fehler bitte mit reproduzierbaren Schritten als
[GitHub Issue](https://github.com/NemoN/plenticore-mcp/issues) melden.
Zugangsdaten und identifizierende Gerätedetails aus Berichten und Logs entfernen.
