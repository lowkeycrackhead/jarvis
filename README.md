# J.A.R.V.I.S. — Windows Voice Assistant & Touch Web HUD

A Windows Python voice assistant with an interactive touch-sensitive Flask web HUD (`server.py` + `index.html`), hybrid local/cloud AI routing via [Ollama](https://docs.ollama.com/windows) (`llama3.2:3b`) and Google Gemini, native Spotify desktop app control, YouTube playback, live task cancellation, and one-click Windows setup (`start.bat`).

Repository: [lowkeycrackhead/jarvis](https://github.com/lowkeycrackhead/jarvis)

## Features

* **Hybrid AI Engine (Local + Cloud):** Runs locally with [Ollama](https://ollama.com/download/windows) (`llama3.2:3b` by default) for fast offline answers and falls back automatically to Google Gemini in `auto` mode. Switch anytime from the web HUD or by voice.

* **Aesthetic Web HUD (`server.py`):** Dark glassmorphic interface at `http://127.0.0.1:5000` with voice capture, text commands, quick-action chips, live status indicators, and an **AI: Auto / Ollama / Gemini** mode toggle.

* **Live Task Cancellation:** Stop any in-progress AI response, speech output, or automation wait immediately using the **Stop Task** button in the web HUD or by pressing `Esc`.

* **Spotify Desktop App Control (Windows):** Launch the installed Spotify app (standard or Microsoft Store) and play the top result for any requested song (`"play [song] on spotify"`).

* **Music & Web Shortcuts:** Play songs from your custom `musiclibrary.py` or YouTube, open common websites, and check the current date, time, or live weather.

* **Hands-Free Voice Mode (`main.py`):** Wake-word listening (`"Jarvis"`), speech recognition via `SpeechRecognition`, and spoken replies via `gTTS` + `pygame`.

## Project Structure

| File | Description | 
| ----- | ----- | 
| `main.py` | Core voice assistant, wake-word loop, AI routing (Ollama + Gemini + backup), Spotify automation, and cancellable task helpers | 
| `server.py` | Flask backend serving the web HUD and REST endpoints on `127.0.0.1:5000` | 
| `index.html` | Dark glassmorphic J.A.R.V.I.S. web interface with mic input, AI engine toggle, and Stop Task controls | 
| `musiclibrary.py` | Dictionary mapping custom song names to direct YouTube links | 
| `client.py` | Minimal test script calling `main.aiprocess(...)` directly | 
| `.env.example` | Template for API keys, AI provider mode, and Ollama model settings | 
| `requirements.txt` | Python package dependencies | 
| `dockerfile` | Container configuration for the project | 

## Quick Start (Windows)

### 1. Install Python Dependencies

Open PowerShell inside your project folder and install the required packages:

```
pip install -r requirements.txt

```

> **Note:** `main.py` also includes an automatic `PyAudio` install fallback if `pyaudio` is missing on first launch.

### 2. Configure `.env`

Copy `.env.example` to `.env` and fill in your settings:

```
GEMINI_API_KEY=put_your_gemini_api_key_here
OLLAMA_MODEL=llama3.2:3b
AI_PROVIDER=auto

```

### 3. Install Ollama & Pull a Local Model (Recommended)

Install [Ollama for Windows](https://ollama.com/download/windows) and download [Llama 3.2 3B](https://ollama.com/library/llama3.2) (\~2 GB, well suited for 16 GB RAM laptops):

```
# Install Ollama (no admin rights required)
irm https://ollama.com/install.ps1 | iex

# Refresh PATH in the current terminal and pull the default model
$env:Path += ";$env:LOCALAPPDATA\Programs\Ollama"
ollama pull llama3.2:3b

```

If PowerShell blocks `irm`, install via WinGet ([winstall](https://winstall.app/apps/Ollama.Ollama)) instead:

```
winget install --id Ollama.Ollama

```

### 4. Run J.A.R.V.I.S.

* **Web HUD (recommended):**

  ```
  python server.py
  
  ```

  Opens automatically at `http://127.0.0.1:5000`.

* **Voice-Only Terminal Mode:**

  ```
  python main.py
  
  ```

  Say `"Jarvis"` to wake the assistant, then speak your command.

## Supported Commands

| Category | Example Commands | Behavior |
| :--- | :--- | :--- |
| **AI Engine** | `"use ollama"`, `"use gemini"`, `"use auto"` | Switches active AI routing mode on the fly |
| **Spotify** | `"open spotify"`, `"play blinding lights on spotify"` | Launches Windows Spotify app, searches, and plays the top result |
| **Music & YouTube** | `"play lip shade"`, `"play [song name]"`, `"stop music"`, `"pause spotify"` | Plays from `musiclibrary.py` or YouTube; pauses/stops playback |
| **Websites** | `"open google"`, `"open youtube"`, `"open github"`, `"open gmail"`, `"open whatsapp"`, `"open instagram"`, `"open reddit"`, `"open facebook"`, `"open twitter"` | Opens the site in your default browser |
| **Date, Time & Weather** | `"what time is it"`, `"what is today's date"`, `"how is the weather today"` | Returns local time/date or live weather data |
| **General AI** | Any other question or prompt | Answered by Ollama and/or Gemini based on `AI_PROVIDER` |
| **Control** | `"stop"`, `"exit"`, `"quit"`, `"shut down"`, `"thank you"` | Shuts down voice mode (or cancels tasks via Web HUD Stop / `Esc`) |

## Environment Variables

| Variable | Default | Description |
| :--- | :--- | :--- |
| `AI_PROVIDER` | `auto` | `auto` (prefers local Ollama when running, falls back to Gemini), `ollama` (local only), or `gemini` (cloud only) |
| `OLLAMA_MODEL` | `llama3.2:3b` | Preferred local Ollama model name (auto-detects installed models if different) |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Local Ollama API endpoint |
| `GEMINI_API_KEY` | *(none)* | Google Gemini API key (also accepts `GOOGLE_API_KEY`) |
| `GEMINI_MODEL` | *(auto)* | Optional override for the Gemini model name |

## Web HUD API Endpoints

| Method & Route | Purpose |
| :--- | :--- |
| `GET /` | Serves the `index.html` J.A.R.V.I.S. HUD |
| `GET /api/health` | Returns server status, active task label, AI provider, and Ollama readiness |
| `POST /api/provider` | Switches AI provider (`{"provider": "auto" \| "ollama" \| "gemini"}`) |
| `POST /api/command` | Executes a Jarvis command (`{"text": "..."}`) and returns replies |
| `POST /api/stop` | Immediately cancels any currently running task, AI call, or automation wait |
| `POST /api/listen` | Records one spoken phrase from the host microphone and returns recognized text |

## Troubleshooting

* **`ModuleNotFoundError: No module named 'pyaudio'`:** Run `pip install PyAudio` in the active Python environment, or use Python 3.11/3.12 where prebuilt Windows wheels are available.

* **Ollama shows offline in the Web HUD:** Confirm Ollama is running in the Windows system tray (`http://127.0.0.1:11434`) and that you have pulled at least one model (`ollama pull llama3.2:3b`).

* **Spotify opens but doesn't start playing:** Keep the Spotify window focused briefly while Jarvis sends the quick-search shortcut, and make sure you are signed in to the desktop app.