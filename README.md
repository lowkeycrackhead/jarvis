# J.A.R.V.I.S. — Windows Voice Assistant & Touch Web HUD

A Windows Python voice assistant with an interactive touch-sensitive Flask web HUD (`server.py` + `index.html`), hybrid local/cloud AI routing via [Ollama](https://docs.ollama.com/windows) (`llama3.2:3b`) and Google Gemini, native Spotify desktop app control, YouTube playback, live task cancellation, and one-click Windows setup (`start.bat`).

Repository: [lowkeycrackhead/jarvis](https://www.google.com/search?q=https://github.com/lowkeycrackhead/jarvis)

## Features

* **Zero-Manual-Setup Launcher (`start.bat` + `setup.ps1`):** Anyone who clones the repo simply double-clicks `start.bat` to automatically set up `.venv`, install Python dependencies, install [Ollama for Windows](https://ollama.com/download/windows), pull `llama3.2:3b`, and launch Jarvis.

* **Hybrid AI Engine (Local + Cloud):** Runs locally with [Ollama](https://ollama.com/download/windows) (`llama3.2:3b` by default) for fast offline answers and falls back automatically to Google Gemini in `auto` mode. Switch anytime from the web HUD or by voice.

* **Interactive Touch Web HUD (`server.py`):** Dark glassmorphic interface at `http://127.0.0.1:5000` with a live neural particle field, magnetic 3D Arc-Reactor core (tap, hold-to-talk, double-tap pulse), audio-reactive waveform ring, quick-action chips, haptics, and an **AI: Auto / Ollama / Gemini** mode toggle.

* **Live Task Cancellation:** Stop any in-progress AI response, speech output, or automation wait immediately using **Stop Task**, swiping left on the task bar, or pressing `Esc`.

* **Spotify Desktop App Control (Windows):** Launch the installed Spotify app (standard or Microsoft Store) and play the top result for any requested song (`"play [song] on spotify"`).

* **Music & Web Shortcuts:** Play songs from your custom `musiclibrary.py` or YouTube, open common websites, and check the current date, time, or live weather.

* **Hands-Free Voice Mode (`main.py`):** Wake-word listening (`"Jarvis"`), speech recognition via `SpeechRecognition`, and spoken replies via `gTTS` + `pygame`.

## Project Structure

| File | Description | 
| ----- | ----- | 
| `start.bat` | One-click Windows launcher (bypasses PowerShell policy and runs `setup.ps1`) | 
| `setup.ps1` | Auto-setup script: creates `.venv`, installs Python deps, installs Ollama if missing, pulls `llama3.2:3b`, and starts Jarvis | 
| `main.py` | Core voice assistant, wake-word loop, AI routing (Ollama + Gemini + backup), Spotify automation, and cancellable task helpers | 
| `server.py` | Flask backend serving the web HUD and REST endpoints on `127.0.0.1:5000` | 
| `index.html` | Interactive touch-sensitive J.A.R.V.I.S. web interface with live particle field, gestures, AI toggle, and Stop Task controls | 
| `musiclibrary.py` | Dictionary mapping custom song names to direct YouTube links | 
| `client.py` | Minimal test script calling `main.aiprocess(...)` directly | 
| `.env.example` | Template for API keys, AI provider mode, and Ollama model settings | 
| `requirements.txt` | Python package dependencies | 
| `dockerfile` | Container configuration for the project | 

## Quick Start (Windows)

### Option A: One-Click Auto-Setup (Recommended)

Clone the repository and double-click `start.bat` (or run it in PowerShell):

```
git clone https://github.com/lowkeycrackhead/jarvis.git
cd jarvis
.\start.bat

```

On first launch, `start.bat` automatically:

1. Creates a `.venv` virtual environment and installs `requirements.txt`.

2. Creates `.env` from `.env.example` if missing.

3. Installs [Ollama for Windows](https://ollama.com/download/windows) automatically if it isn't installed yet.

4. Starts Ollama and downloads [Llama 3.2 3B](https://ollama.com/library/llama3.2) (\~2 GB, one-time).

5. Launches the J.A.R.V.I.S. Touch Web HUD at `http://127.0.0.1:5000`.

To launch voice-only terminal mode instead, run:

```
.\start.bat -VoiceOnly

```

### Option B: Manual Setup

1. Install Python dependencies: `pip install -r requirements.txt`

2. Copy `.env.example` to `.env` and optionally add your `GEMINI_API_KEY`.

3. Install [Ollama for Windows](https://ollama.com/download/windows) and run `ollama pull llama3.2:3b`.

4. Run `python server.py` (web HUD) or `python main.py` (voice-only).

## Supported Commands

| Category | Example Commands | Behavior | 
| ----- | ----- | ----- | 
| **AI Engine** | `"use ollama"`, `"use gemini"`, `"use auto"` | Switches active AI routing mode on the fly | 
| **Spotify** | `"open spotify"`, `"play blinding lights on spotify"` | Launches Windows Spotify app, searches, and plays the top result | 
| **Music & YouTube** | `"play lip shade"`, `"play [song name]"`, `"stop music"`, `"pause spotify"` | Plays from `musiclibrary.py` or YouTube; pauses/stops playback | 
| **Websites** | `"open google"`, `"open youtube"`, `"open github"`, `"open gmail"`, `"open whatsapp"`, `"open instagram"`, `"open reddit"`, `"open facebook"`, `"open twitter"` | Opens the site in your default browser | 
| **Date, Time & Weather** | `"what time is it"`, `"what is today's date"`, `"how is the weather today"` | Returns local time/date or live weather data | 
| **General AI** | Any other question or prompt | Answered by Ollama and/or Gemini based on `AI_PROVIDER` | 
| **Control** | `"stop"`, `"exit"`, `"quit"`, `"shut down"`, `"thank you"` | Shuts down voice mode (or cancels tasks via Web HUD Stop / `Esc`) | 

## Environment Variables

| Variable | Default | Description | 
| ----- | ----- | ----- | 
| `AI_PROVIDER` | `auto` | `auto` (prefers local Ollama when running, falls back to Gemini), `ollama` (local only), or `gemini` (cloud only) | 
| `OLLAMA_MODEL` | `llama3.2:3b` | Preferred local Ollama model name (auto-detects installed models if different) | 
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Local Ollama API endpoint | 
| `GEMINI_API_KEY` | *(none)* | Google Gemini API key (also accepts `GOOGLE_API_KEY`) | 
| `GEMINI_MODEL` | *(auto)* | Optional override for the Gemini model name | 

## Web HUD API Endpoints

| Method & Route | Purpose | 
| ----- | ----- | 
| `GET /` | Serves the `index.html` J.A.R.V.I.S. HUD | 
| `GET /api/health` | Returns server status, active task label, AI provider, and Ollama readiness | 
| `POST /api/provider` | Switches AI provider (`{"provider": "auto" | "ollama" | "gemini"}`) | 
| `POST /api/command` | Executes a Jarvis command (`{"text": "..."}`) and returns replies | 
| `POST /api/stop` | Immediately cancels any currently running task, AI call, or automation wait | 
| `POST /api/listen` | Records one spoken phrase from the host microphone and returns recognized text | 

## Troubleshooting

* **`ModuleNotFoundError: No module named 'pyaudio'`:** Run `pip install PyAudio` in the active Python environment, or use Python 3.11/3.12 where prebuilt Windows wheels are available.

* **Ollama shows offline in the Web HUD:** Confirm Ollama is running in the Windows system tray (`http://127.0.0.1:11434`) and that you have pulled at least one model (`ollama pull llama3.2:3b`).

* **Spotify opens but doesn't start playing:** Keep the Spotify window focused briefly while Jarvis sends the quick-search shortcut, and make sure you are signed in to the desktop app.