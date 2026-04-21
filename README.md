# Voice Brain Dump Machine

A Raspberry Pi application that captures voice notes via a USB microphone,
transcribes them locally with whisper.cpp, extracts actionable tasks using an
Ollama language model running on your local network, and manages them through a
mobile-friendly web interface.

---

## How it works

1. Press the physical button on **GPIO17** to start recording.
2. Press it again to stop.
3. The audio is transcribed locally using **whisper.cpp**.
4. The transcript is sent to an **Ollama** server on your local network.
5. Ollama returns a structured list of tasks.
6. Tasks are saved to a local **SQLite** database.
7. The web UI updates automatically and shows your full task list.

---

## Project structure

```
voice_brain_dump/
├── app.py            # Flask app and all routes
├── recorder.py       # Recording and transcription workflow
├── gpio_handler.py   # Physical button handling (gpiozero)
├── ai_formatter.py   # Ollama HTTP integration and task parsing
├── db.py             # SQLite database setup and CRUD operations
├── state.py          # Shared in-memory app state (status, transcript, errors)
├── requirements.txt
├── .env.example
├── templates/
│   └── index.html
├── static/
│   └── style.css
└── data/
    └── tasks.db      # Created automatically on first run
```

---

## Requirements

### Raspberry Pi

- Raspberry Pi (any model with GPIO, tested on Pi 4)
- Raspberry Pi OS (Bookworm or later recommended)
- USB microphone (set up as ALSA device `plughw:3,0` by default)
- Pushbutton wired between GPIO17 and GND
- Python 3.11 or later
- `alsa-utils` installed (`sudo apt install alsa-utils`)

### whisper.cpp

Build whisper.cpp on the Pi and note the paths to:

- The `whisper-cli` binary (default: `/home/james/whisper.cpp/build/bin/whisper-cli`)
- The model file (default: `/home/james/whisper.cpp/models/ggml-base.en.bin`)

