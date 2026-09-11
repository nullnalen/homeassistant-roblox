# Home Assistant-integrasjon: Roblox foreldreovervåking

Byggeplan for Claude Code. Målet er en custom integration (`custom_components/roblox_parental/`) som henter skjermtid, spill-toppliste, blokkerte spill og (om mulig) sanntids «spiller nå»-status for et barn, via Roblox' interne foreldrekontroll-API.

---

## 0. Viktige forbehold (les først)

- **Uoffisielt API.** Alle endepunkter er interne app-endepunkter, ikke offentlig dokumentert. Ingen OAuth for foreldre-API-et.
- **Auth = `.ROBLOSECURITY`-cookie.** Passkey/passord/2FA skjer i nettleseren når du logger inn manuelt. Addon-en gjenbruker den innloggede sesjonen via cookien. Passkey er altså irrelevant for selve integrasjonen.
- **Cookien roterer.** Varer typisk uker, dør ved ny innlogging/passordbytte/rotasjon. Integrasjonen MÅ håndtere dette med et reauth-flow, ikke feile stille.
- **Poll forsiktig.** Sjeldne kall reduserer risiko for flagging. Presence maks hvert 1–2 min; skjermtid/toppliste hvert 30–60 min.
- **ToS.** Å polle egne barns data er lav risiko, men bryter teknisk Roblox' vilkår. Bygg konservativt.

---

## 1. Bekreftede endepunkter (fra trafikkfangst)

Alle på `https://apis.roblox.com` med mindre annet er nevnt. Auth: cookie `.ROBLOSECURITY=<verdi>`. POST-kall krever `x-csrf-token` (hentes ved å gjøre et kall uten token og lese `x-csrf-token`-responseheaderen på 403, deretter retry).

| Formål | Metode | URL | Params / body |
|---|---|---|---|
| Valider cookie / hvem er jeg | GET | `users.roblox.com/v1/users/authenticated` | – |
| Liste barn + rettigheter | GET | `/parental-controls-api/v1/parental-controls/children-info` | – |
| Ukentlig skjermtid (7 dager, inkl. dag 0 = i dag) | GET | `/parental-controls-api/v1/parental-controls/get-weekly-screentime` | `?userId=<childId>` |
| Toppliste spill per uke (universeId + min) | GET | `/parental-controls-api/v1/parental-controls/get-top-weekly-screentime-by-universe` | `?userId=<childId>` |
| Blokkerte spill | POST | `/experience-blocking-api/v1/get-blocked-experiences` | `{"targetUserId":<childId>,"limit":50,"offset":0}` |
| Barn-innstillinger (chat, grense, aldersnivå) | GET | `/parental-controls-api/v1/parental-controls/child-settings` | `?childUserId=<childId>` |
| Pengebruk-innstillinger | GET | `billing.roblox.com/v1/parental-controls/get-settings` | – |
| Aldersanbefaling per spill | POST | `/experience-guidelines-service/v1beta1/multi-age-recommendation` | `{"universeIds":[...]}` |
| **Spillnavn fra universeId** | GET | `games.roblox.com/v1/games` | `?universeIds=id1,id2,...` (svar er gzip) |
| **Sanntid «spiller nå»** (må testes m/ vennskap) | POST | `presence.roblox.com/v1/presence/users` | `{"userIds":[<childId>]}` |

**Bekreftede ID-er for dette oppsettet** (legges inn via config flow, ikke hardkodes):
- childUserId: `10394267387` (brukernavn `Hest_walter1`)
- parentUserId: `10442971407`

**Merk om navneoppslag:** `games.roblox.com/v1/games` returnerer gzip. `aiohttp` dekomprimerer automatisk. Cache navn per universeId; slå bare opp nye ID-er.

**Merk om presence:** `jdeath/Roblox-Homeassistant` (se seksjon 9) sporer presence via userId **uten** at forelder nødvendigvis er venn — så det er mulig spillnavnet kommer gjennom uansett. Test uten vennskap først; legg bare til vennskap hvis navnet skjules. Viktig detalj derfra: online/offline-status oppdateres selv med **utløpt** cookie, mens *spillnavn* krever gyldig cookie. Så presence-status er mer robust enn presence-spillnavn.

---

## 2. Arkitektur

Standard HA custom integration med config flow + DataUpdateCoordinator.

