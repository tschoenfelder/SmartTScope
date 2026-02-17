
# SmartTScope – Kurzanleitung

Diese Kurz-Doku bringt dich schnell von **0 → laufender App** – erst unter **Windows** (Mock/OpenCV, ohne Pi-Kamera), danach die **Integration auf dem Raspberry Pi** mit **Picamera2**. Außerdem: **SSH über Port 443**, damit Pushes zu GitHub ohne PAT/Proxy-Stress funktionieren.

---

## 1) Voraussetzungen

- **Python 3.11**
- **Git**
- Windows: **PowerShell**
- Raspberry Pi OS (Bullseye/Bookworm) mit **libcamera** (see below 10))

Optional, aber praktisch:
- `venv` für eigene Python-Umgebung
- GitHub-SSH über Port 443 (siehe unten)

---

## 2) SSH auf Windows einrichten (einmalig, Port 443)

Damit GitHub im Firmennetz auch mit blockiertem Port 22 funktioniert.

1. **SSH-Key prüfen/erstellen**
   ```powershell
   dir $env:USERPROFILE\.ssh
   ssh-keygen -t ed25519 -C "tschoenfelder@SmartTScope"
   # -> Enter für Standardpfad, Passphrase nach Wunsch
   ```

2. **ssh-agent aktivieren & Key laden**
   ```powershell
   Get-Service ssh-agent | Set-Service -StartupType Automatic
   Start-Service ssh-agent
   ssh-add $env:USERPROFILE\.ssh\id_ed25519
   ssh-add -l   # zeigt deinen Key
   ```

3. **SSH-Config (ASCII!) für Port 443**
   > Achtung: Datei muss ASCII/UTF-8 sein, **nicht** UTF-16.
   ```powershell
   @"
   Host github.com
     HostName ssh.github.com
     User git
     Port 443
     IdentityFile C:/Users/U070420/.ssh/id_ed25519
     IdentitiesOnly yes
     AddKeysToAgent yes
   "@ | Out-File -Encoding ascii "$env:USERPROFILE\.ssh\config"
   ```

4. **Public Key bei GitHub hinterlegen**  
   GitHub → Settings → **SSH and GPG keys** → *New SSH key* → Inhalt von:
   ```powershell
   type $env:USERPROFILE\.ssh\id_ed25519.pub
   ```

5. **Testen**
   ```powershell
   ssh -T -p 443 git@ssh.github.com
   # Erwartung: "Hi <USER>! You've successfully authenticated, ..."
   ```

**Ein-Zeiler (Agent + Autoload Key) für PowerShell-Profil:**
```powershell
if ((Get-Service ssh-agent).Status -ne 'Running') { Start-Service ssh-agent }
ssh-add -l *> $null
if ($LASTEXITCODE -ne 0) { ssh-add $env:USERPROFILE\.ssh\id_ed25519 }
```

---

## 3) Repository klonen / verbinden

**Neu klonen (SSH, Port 443):**
```powershell
git clone git@github.com:tschoenfelder/SmartTScope.git
cd SmartTScope
```

**Bestehendes lokales Verzeichnis verbinden/umstellen:**
```powershell
git remote set-url origin git@github.com:tschoenfelder/SmartTScope.git
```

---

## 4) Windows – Entwicklung & TDD (Mock/OpenCV)

1. **Python-Umgebung**
   ```powershell
   python -m venv .venv
   . .venv/Scripts/Activate.ps1
   pip install -e .[dev,win]
   ```

2. **Starten (hardwarefrei, Mock)**
   ```powershell
   $Env:SMARTTSCOPE_CAMERA = "mock"
   smarttscope
   ```

3. **Alternative: OpenCV-Webcam**
   ```powershell
   $Env:SMARTTSCOPE_CAMERA = "opencv"
   smarttscope
   ```

4. **Tests & Qualität**
   ```powershell
   pytest -m "not integration"
   ruff check .
   ruff format --check .
   mypy src
   ```

