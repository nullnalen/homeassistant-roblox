# Roblox Parental Controls — Home Assistant Integration

Overvåk barnets Roblox-aktivitet direkte i Home Assistant. Henter skjermtid, spilltoppliste, blokkerte spill og sanntids tilstedeværelse via Roblox sitt interne foreldrekontroll-API.

> **Merk:** Bruker uoffisielle Roblox-endepunkter. Kun for personlig bruk med egne barns data.

---

## Installasjon via HACS

1. Åpne HACS i Home Assistant
2. Gå til **Integrasjoner** → meny øverst til høyre → **Egendefinerte arkiver**
3. Legg til `https://github.com/nullnalen/homeassistant-roblox` som type **Integrasjon**
4. Søk etter "Roblox Parental Controls" og installer
5. Start Home Assistant på nytt

---

## Oppsett

### 1. Hent ROBLOSECURITY-cookie

1. Logg inn på [roblox.com](https://www.roblox.com) i en nettleser med **forelderkontoen**
2. Åpne DevTools (F12) → **Application** → **Cookies** → `https://www.roblox.com`
3. Finn `.ROBLOSECURITY` og kopier hele verdien

> Cookien er et fullstendig innloggingstoken. Del den aldri med andre.

### 2. Legg til integrasjonen

1. Innstillinger → Enheter og tjenester → **Legg til integrasjon** → søk "Roblox"
2. Lim inn ROBLOSECURITY-cookien
3. Velg hvilke barn som skal overvåkes (støtter flere barn)

### 3. Entiteter som opprettes (per barn)

| Entitet | Beskrivelse |
|---------|-------------|
| `sensor.roblox_*_screen_time_today` | Skjermtid i dag (minutter) |
| `sensor.roblox_*_screen_time_this_week` | Skjermtid denne uken (minutter) |
| `sensor.roblox_*_top_games_this_week` | Antall spill spilt denne uken. Attributt `games` inneholder full liste med navn, minutter og blokkert-status |
| `sensor.roblox_*_daily_screen_time_limit` | Daglig grense satt i Roblox (minutter) |
| `sensor.roblox_*_age_restriction_level` | Aldersrestriksjonsnivå (AllAges, NinePlus, ThirteenPlus) |
| `binary_sensor.roblox_*_online` | På når barnet er pålogget Roblox |
| `binary_sensor.roblox_*_in_game` | På når barnet er inne i et spill. Attributt `game` viser spillnavn |
| `binary_sensor.roblox_*_over_daily_limit` | På når skjermtid i dag >= dagsgrensen |
| `binary_sensor.roblox_*_playing_blocked_game` | På når et blokkert spill har fått ny spilletid siden forrige poll |

### 4. Oppdater cookie

Cookien varer typisk noen uker. Når den utløper vil HA varsle deg med et rødt banner på integrasjonen.

For å bytte cookie proaktivt: Innstillinger → Enheter og tjenester → Roblox → **Konfigurer**

---

## Automasjoner (blueprints)

Fire ferdige blueprints som sender push-varsling til HA Companion-appen.

### Importer

Gå til Innstillinger → Automasjoner → **Blueprints** → **Importer blueprint**, og lim inn URL-en til ønsket blueprint:

| Blueprint | URL |
|-----------|-----|
| Varsle når barn starter spill | `https://github.com/nullnalen/homeassistant-roblox/raw/main/blueprints/automation/roblox_game_started.yaml` |
| Varsle når blokkert spill spilles | `https://github.com/nullnalen/homeassistant-roblox/raw/main/blueprints/automation/roblox_blocked_game_played.yaml` |
| Varsle når dagsgrense er nådd | `https://github.com/nullnalen/homeassistant-roblox/raw/main/blueprints/automation/roblox_daily_limit_reached.yaml` |
| Daglig oppsummering kl. 20 | `https://github.com/nullnalen/homeassistant-roblox/raw/main/blueprints/automation/roblox_daily_summary.yaml` |

### Sett opp automasjon fra blueprint

1. Etter import: klikk **Opprett automasjon** på blueprinten
2. Fyll inn feltene:
   - **Sensor** — velg riktig sensor for barnet (f.eks. `binary_sensor.roblox_ilstjerna_in_game`)
   - **Telefon å varsle** — velg din telefon fra listen (krever HA Companion-appen installert)
   - **Barnets navn** — skriv inn navnet som vises i varslingen
3. Lagre

### Eksempel på varsling

```
Roblox
ilstjerna startet Brookhaven RP
```

```
Roblox: Daglig oppsummering
I dag: 1t 45min
Denne uken: 6t 5min

Topp 3 spill:
1. Dubai RP (95min) BLOKKERT
2. LifeTogether (50min) BLOKKERT
3. Adopt Me! (32min)
```

---

## Innstillinger

Under Roblox → Konfigurer kan du justere:

| Innstilling | Standard | Beskrivelse |
|-------------|----------|-------------|
| Polleintervall skjermtid | 30 min | Hvor ofte skjermtid og spillliste hentes |
| Polleintervall tilstedeværelse | 2 min | Hvor ofte online/i-spill sjekkes |
| Tilstedeværelse aktivert | Ja | Skru av for å spare API-kall |

---

## Sikkerhet

- Cookien lagres kryptert i Home Assistant sin `.storage`
- Cookien vises aldri i logger eller diagnostics
- Bytt Roblox-passord etter du er ferdig med oppsett (cookien roterer uansett)
