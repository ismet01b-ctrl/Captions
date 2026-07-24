# DouchkoVE - Go-Live-Runbook

Reihenfolge zum Scharfstellen. Alles laeuft auf dem Server (netcup) im Projekt-
Ordner neben `docker-compose.yml`. Kontroll-Instrument fuer ALLES hier:
**`https://<domain>/admin` -> Tab Live/System** - die Ampel-Zeile ist die
Startliste. Ziel: alles gruen.

---

## 0. `.env` anlegen
```bash
cp .env.example .env
nano .env          # Werte eintragen (siehe unten)
```
`.env` wird NIE committet (steht in .gitignore).

## 1. [BLOCKER] Admin-Key
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```
-> in `.env` als `DVE_ADMIN=...`. Damit kommst du in `/admin`.

## 2. [BLOCKER] OpenAI-Key
`OPENAI_API_KEY=sk-...` in `.env`. Ohne den laeuft keine Regie.

## 3. [BLOCKER] Owner-Konto (Admin-Panel ist davon UNABHAENGIG)
Setze `DVE_OWNER=` auf deine echte Login-Mail. Nur dieses (verifizierte!) Konto
sieht das Owner-Panel (globale Stil-Referenz) unter Account. Das grosse
Admin-Panel `/admin` haengt dagegen NUR am `DVE_ADMIN`-Key.

## 4. [BLOCKER fuer Verkauf] Stripe LIVE
1. Stripe-Dashboard -> Live-Modus.
2. `STRIPE_SECRET_KEY=sk_live_...` in `.env`.
3. Webhook anlegen: Endpoint `https://<domain>/api/stripe/webhook`,
   Event `checkout.session.completed` (+ `checkout.session.async_payment_succeeded`).
   Das erzeugte Secret -> `STRIPE_WEBHOOK_SECRET=whsec_...`.
4. Nach dem Deploy: im Admin-Panel muss "Stripe: live" + "Webhook: set" gruen sein.
5. EINEN echten Testkauf machen (kleinstes Paket) -> Credits kommen an?

## 5. [BLOCKER fuer Verify/Reset] Mail
Eins von beiden in `.env`:
- **Resend:** `RESEND_API_KEY=...`  (am einfachsten)
- **SMTP:** `SMTP_USER=...`, `SMTP_PASS=...` (Gmail: App-Passwort), `MAIL_FROM=...`

Test nach Deploy: Admin-Panel -> System -> "Send test mail" -> kommt sie an?

## 6. [BLOCKER fuer Ton] Sound-Pack (CC0)
Ohne Pack sind ALLE Videos stumm. Einmalig laden (braucht einen kostenlosen
Freesound-API-Key von https://freesound.org/apiv2/apply):
```bash
python3 sfx_pack.py --key <FREESOUND_KEY> --fetch
```
Das legt `sfx/pack/<slot>.wav` an. Beim naechsten Render sitzt der Ton.
(Im Docker: im laufenden App-Container ausfuehren oder die `sfx/pack/`-Dateien
ins Image/Volume legen.)

## 7. Deploy
```bash
git pull            # holt den aktuellen Branch (autodeploy macht das sonst alle 2 Min)
docker compose up -d --build
```
Danach ~1-2 Min warten, dann `/admin` -> alles gruen?

## 8. Monitoring (empfohlen)
UptimeRobot (kostenlos) auf `https://<domain>/api/health` (HTTP 200 = gesund).

---

## Recht (einmalig, nicht von der Software loesbar)
- OpenAI-DPA/AVV unterschreiben (der Datenschutz-Text nennt den Mechanismus).
- Kontakt-Postfach `Ismet@douchkove.com` live + ueberwacht (steht in Impressum/AGB).
- Kleinunternehmer §19 UStG: bereits im Impressum/AGB hinterlegt.

## Was nur mit echtem Material geht (Qualitaet, kein Code-Blocker)
- Ein echter End-to-End-Kauf (Stripe -> Credits -> Render -> Video).
- Windows-Test mit echtem Video (Maske 'hoch', MOV-Import in Premiere).
- Semantik-Regie + Animationen auf echtem Material sichten.

## Admin-Panel Health-Ampel = Startliste
`/admin` zeigt rot/gruen: OpenAI, Stripe (Modus + Webhook), Mail, Disk, DB,
Backup, Watchdog/Cleanup-Heartbeat. Alles gruen = startklar.
