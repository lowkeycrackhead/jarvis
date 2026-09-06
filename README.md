# Jarvis Voice Assistant

A Python voice assistant powered by Google Gemini. Jarvis listens for the wake word **“Jarvis”**, accepts voice commands, speaks responses, opens common websites, plays YouTube music, and handles general questions through Gemini.

## Features

- Voice recognition using your microphone
- Text-to-speech responses
- Gemini-powered conversational responses
- Open Google, YouTube, GitHub, Gmail, Instagram, WhatsApp, Reddit, and more
- Play songs on YouTube using voice commands
- Simple wake-word flow: say **“Jarvis”**, then speak your command

## Requirements

- Python 3.12 or later
- A microphone and speakers
- A Gemini API key from Google AI Studio
- Internet connection

## Installation

Clone the repository:

```powershell
git clone https://github.com/YOUR-USERNAMElowkeycrackhead/jarvis.git
cd YOUR-REPOSITORY
```

Install all required Python packages with one command:

```powershell
python -m pip install -r requirements.txt
```

## Configure the Gemini API Key

Before running Jarvis, set your Gemini API key in PowerShell:

```powershell
$env:GEMINI_API_KEY="paste_your_gemini_api_key_here"
```

Keep this PowerShell window open while running the app.

> Never commit or share your Gemini API key.

## Run Jarvis

```powershell
python main.py
```

Say **“Jarvis”**, wait for the response, then speak your command.

To close Jarvis, say **“thank you”** or **“thanks.”**

## Example Commands

- “Jarvis, open YouTube”
- “Jarvis, open Google”
- “Jarvis, play Blinding Lights”
- “Jarvis, what is artificial intelligence?”
- “Jarvis, open GitHub”

## Docker Support

Docker installs the Python dependencies automatically inside a container.

Build the image:

```powershell
docker build -t jarvis .
```

Create a `.env` file containing:

```text
GEMINI_API_KEY=paste_your_gemini_api_key_here
```

Test the Gemini client:

```powershell
docker run --rm --env-file .env jarvis python client.py
```

### Important Docker Limitation

The full `main.py` voice assistant should be run directly on Windows with Python. Docker Desktop does not reliably provide access to your microphone, speakers, or browser automation on Windows.

Use Docker for dependency testing and `client.py`; use `python main.py` for the complete voice assistant.

## Project Structure

```text
├── main.py              # Main voice assistant
├── client.py            # Gemini test client
├── requirements.txt     # Python dependencies
├── Dockerfile           # Docker build instructions
├── .dockerignore        # Files excluded from Docker builds
├── .gitignore           # Files excluded from GitHub
└── README.md            # Project documentation
```

## Security

Do not upload any file containing your Gemini API key. Add `.env` to `.gitignore` before publishing changes.

## License

This project is intended for personal and educational use.
