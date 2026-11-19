# pyright: reportMissingImports=false, reportMissingModuleSource=false, reportOptionalMemberAccess=false, reportAttributeAccessIssue=false, reportGeneralTypeIssues=false
"""
server.py - Aesthetic web backend for Jarvis with live task cancellation and Ollama/Gemini switching.

Run:
    python server.py
Your browser opens at http://127.0.0.1:5000

Endpoints:
- /api/health    check server status, active task, and Ollama/Gemini status
- /api/provider  switch AI engine between auto, ollama, and gemini
- /api/command   execute a Jarvis command (cancellable via /api/stop)
- /api/stop      immediately cancel any running task or AI response
- /api/listen    record one phrase from this computer's microphone
"""
import os
import threading
import webbrowser

import speech_recognition as sr
from flask import Flask, jsonify, request, send_from_directory

import main  # your existing assistant code

BASE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)

lock = threading.Lock()
replies: list[str] = []
active_task = {"running": False, "label": ""}

recognizer = sr.Recognizer()
mic_lock = threading.Lock()
calibrated = False


def capture_speak(text):
    """Replaces main.speak: instead of playing local audio, hand the text to the web UI."""
    if not main.is_cancelled():
        replies.append(str(text))


main.speak = capture_speak  # processcommand() looks this up at call time


@app.get("/")
def index():
    return send_from_directory(BASE, "index.html")


@app.get("/api/health")
def health():
    ai = main.get_ai_status()
    return jsonify(
        ok=True,
        busy=active_task["running"],
        task=active_task["label"],
        provider=ai["provider"],
        ollama_model=ai["ollama_model"],
        ollama_ready=ai["ollama_ready"],
    )


@app.post("/api/provider")
def set_provider():
    mode = (request.get_json(silent=True) or {}).get("provider", "auto")
    updated = main.set_ai_provider(mode)
    ai = main.get_ai_status()
    return jsonify(provider=updated, ollama_model=ai["ollama_model"], ollama_ready=ai["ollama_ready"])


@app.post("/api/stop")
def stop_task():
    """Cancel any currently running command, AI call, or Spotify/automation wait."""
    main.cancel_current_task()
    return jsonify(stopped=True, message="Task cancelled, Sir.")


@app.post("/api/command")
def command():
    text = (request.get_json(silent=True) or {}).get("text", "").strip()
    if not text:
        return jsonify(replies=[], shutdown=False, cancelled=False)

    with lock:
        replies.clear()
        main.clear_cancel()
        active_task["running"] = True
        active_task["label"] = text
        shutdown = False
        cancelled = False
        low = text.lower()
        try:
            if low in {"thank you", "thanks", "thank you jarvis", "thanks jarvis"}:
                replies.append("You are welcome, Sir.")
            else:
                shutdown = bool(main.processcommand(text))
            cancelled = bool(main.is_cancelled())
        except Exception as error:
            return jsonify(error=str(error)), 500
        finally:
            active_task["running"] = False
            active_task["label"] = ""

        if cancelled:
            out = ["Task cancelled, Sir."]
        else:
            out = list(replies) or ["Done, Sir."]

    return jsonify(replies=out, shutdown=shutdown, cancelled=cancelled)


@app.post("/api/listen")
def listen():
    """Record one phrase from the computer's microphone and return the text."""
    global calibrated
    if not mic_lock.acquire(blocking=False):
        return jsonify(text="")
    try:
        with sr.Microphone() as source:
            if not calibrated:
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                calibrated = True
            audio = recognizer.listen(source, timeout=4, phrase_time_limit=8)
        return jsonify(text=recognizer.recognize_google(audio))
    except (sr.WaitTimeoutError, sr.UnknownValueError):
        return jsonify(text="")
    except sr.RequestError as error:
        return jsonify(error=f"Google speech service unreachable: {error}"), 502
    except Exception as error:
        return jsonify(error=f"Microphone error: {error}"), 500
    finally:
        mic_lock.release()


if __name__ == "__main__":
    threading.Timer(1.2, lambda: webbrowser.open("http://127.0.0.1:5000")).start()
    app.run(host="127.0.0.1", port=5000, threaded=True)
