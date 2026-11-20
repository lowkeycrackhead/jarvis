# J.A.R.V.I.S. — Dual-Mode AI Voice Assistant & Touch Web HUD

A hybrid AI assistant built with Python and Flask that runs in **two modes** from the same codebase:

1. **Cloud Web Mode (Vercel + Supabase):** Open in any browser with zero installation—live streaming Gemini AI, Brave/Firefox/Chrome voice input, browser Screen Vision, Personas, Focus Timers, and cloud-synced Quick Notes & Chat History.

2. **Local Windows Desktop Mode:** Full hardware and OS control—local GPU-accelerated [Ollama](https://docs.ollama.com/windows) (`llama3.2:3b`), hands-free Spotify desktop auto-play, live CPU/RAM/Battery gauges, Windows volume & brightness sliders, desktop Screen Vision, clipboard summarization, and app launching.

* **Live Web App:** [jarvis-sepia-omega-42.vercel.app](https://jarvis-sepia-omega-42.vercel.app)

* **Repository:** [lowkeycrackhead/jarvis](https://www.google.com/search?q=https://github.com/lowkeycrackhead/jarvis)

## Cloud Mode vs. Local Windows Mode

| Feature | Way 1: Cloud Web Mode (Vercel + Supabase) | Way 2: Local Windows Mode (`start.bat` / `server.py`) | 
| ----- | ----- | ----- | 
| **Installation required** | None (runs in any browser) | One-click `start.bat` on Windows 10/11 | 
| **Touch Web HUD & Live Streaming** | Yes | Yes | 
| **Voice Input** | Chrome/Edge Web Speech API + automatic `MediaRecorder` fallback for Brave, Firefox & Safari | Browser mic + host PC microphone (`SpeechRecognition`) | 
| **AI Engine** | Cloud Gemini (`GEMINI_API_KEY`) | Local Ollama (`llama3.2:3b` on GPU/CPU) + automatic Gemini fallback | 
| **Personas & Memory** | Butler, Coder, Study Tutor + Supabase chat history | Butler, Coder, Study Tutor + local/Supabase memory | 
| **Quick Notes & Focus Timers** | Synced in Supabase PostgreSQL | Saved in `jarvis_data.json` (or Supabase if configured) | 
| **Screen Vision** | Browser window/screen picker (`getDisplayMedia` → `/api/vision`) | Silent desktop capture (`Pillow` → Gemini or local `gemma3:4b`) | 
| **Spotify Control** | Launches Spotify desktop app & opens search (`spotify:search:`) | Launches Spotify desktop app, searches, and **auto-plays** the #1 track | 
| **Windows PC Controls & Gauges** | Not available (browser security limit) | Live CPU/RAM/Battery gauges, volume/brightness sliders, lock PC, screenshot, clipboard, open/close apps | 

## Way 1: Using & Deploying Cloud Web Mode (Vercel + Supabase)

### Using the Live App (End Users)

1. Open [jarvis-sepia-omega-42.vercel.app](https://jarvis-sepia-omega-42.vercel.app) in Chrome, Edge, Brave, Firefox, or Safari.

2. Tap or hold the glowing Arc-Reactor core to speak (in Brave, Firefox, or Safari, tap once to start recording and tap again to transcribe and send).

3. Click **HUD Panel** in the top bar to switch Personas (**Butler**, **Coder**, **Study Tutor**), start Focus Timers, or manage cloud-synced Quick Notes.

4. Click **See Screen** to share any browser tab or window for instant AI explanation.

### Requirements to Deploy Your Own Copy

* A free [Vercel](https://vercel.com/docs/frameworks/backend/flask) account (connected to GitHub)

* A free Supabase project (can be created directly inside Vercel's **Storage** tab)

* A Google Gemini API key (`GEMINI_API_KEY`)

* **Cloud Python dependencies** (automatically installed by Vercel from `requirements.txt`):

  * `flask`

  * `google-genai`

  * `python-dotenv`

### Deployment Steps (Vercel + Supabase)

1. **Import on Vercel:** Push or fork the repo on GitHub, import it on Vercel (Vercel auto-detects **Flask** via `server.py` and `vercel.json`), and click **Deploy**.

2. **Link Supabase:** Inside your Vercel project, open **Storage → Create Database → Supabase (Free Plan)** so Vercel automatically injects `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY`.

3. **Create Database Tables:** Open your Supabase dashboard → **SQL Editor → New query**, paste the contents of `supabase_schema.sql`, and click **Run**. This creates `jarvis_notes`, `jarvis_timers`, and `jarvis_messages`.

4. **Add Environment Variable:** In Vercel → **Settings → Environment Variables**, add `GEMINI_API_KEY`, then redeploy (or push any commit). The top-left HUD badge will switch to **CLOUD · SUPABASE**.

## Way 2: Running Locally on Windows (Full Desktop Power)

### System & Software Requirements

* **OS:** Windows 10 (22H2+) or Windows 11

* **Python:** Python 3.10, 3.11, or 3.12 (recommended for prebuilt `PyAudio` wheels)

* **Hardware:** Microphone; 8–16 GB RAM recommended for local Ollama (`llama3.2:3b` uses \~2 GB disk space)

* **Optional:** Installed Spotify desktop app (for hands-free Spotify playback), Intel Arc / NVIDIA / AMD GPU for fast local AI

* **Desktop Python dependencies** (`requirements-desktop.txt`):

  * Core: `flask`, `google-genai`, `python-dotenv`

  * Voice & Audio: `SpeechRecognition`, `PyAudio`, `gTTS`, `pygame`

  * Desktop Automation & Vision: `pywhatkit`, `pyautogui`, `psutil`, `Pillow`

### Option A: One-Click Auto-Setup (Recommended)

Clone the repository and double-click `start.bat` (or run it in PowerShell):

```
git clone https://github.com/lowkeycrackhead/jarvis.git
cd jarvis
.\start.bat

```

On first launch, `start.bat` + `setup.ps1` automatically:

1. Creates a `.venv` virtual environment and installs `requirements-desktop.txt`.

2. Creates `.env` from `.env.example` if missing.

3. Detects Intel Arc / Intel GPUs (without NVIDIA) and automatically enables Vulkan GPU acceleration (`OLLAMA_VULKAN=1`, `OLLAMA_IGPU_ENABLE=1`).

4. Installs [Ollama for Windows](https://ollama.com/download/windows) if not installed and downloads [Llama 3.2 3B](https://ollama.com/library/llama3.2) (\~2 GB, one-time).

5. Launches the Touch Web HUD at `http://127.0.0.1:5000`.

To launch hands-free voice-only terminal mode (`main.py`) instead:

```
.\start.bat -VoiceOnly

```

### Option B: Manual Local Setup

```
# 1. Install all desktop Python dependencies
pip install -r requirements-desktop.txt

# 2. Copy .env.example to .env and configure your keys/model
copy .env.example .env

# 3. Install Ollama for Windows and pull the default model
irm https://ollama.com/install.ps1 | iex
$env:Path += ";$env:LOCALAPPDATA\Programs\Ollama"
ollama pull llama3.2:3b

# Optional: pull gemma3:4b for offline local Screen Vision without a Gemini key
ollama pull gemma3:4b

# 4. Run the Touch Web HUD (or python main.py for voice-only mode)
python server.py

```

If PowerShell blocks `irm`, install Ollama via WinGet ([winstall](https://winstall.app/apps/Ollama.Ollama)): `winget install --id Ollama.Ollama`.

### Intel Arc GPU Acceleration (Avoid 100% CPU Usage)

On Windows laptops with Intel Arc graphics, Ollama defaults to CPU unless Vulkan + iGPU detection are enabled ([Intel Arc guide](https://dev.to/fanmixco/how-to-enable-ollama-gpu-acceleration-on-intel-arc-in-windows-2ll6)):

```
setx OLLAMA_VULKAN 1
setx OLLAMA_IGPU_ENABLE 1

```

Quit Ollama from the system tray, reopen it, run `ollama run llama3.2:3b "hi"`, and verify with `ollama ps` that the **PROCESSOR** column shows `100% GPU` ([Popular AI guide](https://www.popularai.org/p/fix-ollama-cpu-offloading-slow-inference)). (`setup.ps1` applies this automatically on Intel GPU machines.)

## Supported Voice & HUD Commands

| Category | Example Commands | Local Mode | Cloud Mode | 
| ----- | ----- | ----- | ----- | 
| **AI & Personas** | `"use ollama"`, `"use gemini"`, `"use auto"`, `"coder mode"`, `"tutor mode"`, `"butler mode"`, `"clear memory"` | Full support | Gemini + Personas | 
| **Screen Vision** | `"explain what is on my screen"`, `"read my screen"`, `"look at my screen"` | Silent desktop capture | Browser window picker | 
| **Spotify** | `"open spotify"`, `"play blinding lights on spotify"` | Launches app + auto-plays #1 track | Launches Spotify app to search | 
| **Music & YouTube** | `"play lip shade"`, `"play [song name]"`, `"stop music"`, `"pause spotify"` | `musiclibrary.py` / YouTube + media keys | Opens YouTube search tab | 
| **PC Controls** | `"system status"`, `"battery"`, `"set volume to 60"`, `"set brightness to 80"`, `"take a screenshot"`, `"lock screen"`, `"open vs code"`, `"close chrome"` | Full Windows control | Not available | 
| **Clipboard** | `"read my clipboard"`, `"summarize my clipboard"` | Reads Windows clipboard | Not available | 
| **Timers & Notes** | `"set a 25 minute timer for focus"`, `"note down buy cables"`, `"read my notes"` | Local JSON / Supabase | Synced via Supabase | 
| **Websites & Info** | `"open youtube"`, `"open github"`, `"open gmail"`, `"what time is it"`, `"how is the weather today"` | Opens locally | Opens browser tab | 
| **Task Control** | Click **Stop Task**, swipe left on task bar, press `Esc`, or say `"stop"` / `"shut down"` | Full support | Full support | 

## Project Structure

| File | Description | 
| ----- | ----- | 
| `server.py` | Flask backend serving the Touch Web HUD, SSE streaming, Vision, Transcription, Supabase sync, and PC control APIs | 
| `main.py` | Core voice assistant, wake-word loop, Ollama/Gemini streaming & fallback, Spotify automation, and command router | 
| `jarvis_extras.py` | Personas, Supabase REST client, persistent Notes & Timers, Windows telemetry (`psutil`), volume/brightness, clipboard, and Screen Vision | 
| `index.html` | Interactive Touch HUD with neural particle canvas, real mic-reactive waveform orb, hold-to-talk, streaming chat, and HUD Control Panel | 
| `vercel.json` | Vercel Flask function config bundling `index.html`, `jarvis_extras.py`, and `musiclibrary.py` | 
| `supabase_schema.sql` | SQL script to create `jarvis_notes`, `jarvis_timers`, and `jarvis_messages` tables in Supabase | 
| `requirements.txt` | Lean cloud dependencies for Vercel (`flask`, `google-genai`, `python-dotenv`) | 
| `requirements-desktop.txt` | Full Windows desktop dependencies (adds `SpeechRecognition`, `PyAudio`, `gTTS`, `pygame`, `pywhatkit`, `pyautogui`, `psutil`, `Pillow`) | 
| `start.bat` & `setup.ps1` | One-click Windows auto-installer and launcher (Python `.venv`, deps, Intel GPU Vulkan setup, Ollama + `llama3.2:3b`) | 
| `musiclibrary.py` | Custom song-to-YouTube shortcut dictionary | 
| `.env.example` | Template for Gemini, Ollama, and Supabase environment variables | 

## Environment Variables

| Variable | Default | Where Used | Description | 
| ----- | ----- | ----- | ----- | 
| `GEMINI_API_KEY` | *(none)* | Cloud & Local | Google Gemini API key (required for Vercel AI, Screen Vision & Brave voice transcription) | 
| `SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_URL` | *(none)* | Cloud & Optional Local | Supabase project URL for cloud-synced notes, timers & history | 
| `SUPABASE_KEY` / `NEXT_PUBLIC_SUPABASE_ANON_KEY` | *(none)* | Cloud & Optional Local | Supabase anon or service-role key | 
| `AI_PROVIDER` | `auto` (local) / `gemini` (Vercel) | Local & Cloud | `auto`, `ollama`, or `gemini` | 
| `OLLAMA_MODEL` | `llama3.2:3b` | Local | Preferred local Ollama model | 
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Local | Local Ollama API endpoint | 

## API Endpoints (`server.py`)

| Method & Route | Purpose | 
| ----- | ----- | 
| `GET /` | Serves the `index.html` Touch Web HUD | 
| `GET /api/health` | Returns server status, active task, AI provider, Ollama readiness, persona, cloud mode, and Supabase status | 
| `POST /api/stream` | Streams AI replies word-by-word via Server-Sent Events (SSE) or runs direct commands | 
| `POST /api/command` | Non-streaming JSON command execution | 
| `POST /api/stop` | Immediately cancels any active AI stream, speech, or automation wait | 
| `POST /api/provider` | Switches AI provider (`auto`, `ollama`, `gemini`) | 
| `POST /api/persona` | Switches active persona (`butler`, `coder`, `tutor`) | 
| `POST /api/memory/clear` | Clears multi-turn conversation history | 
| `POST /api/vision` | Analyzes a browser-captured base64 JPEG screen snapshot via Gemini Vision | 
| `POST /api/transcribe` | Transcribes browser-recorded voice clips (for Brave, Firefox & Safari) via Gemini audio | 
| `POST /api/listen` | Records one phrase from the host PC microphone (local Windows mode only) | 
| `GET /api/history` | Fetches recent chat history from Supabase | 
| `GET /api/system`, `POST /api/system/volume`, `POST /api/system/brightness`, `POST /api/system/action` | Live PC gauges and Windows controls (local Windows mode only) | 
| `GET/POST /api/notes`, `DELETE /api/notes/<id>` | Persistent Quick Notes (Supabase or local JSON) | 
| `GET/POST /api/timers`, `DELETE /api/timers/<id>` | Live Focus Timers (Supabase or local JSON) | 

## Troubleshooting

* **Voice input fails in Brave (`network` error):** Brave blocks Google's Web Speech servers ([Stack Overflow](https://stackoverflow.com/questions/74113965/speechrecognition-emitting-network-error-event-in-brave-browser)). Jarvis automatically switches to tap-to-record mode (`/api/transcribe`)—just tap the core once to record and tap again to send (requires `GEMINI_API_KEY`).

* **Ollama uses 100% CPU on Intel Arc:** Run `setx OLLAMA_VULKAN 1` and `setx OLLAMA_IGPU_ENABLE 1`, restart Ollama from the system tray, and verify `100% GPU` with `ollama ps`.

* **`ModuleNotFoundError: No module named 'pyaudio'` / `psutil` / `PIL`:** Run `pip install -r requirements-desktop.txt` (or double-click `start.bat`).

* **Spotify searches but doesn't auto-play on Vercel:** Browsers block websites from sending keyboard shortcuts to desktop apps. Run `.\start.bat` or `python server.py` locally for full hands-free Spotify auto-play.