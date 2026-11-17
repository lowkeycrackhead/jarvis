  # JARVIS Voice Assistant

A Windows desktop voice assistant built with Python and Google Gemini. JARVIS listens for its wake word, accepts spoken commands, replies aloud, opens frequently used websites, plays music on YouTube, and answers general questions through Gemini.

## Features

- Wake-word interaction: say **"Jarvis"**, then say your command.
- Speech recognition through your microphone.
- Natural spoken responses with Google Text-to-Speech.
- Gemini-powered general questions and conversation.
- Quick commands for Google, YouTube, Gmail, GitHub, WhatsApp, Instagram, Reddit, and other websites.
- YouTube music playback.
- Current time, date, and day responses.
- Optional browser control panel via `server.py`.

## Requirements

- Windows 10 or 11
- Python 3.10 or newer
- A working microphone and speakers
- Internet access
- A Gemini API key from [Google AI Studio](https://aistudio.google.com/app/apikey)

## Installation

Clone the repository and enter its folder:

```powershell
git clone https://github.com/YOUR-USERNAME/jarvis.git
cd jarvis
```

Create and activate a virtual environment (recommended):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install the dependencies:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install python-dotenv
```

> `python-dotenv` is required because JARVIS reads the Gemini key from a local `.env` file.

## Configure Gemini

Create a file named `.env` in the project folder:

```env
GEMINI_API_KEY=your_gemini_api_key_here
```

Use the complete API key exactly as provided by Google AI Studio. Do not add spaces, quote marks, or your key to source code.

## Run JARVIS

```powershell
python main.py
```

Say **"Jarvis"**, wait for the acknowledgement, and then speak your command.

To close the assistant, say **"stop"**, **"exit"**, or **"quit"**.

## Example Commands

- "Jarvis, open YouTube"
- "Jarvis, open GitHub"
- "Jarvis, play Blinding Lights"
- "Jarvis, what time is it?"
- "Jarvis, what is artificial intelligence?"
- "Jarvis, stop"

## Optional Web Control Panel

The project also includes a small local browser interface:

```powershell
python -m pip install flask
python server.py
```

Open `http://127.0.0.1:5000` if the browser does not open automatically.

## Troubleshooting

### Gemini 401 authentication error

Confirm that `.env` is in the same folder as `main.py`, that `GEMINI_API_KEY` contains the complete active key, and that the project dependencies are up to date:

```powershell
python -m pip install --upgrade google-genai python-dotenv
```

If a valid key still returns `401 UNAUTHENTICATED`, the key or its Google AI Studio project is being rejected by Google. Recheck the key status and project in AI Studio; this is not caused by a voice command.

### PyAudio installation issue

PyAudio may require additional Windows build support on some machines. Install a compatible PyAudio wheel for your Python version, then rerun:

```powershell
python -m pip install -r requirements.txt
```

## Security

Your Gemini key is a password. Never commit it to GitHub. Create a `.gitignore` file containing at least:

```gitignore
.env
.venv/
__pycache__/
*.mp3
```

## Project Structure

```text
├── main.py            # Voice-assistant application
├── server.py          # Optional local web control panel
├── index.html         # Browser interface for server.py
├── client.py          # Basic Gemini client test
├── requirements.txt   # Python dependencies
├── dockerfile         # Container build instructions
└── README.md          # Project documentation
```

## License

This project is provided for personal and educational use.