5. **Dual-Viewer Demo**
   ```powershell
   $Env:SMARTTSCOPE_CAMERA  = "opencv"
   $Env:SMARTTSCOPE_CAMERA_B = "mock"
   python examples/dual_camera.py
   ```

> Adapterwahl jederzeit per ENV oder YAML (siehe `configs/*.yaml`).

---

## 5) Raspberry Pi – Integration mit Picamera2

1. **Systempakete**
   ```bash
   sudo apt update
   sudo apt install -y python3-picamera2 libcamera-apps
   ```

2. **Python-Umgebung**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e .[rpi]
   ```

3. **Kamera testen (optional)**
   ```bash
   libcamera-hello -t 2000
   ```

4. **SmartTScope starten**
   ```bash
   export SMARTTSCOPE_CAMERA=picamera2
   smarttscope
   ```

5. **Integrationstests (Pi)**
   ```bash
   pytest -m integration
   ```

> Für zwei CSI-Kameras Index 0/1 nutzen; ggf. ENV-Variablen/Factory erweitern (z. B. `SMARTTSCOPE_CAMERA_INDEX`).

---

## 6) Konfiguration (ENV oder YAML)

**Beispiel-YAML:** `configs/raspberry-pi.yaml`
```yaml
app:
  window: { width: 1024, height: 640 }
adapters:
  camera: picamera2   # mock | opencv | picamera2
```

**Mit YAML starten:**
```powershell
$Env:SMARTTSCOPE_CONFIG = "configs/windows-dev.yaml"
smarttscope
```
```bash
export SMARTTSCOPE_CONFIG=configs/raspberry-pi.yaml
smarttscope
```

**ENV überschreibt YAML:**  
`SMARTTSCOPE_CAMERA=mock|opencv|picamera2`

---

## 7) CI (Headless)

- Workflow liegt in `.github/workflows/ci.yml`  
- Headless Qt: `QT_QPA_PLATFORM=offscreen`  
- Startet bei Push/PR automatisch.  
- Für Pi-Tests: Self-hosted Runner (optional).

---

## 8) Troubleshooting (kurz)

- **`Permission denied (publickey)`**  
  Key im Account? `ssh-add -l` zeigt Key? `~/.ssh/config` als **ASCII** gespeichert? Port 443 in der Config?

- **Passphrase nervt bei jedem Push**  
  ssh-Agent dauerhaft aktivieren + Key einmal `ssh-add`. Siehe Ein-Zeiler oben.

- **OpenCV findet keine Webcam**  
  Auf `mock` wechseln: `SMARTTSCOPE_CAMERA=mock`

- **Qt „platform plugin“ Fehler auf Pi**  
  Unter Wayland: `export QT_QPA_PLATFORM=xcb` ausprobieren.

---

## 9) Häufige Befehle

```powershell
# Status & Branch
git status
git branch -vv

# Upstream beim ersten Push setzen
git push -u origin main

# Tests (ohne HW)
pytest -m "not integration"

# App starten (Windows, Mock)
$Env:SMARTTSCOPE_CAMERA = "mock"; smarttscope
```

Viel Erfolg mit **SmartTScope**!

---

## 10) Prepare Raspi5 (two cameras)

```
# (optional) Kameras checken
rpicam-hello --version
rpicam-hello --list-cameras
rpicam-hello --camera 0 -t 2000
rpicam-hello --camera 1 -t 2000   # falls zweite CSI-Kamera vorhanden

If fails, check sudo nano /boot/firmware/config.txt
# Automatically load overlays for detected cameras
# depending on IMX290 being connected to CSI port 0 or 1
camera_auto_detect=0
[all]
dtoverlay=imx290,cam0,clock-frequency=37125000
dtoverlay=imx477,cam1
```

0) Voraussetzungen (einmalig)
```
# System & Kamera-Tools
sudo apt update
sudo apt install -y git python3-venv python3-pip rpicam-apps python3-picamera2

