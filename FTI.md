# FTI — onbemande expo-stand

Drie weken, geen internet, niemand aan de stand. Ook de installatie werkt zonder internet: alle Python-pakketten (`offline\wheels`) en lettertypes zitten in de map. Een bezoeker drukt op een
knop op het stuur, rijdt **één ronde Spa in de Radical**, typt zijn naam op
het toetsenbord en ziet meteen op welke plaats hij eindigt.

## Hoe het werkt

| Stap | Wat er gebeurt |
|---|---|
| Wachten | Scherm 2: klassement + "Druk op START op het stuur" |
| Knop op het stuur | De autopilot schrijft `race.ini`, start Assetto Corsa (hotlap, Radical, Spa, hulpmiddelen aan) |
| Rijden | Scherm 2 toont een lopende klok + voortgang van de ronde |
| Finish | Na de eerste **geldige** ronde: 5 s "Finish!", daarna wordt AC afgesloten |
| Naam | Scherm 2: tijd + voorlopige plaats; de bezoeker typt zijn naam + ENTER (90 s) |
| Resultaat | "Proficiat, Lotte! P14 van 231" + rij oplichtend in het klassement (25 s) |

- **Track limits tellen niet**: event-type `expo` negeert cuts. Alleen de
  minimum rondetijd blijft (tegen afsnijden/glitches).
- **Toetsenbord**: de autopilot onderschept *elke* toets. Alleen letters,
  cijfers, spatie, `-`, `.`, `'`, Backspace en Enter doen iets — en enkel in
  het naamveld. Alt+Tab, Alt+F4, Windows-toets, Esc, Ctrl+Shift+Esc… doen niets.
- **Vastgelopen?** Staat de wagen 45 s stil of duurt een rit langer dan 7 min,
  dan stopt de rit vanzelf. Elk onderdeel herstart zichzelf als het crasht.
- **Geen internet nodig.** Komt er later internet, dan worden de tijden alsnog
  naar sim.hydroteam.be gestuurd.

## Eenmalig installeren (geen internet nodig)

0. Zet de map **hydrosim** op het **bureaublad** van de sim-pc (vanaf de USB,
   of `git clone`). Had de pc al een hydrosim-map? Kopieer daaruit `.env` en de
   map `data` naar de nieuwe map: zo blijven tokens en tijden behouden.
   Dubbelklik dan **INSTALLEREN** en ga verder bij stap 3.
1. (Zonder USB) Open een opdrachtprompt in de hydrosim-map en haal de FTI-versie binnen:
   ```
   git fetch origin
   git checkout fti
   ```
2. Dubbelklik **`windows\setup-fti.bat`**. Dat doet alles in één keer:
   - installeert Python-pakketten (de eerste keer)
   - zoekt Assetto Corsa en de Radical-map (`content\cars\*radical*`); bij
     meerdere vraagt het welke
   - schrijft `autopilot\autopilot.ini` en **toont de ADMIN CODE — schrijf die op!**
   - maakt het event **FTI 2026** aan en activeert het (expo, Spa, Radical,
     track limits genegeerd, min. rondetijd 100 s)
   - downloadt de lettertypes voor offline gebruik
   - vraagt of de stand automatisch moet starten bij aanmelden (ja)

   Opnieuw uitvoeren mag altijd: bestaande instellingen blijven behouden.
3. Startknop kiezen (optioneel): `.venv\Scripts\python -m autopilot --learn`,
   druk op de knop die START moet zijn en zet de getoonde nummers in
   `autopilot\autopilot.ini` onder `[wheel]` (leeg laten = elke knop start).
4. Steam: aanmelden, AC één keer met de hand starten (stuur kalibreren,
   besturing instellen, grafische instellingen), dan **Steam → Go Offline**.
   Zet Steam op "start met Windows". `acs.exe` werkt niet zonder Steam.
5. Test: `windows\start-fti.bat`, druk op de stuurknop, rij een ronde, typ een
   naam. Stoppen: `windows\stop-fti.bat`. Testrit wegdoen via `/admin` → Laps → Discard.
6. Windows automatisch laten aanmelden (`netplwiz` → vinkje uit bij
   "Gebruikers moeten een gebruikersnaam en wachtwoord invoeren").
7. **Als administrator**: `windows\lockdown.ps1` en daarna **herstarten**.
   - schakelt de **Ctrl- en Alt-toetsen uit** (op Windows-niveau, voor de hele
     pc): Ctrl+Alt+Del kan niet meer ingedrukt worden
   - schakelt Taakbeheer, Vergrendelen, Afmelden, Afsluiten en meldingen uit
   - scherm en slaapstand nooit uit
   Alles terugzetten: `windows\unlock.ps1` als administrator + herstarten.
8. Herstart. De stand start vanzelf: server, collector en autopilot draaien
   geminimaliseerd, het expo-scherm opent op scherm 2.

Tip: test eerst alles **zonder** `lockdown.ps1` en met `lock = 0` in
`autopilot.ini`, en zet daarna pas de vergrendeling aan.

Andere naam of wagen voor het event? `.venv\Scripts\python -m flask --app app
create-expo --name "..." --slug ... --car <map> --min-lap 100`.

## Ter plaatse

- Muis **niet** aansluiten (of wegbergen). Enkel stuur + pedalen + toetsenbord.
- Stand komt niet in beeld op scherm 2? Pas `position` in
  `autopilot\autopilot.ini` aan (linkerbovenhoek van scherm 2, bv. `1920,0`;
  links van het hoofdscherm = `-1920,0`).

### Admin aan de stand

- Typ de **admin code** op het toetsenbord (gewoon, op eender welk moment):
  het toetsenbord is 10 minuten vrij. Opnieuw de code typen = meteen weer op slot.
- Stoppen: `windows\stop-fti.bat`. Starten: `windows\start-fti.bat`.
- Naam aanpassen of een tijd weggooien: http://127.0.0.1:8088/admin → *Laps*.
- Na het event: `windows\unlock.ps1` als administrator, snelkoppeling
  "HydroSim expo" uit de Opstarten-map verwijderen.

## Instellingen (`autopilot\autopilot.ini`)

| Sectie | Wat |
|---|---|
| `[ac]` | AC-map, wagen (map onder `content\cars`), skin, circuit, `session = hotlap` (vliegende ronde) of `race` (1 ronde met staande start) |
| `[assists]` | automatisch schakelen, ABS, TC… (standaard alles aan voor beginners) |
| `[conditions]` | weer, temperatuur, tijdstip |
| `[run]` | time-outs in seconden (stilstand, max. rit, naam typen, resultaat tonen) |
| `[wheel]` | welke controller / knop start een rit |
| `[keyboard]` | vergrendeling, admin code, optionele startknop op het toetsenbord (bv. `F9` voor een USB-arcadeknop) |
| `[screen]` | expo-scherm openen + positie op scherm 2 |

## Repetitie zonder AC (eender welke pc)

```bash
python -m autopilot --demo --config autopilot/autopilot.ini
```
Enter = knop op het stuur, naam typen + Enter = naam. Open `/expo` in de browser.