```
custom_components/roblox_parental/
├── __init__.py            # setup entry, opprett coordinator(er), forward til plattformer
├── manifest.json          # domain, deps (ingen ekstern pip om mulig), iot_class=cloud_polling
├── const.py               # DOMAIN, endepunkt-URLer, defaults, poll-intervaller
├── api.py                 # RobloxParentalClient: alle kall, csrf-håndtering, gzip, feil→exceptions
├── coordinator.py         # 2 coordinatorer: FastCoordinator (presence), SlowCoordinator (skjermtid/spill)
├── config_flow.py         # cookie-input, valider, velg barn, reauth-steg
├── sensor.py              # sensorer (se fase 4)
├── binary_sensor.py       # er_online / spiller_nå / over_dagsgrense / spiller_blokkert
├── strings.json + translations/en.json + translations/nb.json
└── diagnostics.py         # (valgfritt) redaktert dump for feilsøking
```

**To coordinatorer** fordi pollingtaktene er ulike:
- `SlowCoordinator` (default 30 min): skjermtid, toppliste, blokkerte, innstillinger, navneoppslag.
- `FastCoordinator` (default 2 min): presence. Kan slås av i options hvis presence ikke gir spillnavn.

---

## 3. api.py — nøkkeldetaljer

- `aiohttp.ClientSession` med cookie `.ROBLOSECURITY` satt på `apis.roblox.com`, `games.roblox.com`, `presence.roblox.com`, `billing.roblox.com`, `users.roblox.com`.
- **CSRF:** hjelpemetode `_post(url, json)` som: prøver POST → hvis 403 med `x-csrf-token`-header, lagre token og retry én gang. Cache token på klienten.
- **Feilhåndtering:**
  - 401/403 uten csrf-årsak → `RobloxAuthError` → coordinator kaster `ConfigEntryAuthFailed` → HA starter reauth-flow.
  - 429 → `RobloxRateLimitError` → coordinator backoff (dobbel intervall midlertidig).
  - Nettverk/5xx → `UpdateFailed`.
- **User-Agent:** sett en fast, app-lignende UA (fangsten viste `Mozilla/5.0 (iPhone …)`). Ikke nødvendig å etterligne eksakt, men sett noe stabilt.
- **Navne-cache:** dict `{universeId: name}` i klienten, persistert i config entry `data`/`options` eller HA `Store` så den overlever restart.

Metoder:
```
authenticate() -> dict            # /users/authenticated, brukes til valider + reauth
get_children() -> list
get_weekly_screentime(child_id) -> list[{daysAgo, minutesPlayed}]
get_top_universes(child_id) -> list[{universeId, weeklyMinutes}]
get_blocked(child_id) -> set[int]
get_child_settings(child_id) -> dict   # daglig grense, chat, aldersnivå
resolve_names(universe_ids) -> dict[int,str]   # bruker cache + games.roblox.com
get_presence(child_id) -> dict         # userPresenceType, universeId, lastLocation
```

---

## 4. Sensorer / entiteter

Grupper alt under én device per barn (`identifiers={(DOMAIN, child_id)}`, name = displayName).

**sensor.py (SlowCoordinator):**
- `sensor.roblox_<navn>_skjermtid_i_dag` — minutter dag 0. `device_class` ingen, `unit=min`, `state_class=total_increasing` (nullstilles daglig — bruk `total`).
- `sensor.roblox_<navn>_skjermtid_uke` — sum 7 dager, `unit=min`.
- `sensor.roblox_<navn>_topp_spill` — state = mestspilte spillnavn; attributter = full liste `[{navn, minutter, blokkert:bool}]`.
- `sensor.roblox_<navn>_antall_spill_uke` — antall unike spill.
- `sensor.roblox_<navn>_dagsgrense` — grensen i minutter (fra child-settings).
- `sensor.roblox_<navn>_aldersnivå` — `contentAgeRestriction` (AllAges/NinePlus/…).

**binary_sensor.py:**
- `binary_sensor.roblox_<navn>_online` (FastCoordinator, presence) — på hvis online/ingame.
- `binary_sensor.roblox_<navn>_spiller_nå` (FastCoordinator) — på hvis userPresenceType=2 (InGame). Attributt: nåværende spillnavn hvis synlig.
- `binary_sensor.roblox_<navn>_over_dagsgrense` (Slow) — skjermtid_i_dag ≥ dagsgrense.
- `binary_sensor.roblox_<navn>_spiller_blokkert` (Slow) — på hvis et blokkert universe har fått økt ukesminutter siden forrige poll (fanger at blokkering ikke virker).

---

