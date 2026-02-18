# 🏗️ EAM Knowledge Cockpit — Deployment-Anleitung

**Für:** Severin's Hetzner Server (46.225.87.74, 4GB RAM)
**Dauer:** ~30 Minuten
**Voraussetzung:** SSH-Zugang zum Server

---

## Übersicht: Was passiert

```
1. Supabase: Datenbank-Tabellen erstellen (im Browser)
2. Server: Code + PDFs hochladen
3. Server: Docker starten
4. Server: Daten einspeisen (Papers + Konzepte + Triggers)
5. Testen: API-Endpoints aufrufen
```

---

## Schritt 1: Supabase — Tabellen erstellen

### 1a. Supabase öffnen
- Gehe zu https://supabase.com/dashboard
- Öffne dein Projekt (das vom gasserwerk-rag)
- Klicke links auf **SQL Editor**

### 1b. Schema ausführen
- Kopiere den GESAMTEN Inhalt von `sql/001_eam_schema.sql`
- Füge ihn im SQL Editor ein
- Klicke **Run** (grüner Button)
- Du solltest sehen: "Success. No rows returned"

### 1c. Prüfen
- Klicke links auf **Table Editor**
- Du solltest neue Tabellen sehen:
  - `eam_papers`
  - `eam_paper_chunks`
  - `eam_domains` (sollte 6 Einträge haben)
  - `eam_concepts`
  - `eam_decision_triggers`
  - `eam_concept_papers`
  - `eam_concept_checkpoints`

### 1d. API-Keys notieren
- Gehe zu **Project Settings** → **API**
- Notiere dir:
  - **Project URL** (z.B. `https://xxxxx.supabase.co`)
  - **service_role key** (der lange Key unter "secret")

---

## Schritt 2: Server — Code hochladen

### 2a. SSH-Verbindung öffnen
Öffne ein Terminal auf deinem Computer:
```bash
ssh root@46.225.87.74
```
Gib dein Passwort ein.

### 2b. Docker prüfen
```bash
docker --version
```
Falls "command not found":
```bash
curl -fsSL https://get.docker.com | sh
```

### 2c. Docker Compose prüfen
```bash
docker compose version
```
Falls "command not found":
```bash
apt update && apt install -y docker-compose-plugin
```

### 2d. Verzeichnis erstellen
```bash
mkdir -p /opt/eam-cockpit/papers
cd /opt/eam-cockpit
```

### 2e. Code hochladen
**Option A: Direkt von deinem Computer (neues Terminal, NICHT auf dem Server):**
```bash
scp -r /pfad/zu/eam-cockpit/* root@46.225.87.74:/opt/eam-cockpit/
```

**Option B: Die ZIP-Datei nutzen (wenn du sie von Claude heruntergeladen hast):**
```bash
# Auf deinem Computer:
scp eam-cockpit.zip root@46.225.87.74:/opt/

# Dann auf dem Server:
cd /opt
unzip eam-cockpit.zip
mv eam-cockpit/* /opt/eam-cockpit/
```

### 2f. PDFs hochladen
Die 18 heruntergeladenen PDFs müssen in `/opt/eam-cockpit/papers/`:
```bash
# Von deinem Computer (neues Terminal):
scp /pfad/zu/EAM-Papers-2024-2025/*.pdf root@46.225.87.74:/opt/eam-cockpit/papers/
```

### 2g. Prüfen ob alles da ist
```bash
cd /opt/eam-cockpit
ls -la
```
Du solltest sehen:
```
api/
config/
data/
scripts/
sql/
papers/
Dockerfile
docker-compose.yml
requirements.txt
.env.example
```

Und die PDFs:
```bash
ls papers/
```
Sollte 18 PDF-Dateien zeigen.

---

## Schritt 3: Environment-Datei erstellen

### 3a. .env erstellen
```bash
cd /opt/eam-cockpit
cp .env.example .env
nano .env
```

### 3b. Keys einfügen
Ersetze die Platzhalter mit deinen echten Keys:
```
SUPABASE_URL=https://DEIN-PROJEKT.supabase.co
SUPABASE_KEY=eyJ...DEIN_SERVICE_ROLE_KEY...
OPENAI_API_KEY=sk-...DEIN_OPENAI_KEY...
ANTHROPIC_API_KEY=sk-ant-...DEIN_ANTHROPIC_KEY...
PAPERS_DIR=/opt/eam-cockpit/papers
```

### 3c. Speichern
- `Ctrl+O` → `Enter` (speichern)
- `Ctrl+X` (nano beenden)

---

## Schritt 4: Docker starten

### 4a. Bauen und starten
```bash
cd /opt/eam-cockpit
docker compose up -d --build
```

Das dauert 1-2 Minuten (Python-Pakete installieren).

### 4b. Prüfen ob es läuft
```bash
docker compose ps
```
Sollte zeigen: `eam-cockpit   ...   Up   ...   0.0.0.0:8100->8100/tcp`

