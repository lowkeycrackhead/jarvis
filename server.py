"""
server.py - web backend for Jarvis.

Put this file and index.html in the SAME folder as your main.py, then run:
    python server.py
Your browser opens at http://127.0.0.1:5000

- /api/command  runs your existing commands (processcommand in main.py)
- /api/listen   records one phrase from this computer's microphone and returns
                the text (same method your original main.py used). The page
                switches to this automatically when the browser's own speech
                recognition can't reach Google.
"""
import os
import threading
import webbrowser

import speech_recognition as sr
from flask import Flask, jsonify, request, send_from_directory

import main  # your existing assistant code

BASE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)

lock = threading.Lock()        # run one command at a time
replies = []                   # replies collected during the current command

recognizer = sr.Recognizer()
mic_lock = threading.Lock()    # only one recording at a time
calibrated = False


def capture_speak(text):
    """Replaces main.speak: instead of playing audio, hand the text to the page."""
    replies.append(str(text))


main.speak = capture_speak  # processcommand() looks this up at call time


@app.get("/")
def index():
    return send_from_directory(BASE, "index.html")


@app.get("/api/health")
def health():
    return jsonify(ok=True)


@app.post("/api/command")
def command():
    text = (request.get_json(silent=True) or {}).get("text", "").strip()
    if not text:
        return jsonify(replies=[], shutdown=False)

    with lock:
        replies.clear()
        shutdown = False
        low = text.lower()
        try:
            if "thank you" in low or "thanks" in low:
                replies.append("You are welcome, Sir.")
            else:
                shutdown = bool(main.processcommand(text))
        except Exception as error:
            return jsonify(error=str(error)), 500
        # Commands like "open google" are silent, so confirm them
        out = list(replies) or ["Done, Sir."]

    return jsonify(replies=out, shutdown=shutdown)


@app.post("/api/listen")
def listen():
    """Record one phrase from the computer's microphone and return the text."""
    global calibrated
    if not mic_lock.acquire(blocking=False):
        return jsonify(text="")
    try:
        with sr.Microphone() as source:
            if not calibrated:
                recognizer.adjust_for_ambient_noise(source, duration=0.6)
                calibrated = True
            audio = recognizer.listen(source, timeout=4, phrase_time_limit=8)
        return jsonify(text=recognizer.recognize_google(audio))
    except (sr.WaitTimeoutError, sr.UnknownValueError):
        return jsonify(text="")          # silence or unclear speech: just try again
    except sr.RequestError as error:
        return jsonify(error=f"Google speech service unreachable: {error}"), 502
    except Exception as error:
        return jsonify(error=f"Microphone error: {error}"), 500
    finally:
        mic_lock.release()


if __name__ == "__main__":
    threading.Timer(1.2, lambda: webbrowser.open("http://127.0.0.1:5000")).start()
    app.run(host="127.0.0.1", port=5000, threaded=True)