## 5. Byggefaser (rekkefølge for Claude Code)

**Fase 1 — Skjelett + api.py + cookie-auth.** Få `authenticate()` og `get_children()` til å funke mot ekte cookie. Verifiser i en throwaway-scriptkjøring før HA-integrasjon.

**Fase 2 — SlowCoordinator + kjernesensorer.** Skjermtid (i dag/uke), toppliste med navneoppslag (gzip + cache), blokkerte spill. Dette gir umiddelbar verdi og krever ikke vennskap.

**Fase 3 — config_flow + reauth.** Cookie-input, valider via authenticate, auto-oppdag barn (velg hvis flere), lagre child_id. Reauth-steg som trigges av `ConfigEntryAuthFailed`.

**Fase 4 — binary_sensors + child-settings.** Dagsgrense, aldersnivå, over-grense, spiller-blokkert-deteksjon.

**Fase 5 — Presence (sanntid).** FastCoordinator. **Test først** om presence returnerer spillnavn for forelderkontoen:
   - Test A: uten vennskap — sannsynligvis bare Online/InGame uten navn.
   - Test B: forelder + barn som venner (legges til via foreldrekontroll, `canParentManageChildsFriends=true`) — test om `lastLocation`/universeId kommer gjennom.
   - Bygg presence-sensor uansett; vis navn hvis tilgjengelig, ellers bare status. Gjør FastCoordinator valgfri i options.

**Fase 6 — Polish.** Options flow (poll-intervaller, skru presence av/på), translations (nb/en), diagnostics med redaktert cookie, HACS-manifest (`hacs.json`) så du kan installere via HACS.

---

## 6. Automasjoner å bygge etterpå (i HA, ikke i integrasjonen)

- Push når `spiller_nå` går fra av→på: «ilstjerna åpnet \<spill\>».
- Push når `spiller_blokkert` = på: «Blokkert spill fikk ny spilletid — sjekk blokkering».
- Push når `over_dagsgrense` = på.
- Daglig kl. 20: send dagens skjermtid + topp 3 spill.

---

## 7. Sikkerhet / hygiene

- Cookien er et fullt innloggingstoken. Lagres kun i HA config entry (kryptert i `.storage`). Aldri logg den. Diagnostics må redigere den bort.
- Slett/roter de tre `.chlz`-fangstfilene — de inneholder cookien i klartekst. Bytt Roblox-passord når integrasjonen er ferdig og du har hentet en frisk cookie (det roterer likevel).
- Ikke publiser repoet med ekte child/parent-ID-er eller cookie.

---

## 8. Åpne spørsmål å avklare i morgen

1. Gir presence spillnavn etter at forelder+barn er venner? (avgjør om «spiller nå med spillnavn» er mulig — ellers er daglig skjermtid ferskeste kilde)
2. Hvor ofte oppdateres `daysAgo:0`-skjermtid egentlig serverside? (bestemmer nytten av <30 min polling)
3. Ønsker du flere barn støttet nå, eller bare denne ene kontoen? (config flow bør takle flere uansett)

---

## 9. Referanse: jdeath/Roblox-Homeassistant

Eksisterende HACS-integrasjon som bekrefter tilnærmingen. **Lån presence-logikken derfra, behold vår arkitektur.**

Repo: `https://github.com/jdeath/Roblox-Homeassistant`

**Hva den er:** En gjenbrukt versjon av HAs innebygde `steam_online`-integrasjon, tilpasset Roblox. Sporer **presence** (online/offline + hvilket spill spilles) for vilkårlige userIds.

**Hva vi låner:**
- Presence-implementasjonen — nøyaktig kallet for «spiller nå» + spillnavn. Dette er biten vi ikke hadde bekreftet fra fangstene.
- Cookie-som-`api_key`-mønsteret (samme `.ROBLOSECURITY`).
- 2-min polletakt (justerbar via `BASE_INTERVAL`/`SCAN_INTERVAL`).

**Bekreftet fra repoet:**
- Sporer via userId — ikke åpenbart avhengig av vennskap. Test uten venn først.
- Utløpt cookie → mister spillnavn, men online/offline fortsetter. Bekrefter at status er mer robust enn spillnavn.
- Forfatterens egen advarsel: bruk helst en **dummy/sekundær konto** for cookien, siden den lar noen logge inn som deg og stjele Robux/items.