### 4c. Health Check
```bash
curl http://localhost:8100/health
```
Sollte zeigen: `{"status":"ok","service":"eam-knowledge-cockpit"}`

Falls Fehler:
```bash
docker compose logs
```

---

## Schritt 5: Daten einspeisen

### 5a. Seed-Daten (Konzepte, Triggers, Paper-Metadaten)
```bash
docker compose exec eam-cockpit python scripts/ingest.py --seed-only
```

Das dauert 1-2 Minuten (erstellt ~70 Embeddings). Du siehst:
```
📄 Seeding Papers...
  ✅ [A] paper_35_fuentes: Enterprise Architecture and IT Governance...
  ...
🧠 Seeding Concepts...
  ✅ concept_togaf_adm: TOGAF ADM
  ...
🎯 Seeding Decision Triggers...
  🔴 dt_dashboard_metrics: Welche Metriken zeige ich im Dashboard?...
  ...
```

### 5b. PDFs verarbeiten (Text extrahieren + Embeddings)
```bash
docker compose exec eam-cockpit python scripts/ingest.py --papers-only
```

Das dauert 5-10 Minuten (18 PDFs lesen, chunken, embedden). Du siehst:
```
📚 Verarbeite PDFs aus /opt/eam-cockpit/papers...
  📖 01_Wao_ArchiMate_Value_CBI2024.pdf → paper_01_wao
     Extrahiere Text...
     12543 Zeichen extrahiert
     18 Chunks erstellt
     ✅ 18 Chunks + Embeddings gespeichert
  ...
```

### 5c. Statistiken prüfen
```bash
docker compose exec eam-cockpit python scripts/ingest.py --stats
```

Erwartetes Ergebnis:
```
📊 EAM Knowledge Cockpit — Statistiken
==================================================
  Papers................................. ~19
  Paper Chunks.......................... ~200-400
  Konzepte.............................. 30
  Decision Triggers..................... 18
  Concept↔Paper Links.................. ~30-50
```

---

## Schritt 6: Testen

### 6a. Lern-Modus
```bash
curl -X POST http://localhost:8100/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "Was ist ArchiMate und warum brauche ich das?", "mode": "learn"}'
```

### 6b. Entscheidungs-Modus
```bash
curl -X POST http://localhost:8100/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "Welche Metriken soll ich im Dashboard zeigen?", "mode": "decide", "product": "klar-seite"}'
```

### 6c. Explore-Modus
```bash
curl -X POST http://localhost:8100/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "Was sagt die Forschung über RAG und Enterprise Architecture?", "mode": "explore"}'
```

### 6d. Knowledge Graph navigieren
```bash
# Alle Domänen
curl http://localhost:8100/domains

# Eine Domäne mit allen Inhalten
curl http://localhost:8100/domains/domain_b_ai_ea

# Ein Konzept mit verknüpften Papers + Triggers
curl http://localhost:8100/concepts/concept_rag_ea

# Alle Decision Triggers für klar-seite
curl http://localhost:8100/triggers?product=klar-seite

# Alle S-Tier Papers
curl http://localhost:8100/papers?tier=S
```

---

## Schritt 7 (Optional): nginx Reverse Proxy

Falls du das Cockpit über eine Subdomain erreichbar machen willst:

### 7a. nginx-Config erweitern
```bash
nano /etc/nginx/sites-available/klar-seite
```

Füge einen neuen `server`-Block hinzu:
```nginx
server {
    listen 80;
    server_name eam.klar-seite.de;

    location / {
        proxy_pass http://127.0.0.1:8100;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 7b. DNS-Record setzen
Bei deinem Domain-Anbieter:
```
eam.klar-seite.de → 46.225.87.74
```

### 7c. SSL + Aktivieren
```bash
nginx -t
systemctl reload nginx
certbot --nginx -d eam.klar-seite.de
```

---

## Troubleshooting

**Docker startet nicht:**
```bash
docker compose logs
```
Meistens: .env nicht korrekt oder Port 8100 besetzt.

**Ingestion schlägt fehl:**
```bash
docker compose exec eam-cockpit python -c "from supabase import create_client; print('OK')"
```
Prüft ob Supabase-Verbindung funktioniert.

**Zu wenig RAM:**
```bash
free -h
```
4GB reicht. Falls knapp: `docker compose down` andere Container.

**PDFs werden nicht gefunden:**
```bash
docker compose exec eam-cockpit ls /opt/eam-cockpit/papers/
```
Müssen die 18 PDF-Dateien zeigen.

---

## Kosten

| Komponente | Monatlich |
|------------|-----------|
| Hetzner (bestehend) | 0 € (bereits bezahlt) |
| Supabase Free Tier | 0 € |
| OpenAI Embeddings (einmalig) | ~0.10 € |
| Claude API (pro Frage) | ~0.01 € |
| **Total Setup** | **~0.10 €** |
| **Total pro Monat** | **~1-5 €** (je nach Nutzung) |
