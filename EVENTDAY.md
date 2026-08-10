# Draaiboek eventdag (NL)

Voor wie de simulator-stand bemant. Techniek hoeft je niet te boeien: alles
staat al geïnstalleerd op de sim-pc.

## Opstarten (5 minuten)

1. Zet de sim-pc en de twee schermen aan, start Assetto Corsa **niet** eerst —
   volgorde maakt eigenlijk niet uit, maar zo zie je meteen of alles draait.
2. Dubbelklik **`windows\start.bat`** (snelkoppeling op het bureaublad).
   Er openen twee zwarte consolevensters (server + collector) en een
   fullscreen leaderboard.
3. Sleep het leaderboard-venster naar het tweede scherm (alleen de eerste
   keer — Windows onthoudt het).
4. Start Assetto Corsa, kies de auto en **Spa**, en ga rijden in
   *Practice* of *Hotlap*.

Klaar. Elke gereden ronde verschijnt binnen een seconde op het bord, en er
komt een **popup: "Who drove this lap?"** — naam intikken, **Put it on the
board**, en de bezoeker staat in het klassement. Uitlap of testronde van het
team? **Discard lap.**

Het bord staat ook live op **https://sim.hydroteam.be** — de QR-code op het
kioskscherm wijst ernaar, zo kunnen bezoekers thuis hun tijd terugvinden.

## Namen invoeren vanaf een tweede laptop

De popup hoeft niet op de sim-pc zelf bediend te worden. Ga op eender welke
laptop (eigen 4G mag, hoeft niet het venue-netwerk te zijn) naar
**https://sim.hydroteam.be/kiosk** en log in met het adminwachtwoord van de
*cloud*-app. Je krijgt hetzelfde scherm mét popup: rondes verschijnen er
binnen enkele seconden, en een naam die je daar intikt staat binnen enkele
seconden óók op het grote scherm naast de sim. Beide schermen mogen tegelijk
openstaan — wie het laatst antwoordt, wint, en het andere scherm springt
vanzelf mee.

Valt het internet weg, dan werkt dit uiteraard even niet (de sim-pc zelf
draait gewoon door). Er is een fallback zonder internet: surf op een laptop
op hetzelfde netwerk als de sim-pc naar `http://<ip-van-de-sim-pc>:8088/kiosk`
en log in met het adminwachtwoord van de *sim-pc* (`ADMIN_PASSWORD` in
`.env`; het IP staat in het install-overzicht of via `ipconfig`). Verbindt
dat niet, draai `windows\install.ps1` eenmalig als administrator voor de
firewallregel.

## Goed om te weten

- **Afgesneden bochten tellen niet**: een ronde met een cut wordt automatisch
  ongeldig en krijgt geen popup. Niks aan doen.
- **Naam fout getikt of grap-naam?** Open `http://127.0.0.1:8088/admin` op de
  sim-pc (wachtwoord: zie `ADMIN_PASSWORD` in het bestand `.env` in de
  hydrosim-map) → *Laps* → naam aanpassen of *Discard*.
- **Internet weggevallen?** Geen probleem — alles blijft lokaal werken en de
  rondes worden automatisch doorgestuurd zodra er weer verbinding is.
- **Popup gemist / meerdere rondes achterstand?** De popup toont de nieuwste
  ronde eerst en meldt hoeveel oudere rondes nog wachten; ze komen vanzelf
  één voor één.
- **Teamlid rijdt een demonstratie?** Zet in het kioskscherm rechtsonder
  *Driver in the seat* op hun naam — dan verschijnt er geen popup en worden
  alle rondes automatisch aan hen toegekend. Daarna weer op *Clear*.

## Nieuw event aanmaken (bv. volgend jaar, andere track)

1. `http://127.0.0.1:8088/admin` → **+ New event**.
2. Naam (staat groot op het scherm), slug (de URL), kind **event**,
   *Track filter* bv. `spa` (of leeg voor eender welke track), minimale
   rondetijd (tegen shortcuts/glitches), toegestane cuts (meestal 0).
3. **Make this the active event** aanvinken → Save. Het oude klassement
   blijft bereikbaar op `/e/<oude-slug>`.
4. Meer hoeft niet: het nieuwe event verschijnt vanzelf op sim.hydroteam.be
   bij de eerste gereden ronde.

Voor teamtiming in de werkplaats: zelfde stappen, maar kind **inhouse** — dan
toont het bord ook auto, banden en rijhulpen, en kan je per auto filteren.

## Vooraf testen zonder Assetto Corsa

`windows\start-demo.bat` — verzint elke ~25 s een ronde. Popup, bord en de
livekoppeling met sim.hydroteam.be gedragen zich exact zoals op de eventdag.

## Afsluiten

Sluit de twee consolevensters (of herstart de pc). Het kioskscherm sluit met
Alt+F4. Alle rondes staan veilig in de database én op sim.hydroteam.be;
exporteren kan altijd nog via *Admin → CSV*.

## Als het misgaat

| Probleem | Oplossing |
|---|---|
| Bord blijft leeg terwijl er gereden wordt | Kijk in het venster "HydroSim collector": staat daar `live: … session`? Zo niet: staat AC in replay/pauze? Track-filter juist (bv. `spa`)? |
| "server unreachable — lap queued" in de collector | Servervenster gesloten? Start `start.bat` opnieuw; de wachtrij wordt vanzelf verwerkt. |
| sim.hydroteam.be loopt achter | Internet van de venue weggevallen — lokaal werkt alles door, sync haalt vanzelf in. |
| Popup verschijnt niet | Alleen géldige rondes krijgen een popup (geen cuts, boven de minimumtijd). Check *Admin → Laps* of de ronde als `invalid` binnenkwam. |
| Alles hangt | Beide consolevensters sluiten en `start.bat` opnieuw. Er gaat niets verloren. |