**Hva den IKKE gjør (og hvorfor vi fortsatt bygger vår egen):**
- Bruker ikke foreldrekontroll-API-et i det hele tatt.
- Ingen skjermtid (dag/uke), ingen ukes-toppliste med minutter, ingen blokkerte spill, ingen dagsgrense/aldersnivå/pengebruk.
- Gammel YAML `platform:`-stil (ikke config flow / coordinator / device). Mindre pen, mindre HACS-moderne.

**Konklusjon:** vår integrasjon = jdeath sin presence-del + foreldre-API-sensorene (seksjon 1) + moderne arkitektur (seksjon 2). Se på `custom_components/roblox/sensor.py` i repoet for presence-kallet før fase 5.

**Vurder dummy-konto:** Forfatterens råd om egen konto for cookien er verdt å vurdere også for oss — men merk at foreldre-API-kallene (skjermtid osv.) krever at cookien tilhører **forelderkontoen** som er lenket til barnet. Presence krever ikke det. Mulig kompromiss: hvis du vil isolere risiko, kan presence kjøre på en dummy-cookie og foreldre-data på forelder-cookien. To cookies i config, men mindre eksponering. Overkomplisert for v1 — start med kun forelder-cookie, vurder splitting senere.

---

## 10. Distribusjon — hva du kan og ikke kan tilby andre

Tre nivåer, fra grønt til rødt:

### A. Egen bruk — greit
Én forelder, egne barns data, egen lenkede forelderkonto. Dette er dine data du allerede har lovlig tilgang til. Lav risiko. Bygg og bruk fritt.

### B. Dele koden åpent (HACS/GitHub) — sannsynligvis greit, med forbehold
Du publiserer *verktøyet*, ikke *tilgangen* eller *dataene*. Hver forelker legger selv inn sin egen cookie og er ansvarlig for egen bruk. Dette er samme modell som jdeath-repoet og mange uoffisielle HA-integrasjoner.
- **Krav i README:** tydelig «uoffisielt, ikke tilknyttet Roblox, på egen risiko». Forklar cookie-risikoen. Anbefal at brukeren forstår hva `.ROBLOSECURITY` er.
- **Du distribuerer aldri en cookie eller data.** Hver installasjon står på egne ben.
- **Fortsatt teknisk et ToS-brudd** for brukerne (uoffisielle endepunkter), men ansvaret ligger hos den som installerer og logger inn — ikke hos deg som kodedeler. Vanlig praksis, men ikke null risiko.

### C. Ekte tjeneste til andre foreldre (hosted, du holder tilgang/data) — ikke gjør dette med cookie-modellen
Dette er der Roblox' vilkår stopper deg hardt:
- Krever **godkjent tredjeparts-API-tilgang** via søknad. Roblox vurderer forespørsler og setter rate limits / datatilgang.
- Du kan **ikke selge data** hentet via API-ene, **ikke bruke brukerdata til å trene AI/språkmodeller**, og må **slette all data** hvis du mister API-tilgang.
- Å be andre foreldre håndtere sin egen sesjonscookie i din software er nettopp det Roblox advarer mot (kontodeling/kontokompromittering). Å hoste andres cookies gjør deg til forvalter av deres fulle innloggingstokens — juridisk og sikkerhetsmessig en byrde du ikke vil ha.
- Roblox kan IP-banne ved automatiseringsbrudd.

**Hvis målet noen gang blir C:** søk Roblox om offisiell tredjeparts-API-tilgang og bygg kun på det de godkjenner. Da håndterer ingen rå cookies, og du er innenfor vilkårene. Større prosjekt, men eneste bærekraftige vei til en delt tjeneste.

### Anbefaling
Bygg for **A** nå. Hvis andre foreldre spør, gå til **B** (del repoet, la dem installere selv). Ikke bygg **C** uten offisiell API-godkjenning.

---

## 11. Fase 7 (senere): auto-deteksjon + én-trykks blokkering

Mål: etterligne «hviteliste» (blokker alt, godkjenn utvalgte) oppå Roblox' svarteliste-mekanisme. **Bygg deteksjon + varsling automatisk, men hold selve blokkeringen til ett trykk fra forelder — ikke helautomatisk.**

### Forutsetning: fang skrive-endepunktet først
Fangstene har bare *lese*-kallet (`get-blocked-experiences`). Skrive-kallet (blokker/avblokker) er ikke fanget ennå.
- **Å gjøre:** blokker og avblokker ett spill manuelt i appen mens Charles kjører, last opp fangsten.
- **Forventet:** POST til noe som `experience-blocking-api/v1/block-experience` / `unblock-experience` med `targetUserId` + `universeId` + `x-csrf-token`. Bekreft eksakt path + body før bygging.