# Qt/OpenGL-Libs (für PySide6 Fenster)
sudo apt install -y libegl1 libgl1 libxkbcommon-x11-0 libxcb-xinerama0 libxcb-cursor0

# (optional, falls Qt unter Wayland zickt)
# sudo apt install -y xorg xwayland
```

1) Repo klonen
Öffentliches Repo → kein Token nötig:
```
cd ~
git clone https://github.com/tschoenfelder/SmartTScope.git
cd SmartTScope
```

2) Python-Umgebung & Installation
```
sudo mkdir -p /mnt/nvme/piptmp
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip cache purge
TMPDIR=/mnt/nvme/piptmp pip install -U pip
pip cache purge
TMPDIR=/mnt/nvme/piptmp pip install --no-cache-dir "numpy<1.27" --upgrade --force-reinstall
TMPDIR=/mnt/nvme/piptmp pip install --no-cache-dir -e .[rpi]
```

3) SmartTScope starten
```
Single-Kamera
source .venv/bin/activate
export SMARTTSCOPE_CAMERA=picamera2
export SMARTTSCOPE_CAMERA_INDEX=0   # 0 = imx290 laut deiner Liste
smarttscope

Dual-Kamera
source .venv/bin/activate
export SMARTTSCOPE_CAMERA=picamera2
export SMARTTSCOPE_CAMERA_B=picamera2
export SMARTTSCOPE_CAMERA_INDEX=0      # imx290
export SMARTTSCOPE_CAMERA_B_INDEX=1    # imx477
python examples/dual_camera.py
```

Falls das Fenster leer/unsichtbar ist (Wayland/Remote-Desktop):
```
export QT_QPA_PLATFORM=xcb vor dem Start setzen.
```

4) Projekt später aktualisieren
 a) einmalig
```
 sudo apt update
 sudo apt install -y git python3-venv python3-pip python3-picamera2 rpicam-apps
 # optional: falls große Wheels kompiliert werden:
 sudo apt install -y build-essential libatlas-base-dev
```

 b) erstmalig
  Option A1 – SSH (empfohlen für private Repos, ohne Token-Prompts)

```

# Deploy-Key erzeugen (passwortlos ist ok, da nur read-only auf Repo)
ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519_smarttscope -C "pi-deploy"
cat ~/.ssh/id_ed25519_smarttscope.pub
```


Den Public Key in GitHub unter Repository → Settings → Deploy keys → Add deploy key eintragen (Read-Only genügt).

Dann klonen:

```
git clone git@github.com:tschoenfelder/SmartTScope.git
cd SmartTScope
```

Python-Umgebung vorbereiten (VENV mit System-Paketen)

So sieht die venv auch python3-picamera2 (kommt über apt).

```
cd ~/SmartTScope
python3 -m venv --system-site-packages .venv
source .venv/bin/activate

# (optional) großer Temp auf NVMe/USB, falls /tmp klein ist:
# mkdir -p /mnt/nvme/tmp && export TMPDIR=/mnt/nvme/tmp

pip install --upgrade pip wheel
pip install -e .[rpi]         # Projekt im Edit-Mode + RPi-Extras
```

  Option A2 – HTTPS (für öffentliche Repos oder mit PAT)
```

# Öffentliches Repo:
git clone https://github.com/tschoenfelder/SmartTScope.git
cd SmartTScope

# Privates Repo ohne Interaktivität (PAT im RAM):
# export GITHUB_TOKEN="DEIN_TOKEN_MIT_repo+workflow"
# git -c http.extraheader="AUTHORIZATION: Basic $(printf "tschoenfelder:$GITHUB_TOKEN" | base64 -w0)" clone https://github.com/tschoenfelder/SmartTScope.git
# cd SmartTScope
```

 c) Aktualisieren eines bestehenden Klons
```
cd ~/SmartTScope
git fetch origin
git switch main
git pull --ff-only
# bei lokalen Änderungen, die stören:
# git stash -u && git pull --ff-only && git stash pop
```

```
source .venv/bin/activate
pip install -e .[rpi]   # zieht neue Python-Abhängigkeiten nach
```

5) Starten (Dual-Cam Beispiel)
```
source ~/SmartTScope/.venv/bin/activate
export SMARTTSCOPE_CAMERA=picamera2
export SMARTTSCOPE_CAMERA_B=picamera2
# Indizes gemäß `rpicam-hello --list-cameras`:
export SMARTTSCOPE_CAMERA_INDEX=0
export SMARTTSCOPE_CAMERA_B_INDEX=1