See the [whisper.cpp README](https://github.com/ggerganov/whisper.cpp) for build instructions.

### Ollama

Ollama must be running on **another machine on the same local network** (or on
the Pi itself if it has enough RAM).

Install Ollama: https://ollama.com  
Pull a model: `ollama pull llama3.1:8b`  
Start the server: `ollama serve`

By default Ollama listens on port `11434`.

---

## Installation

### 1. Clone or copy the project

```bash
git clone <your-repo> ~/voice_brain_dump
cd ~/voice_brain_dump
```

### 2. Create a Python virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
nano .env
```

Key variables to set:

| Variable          | Description                                           | Default                                                  |
|-------------------|-------------------------------------------------------|----------------------------------------------------------|
| `OLLAMA_BASE_URL` | Base URL of your Ollama server                        | `http://192.168.1.100:11434`                             |
| `OLLAMA_MODEL`    | Model name to use                                     | `llama3.1:8b`                                            |
| `OLLAMA_TIMEOUT`  | Seconds to wait for Ollama before timing out          | `60`                                                     |
| `AUDIO_DEVICE`    | ALSA device string for your USB microphone            | `plughw:3,0`                                             |
| `WHISPER_BINARY`  | Path to the `whisper-cli` binary                      | `/home/james/whisper.cpp/build/bin/whisper-cli`          |
| `WHISPER_MODEL`   | Path to the ggml model weights                        | `/home/james/whisper.cpp/models/ggml-base.en.bin`        |
| `FLASK_HOST`      | Interface to bind the web server to                   | `0.0.0.0`                                                |
| `FLASK_PORT`      | Port for the web UI                                   | `5000`                                                   |

### 5. Find your microphone ALSA device

```bash
arecord -l
```

Look for your USB microphone in the output and note the card and device numbers.  
For card 3, device 0, the value is `plughw:3,0`.

---

## Running the app

```bash
source venv/bin/activate
python app.py
```

Open the web UI in your browser at `http://<raspberry-pi-ip>:5000`.

---

## Starting automatically on boot with systemd

### 1. Create the service file

```bash
sudo nano /etc/systemd/system/voice-brain-dump.service
```

Paste the following (adjust paths if your username is not `james`):

```ini
[Unit]
Description=Voice Brain Dump Machine
After=network.target

[Service]
Type=simple
User=james
WorkingDirectory=/home/james/voice_brain_dump
EnvironmentFile=/home/james/voice_brain_dump/.env
ExecStart=/home/james/voice_brain_dump/venv/bin/python app.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 2. Enable and start the service

```bash
sudo systemctl daemon-reload
sudo systemctl enable voice-brain-dump
sudo systemctl start voice-brain-dump
```

### 3. Check the logs

```bash
sudo journalctl -u voice-brain-dump -f
```

---

## Web UI

The homepage (`http://<pi-ip>:5000`) shows:

- Current app status: `Idle`, `Recording`, `Processing`, or `Error`
- The latest raw transcript
- A form to add tasks manually
- Your full pending task list with tick-off and delete buttons
- Your completed task list with undo and delete buttons
- A button to clear all completed tasks

The page polls `/api/state` every 4 seconds and reloads automatically when a
recording finishes processing, so you do not need to refresh manually.

### API endpoints

| Method | Route                    | Description                    |
|--------|--------------------------|--------------------------------|
| GET    | `/api/state`             | Current app state as JSON      |
| GET    | `/api/tasks`             | All tasks (pending/completed)  |

---

## Troubleshooting

**Button does nothing**  
Check the wiring: one leg of the button to GPIO17, other leg to GND.  
Run `sudo journalctl -u voice-brain-dump -f` to see GPIO errors.

**Microphone not found**  
Run `arecord -l` to confirm the device number and update `AUDIO_DEVICE` in `.env`.

**whisper-cli not found**  
Verify `WHISPER_BINARY` points to the compiled binary and that it is executable
(`chmod +x /path/to/whisper-cli`).

**Ollama not responding**  
- Confirm Ollama is running on the remote machine: `ollama serve`
- Check `OLLAMA_BASE_URL` is correct and the Pi can reach that IP on port 11434
- Try `curl http://<ollama-ip>:11434/api/tags` from the Pi to test connectivity

**Tasks not being extracted**  
Check the logs for the raw Ollama response. You may need a larger or different
model. Set `OLLAMA_MODEL` to the model name you have pulled on the Ollama server.

---

## Continuous deployment via GitHub Actions

Every push to `main` automatically deploys to the Pi and restarts the service.
This is done using a **self-hosted GitHub Actions runner** installed on the Pi
itself — the Pi polls GitHub, so no port forwarding or public IP is required.

### 1. Register the runner on the Pi

On GitHub, go to your repository → **Settings** → **Actions** → **Runners** →
**New self-hosted runner**.

Select **Linux / ARM64** (Pi 4/5) or **ARM** (Pi 3), then follow the commands
GitHub shows — they look like this (the token will differ):

```bash
# Run these on the Pi
mkdir -p ~/actions-runner && cd ~/actions-runner
curl -o actions-runner-linux-arm64-2.x.x.tar.gz -L https://github.com/actions/runner/releases/download/v2.x.x/actions-runner-linux-arm64-2.x.x.tar.gz
tar xzf actions-runner-linux-arm64-2.x.x.tar.gz
./config.sh --url https://github.com/<your-username>/<your-repo> --token <your-token>
```

Use the exact commands and token from the GitHub UI — they expire after an hour.

### 2. Install the runner as a systemd service

```bash
cd ~/actions-runner
sudo ./svc.sh install
sudo ./svc.sh start
```

The runner now starts automatically on boot and runs in the background.

### 3. Allow the runner to restart the app service without a password

The deployment workflow restarts `voice-brain-dump` with `sudo systemctl restart`.
Grant the runner user (usually `james`) passwordless permission for that one
command only:

```bash
sudo visudo -f /etc/sudoers.d/voice-brain-dump
```

Add this line (replace `james` with your username if different):

```
james ALL=(ALL) NOPASSWD: /bin/systemctl restart voice-brain-dump
```

### 4. Set the correct working directory in the service file

The runner checks out code into `~/actions-runner/_work/<repo>/<repo>`.
Update the `WorkingDirectory` in your systemd service to match, for example:

```ini
WorkingDirectory=/home/james/actions-runner/_work/Brain_Dump/Brain_Dump/voice_brain_dump
EnvironmentFile=/home/james/actions-runner/_work/Brain_Dump/Brain_Dump/voice_brain_dump/.env
ExecStart=/home/james/actions-runner/_work/Brain_Dump/Brain_Dump/voice_brain_dump/venv/bin/python app.py
```

Then reload systemd:

```bash
sudo systemctl daemon-reload
sudo systemctl restart voice-brain-dump
```

### 5. Push to deploy

```bash
git add .
git commit -m "your changes"
git push origin main
```

GitHub triggers the workflow, the runner on the Pi pulls the latest code,
updates dependencies, and restarts the service. Watch progress in the
**Actions** tab of your repository.

### Deployment pipeline summary

```
git push → GitHub Actions → self-hosted runner on Pi
                                  │
                                  ├─ git pull latest code
                                  ├─ pip install -r requirements.txt
                                  ├─ sudo systemctl restart voice-brain-dump
                                  └─ systemctl is-active check
```
# Brain_Dump