### Flyt
1. FastCoordinator (presence, 1–2 min) ser at barnet startet universe X.
2. HA sjekker X mot en godkjent-liste (f.eks. `input_select`, `input_text`, eller en liste i integrasjonens options).
3. Er X ikke godkjent → send push med spillnavn + to actionable-knapper: «Godkjenn» / «Blokker».
4. «Godkjenn» → legg X til godkjent-liste (avblokker om nødvendig).
5. «Blokker» → kall block-endepunktet for X.

Gir ekte hviteliste-oppførsel bygget på svarteliste-API-et.

### Ærlige begrensninger (skriv inn i README)
- **Ikke sanntid nok til å hindre start.** Presence poller hvert par minutter → barnet spiller noen minutter før blokkering slår inn. Blokkering stopper trolig ikke en pågående økt, bare *neste* åpning. Dette er «oppdag og steng etterpå», ikke «forhindre».
- **Skjørere enn lesing.** Nå skrives det til barnets konto. Hyppige blokk-kall er mer synlig enn passiv lesing → høyere risiko for at Roblox flagger sesjonen. Cookie-utløp midt i en operasjon kan gi rar tilstand.
- **Roblox gjør dette delvis offisielt.** Roblox Kids (under 9) gir allerede kun kuratert pool + mulighet for å blokkere enkeltspill. Content maturity «Minimal» + manuell blokkering dekker mye av samme behov uten automatiseringsrisiko.

### Anbefaling
- Bygg **deteksjon + varsling** (lav risiko, forelder beholder kontroll).
- Gjør **blokkering til ett trykk**, ikke helautomatisk — unngår at falske positiver eller uskyldige spill stenges automatisk, og skriver til kontoen kun ved bevisst valg.
- Vurder om Roblox' native content maturity + manuell blokkering egentlig er nok før du bygger denne fasen i det hele tatt.

---

## 12. Prioritering: Roblox nå, Fortnite som betinget neste steg

Bevisst avgrensning. Ikke bygg en generell multi-API-barnevakt — det blir mange skjøre uoffisielle integrasjoner som knekker ved hver app-oppdatering. Fokuser på den faktiske, aktuelle risikoen.

### Roblox — bygg nå
Den reelle, pågående risikoen: åpen plattform for de yngste, barnet spiller 6+ t/uke, de mestspilte var spill som var blokkert. Konkret, målbart, og API-et er allerede kartlagt. **Dette haster og er ferdig utredet.**

### Fortnite — sjekk relevans først, bygg eventuelt senere
Fortnite har gått fra ett spill til en **plattform**: Battle Royale + Lego Fortnite + Rocket Racing + Festival, og et hav av brukerskapte UEFN-øyer med varierende alderstilpasning og chat med fremmede. Samme dynamikk som gjør Roblox utrygt.
- **Men:** høyere inngangsterskel for de yngste. Epic bruker aldersband; Cabined Accounts er ganske låst som standard for barn under en viss alder.
- **Å gjøre:** avklar om barnet faktisk spiller det. Hvis nei → sett opp Epic-foreldrekontroll (PIN, aldersgrense på øyer, chat av) forebyggende, men ikke bygg overvåking. Hvis hun begynner å spille mye → Charles-fangst av Fortnite-appen, sjekk om Epic har tilsvarende foreldre-data-endepunkter. Eget prosjekt, ikke del av kjernen.

### Alt annet — la ligge
- **Spotify:** offisiell HA-integrasjon finnes allerede (HACS/core). Skru på ved behov, ingen bygging.
- **iOS-enheten (alle apper, spill, NRK, tidsgrenser):** dekkes av Apple Screen Time / Family Sharing — offisielt, på OS-nivå. Eksponeres ikke til HA (personvern by design), men kraftigere enn egenbygd for bred barnevakt.
- **NRK Super / enkelt-spill på iOS:** enten trygt nok, dekket av Screen Time, eller ikke verdt reverse-engineering. Ta NRK som separat miniprosjekt kun hvis det viser seg nødvendig (fangst først).

### Kjerneprinsipp
Roblox er der barnet er, der kontrollen er svakest, og der du har data. Bygg for det. Bred barnevakt = lene seg på Apple Family Sharing (enhetsnivå) + selektive ekte API-er (Spotify), ikke fem uoffisielle nettverks-integrasjoner.