python examples/dual_camera.py
```

Tipp: Kameras prüfen
```
rpicam-hello --list-cameras
# einzeln testen:
rpicam-hello --camera 0 -t 2000
rpicam-hello --camera 1 -t 2000
```

6) Auf neueste Version aktualisieren (Kurzform – täglich)
```
cd ~/SmartTScope
git pull --ff-only
source .venv/bin/activate
pip install -e .[rpi]
```

7) Troubleshooting (kurz)

„Device busy/Resource is busy“
Stelle sicher, dass zwei unterschiedliche Indizes verwendet werden und keine Fremdprozesse die Kamera halten:

```
pgrep -fa 'rpicam|libcamera' || true
# testweise (nur wenn nötig) User-Services pausieren:
systemctl --user stop pipewire wireplumber 2>/dev/null || true
```

Picamera2 nicht gefunden
Venv neu mit System-Site-Packages anlegen:

```
rm -rf .venv
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -e .[rpi]
```


Sicherstellen, dass der richtige Code aktiv ist

```
python - <<'PY'
import smarttscope, inspect
import smarttscope.app.factory as f
print("smarttscope:", inspect.getsourcefile(smarttscope))
print("factory.py:", inspect.getsourcefile(f))
PY
```

Push local changes to git:
Option A – Lokale Commits behalten und auf origin/main rebased

(empfohlen, wenn du deine Raspi-Änderungen behalten willst)

```
git fetch origin
git rebase origin/main
# bei Konflikten: Dateien lösen, dann
git add <gelöste/dateien>
git rebase --continue


Danach ist dein lokaler Branch = origin/main + deine Commits oben drauf.
Wenn du nicht pushen willst (Raspi nur Konsument): fertig.
Falls du die Raspi-Commits teilen willst: als separaten Branch hochladen:

git switch -c pi-work
git push -u origin pi-work
```

Option B – Lokale Commits verwerfen und exakt auf Remote gehen

(wenn deine Raspi-Änderungen nicht wichtig sind)

```
git fetch origin
git reset --hard origin/main
git clean -fdX   # optional: untracked/ignorierte Buildfiles weg
```


Jetzt entspricht dein Arbeitsbaum exakt origin/main.

Option C – Merge-Commit zulassen (kein FF, kein Rebase)

(einfach, aber Geschichte wird „verzweigt“)

```
git fetch origin
git merge origin/main     # löst Konflikte aus wie üblich
```

Hilfreiche Checks (vorher / nachher)
```
git status -sb
git log --oneline --decorate --graph --all --max-count=20
```


Wenn stash dir „Keine lokalen Änderungen“ meldete, heißt das nur: keine uncommitteten Änderungen.
Die Divergenz kommt von lokalen Commits → darum scheitert --ff-only.

Tipp: Wenn du künftig immer rebasen willst:

```
git config --global pull.rebase true
```


Dann reicht git pull (ohne --ff-only) und Git rebased automatisch statt zu mergen.

QT Designer übersetzen:
pyside6-rcc resources.qrc -o resources_rc.py
pyside6-uic SmartTScope.ui -o ui_smarttscope.py


Credits:
Icons: 
https://composables.com/
Lucide (ISC)
Tabler Icons (MIT
https://fluent2.microsoft.design
https://icons.getbootstrap.com/
https://github.com/google/material-design-icons/
https://fonts.google.com/icons?
