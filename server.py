# pyright: reportMissingImports=false, reportMissingModuleSource=false, reportOptionalMemberAccess=false, reportAttributeAccessIssue=false, reportGeneralTypeIssues=false
"""
server.py - Interactive web backend for J.A.R.V.I.S. with SSE live token streaming,
live task cancellation, Ollama/Gemini switching, Personas, PC telemetry & controls,
Screen Vision, Clipboard actions, and persistent Notes & Timers.

Run:
    python server.py
Your browser opens at http://127.0.0.1:5000
"""
from __future__ import annotations
import base64
import json
import os
import re
import threading
import urllib.parse
import webbrowser

try:
    import speech_recognition as sr
except Exception:
    sr = None
from flask import Flask, Response, jsonify, request, send_from_directory, stream_with_context

import jarvis_extras as extras
import main  # your existing assistant code

BASE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)

lock = threading.Lock()
replies: list[str] = []
active_task = {"running": False, "label": ""}

recognizer = sr.Recognizer() if sr is not None else None
mic_lock = threading.Lock()
calibrated = False


def capture_speak(text):
    """Replaces main.speak: instead of playing local audio, hand the text to the web UI."""
    if not main.is_cancelled():
        replies.append(str(text))


main.speak = capture_speak  # processcommand() looks this up at call time


def _is_direct_action_command(text: str) -> bool:
    """Return True if the command should run through processcommand() rather than raw AI streaming."""
    raw = re.sub(
        r"^(?:hey\s+|ok\s+|hi\s+|hello\s+)?(?:jarvis|jarvas|jervis|jarves|charvis|jarvice)\b[\s,.!?:;-]*",
        "",
        str(text).strip(),
        flags=re.IGNORECASE,
    ).strip() or str(text).strip()
    low = raw.lower().strip()
    exact = {
        "stop", "exit", "quit", "shutdown", "shut down",
        "thank you", "thanks", "thank you jarvis", "thanks jarvis",
        "use ollama", "switch to ollama", "ollama mode",
        "use gemini", "switch to gemini", "gemini mode",
        "use auto", "auto ai", "auto mode",
        "coder mode", "coding mode", "switch to coder", "be a coder",
        "tutor mode", "study mode", "switch to tutor", "study tutor",
        "butler mode", "jarvis mode", "normal mode", "default mode",
        "clear memory", "forget conversation", "reset memory",
        "read my notes", "show my notes", "list notes", "my notes",
        "lock screen", "lock my pc", "lock computer", "lock laptop",
        "mute", "mute volume", "unmute", "unmute volume",
    }
    if low in exact:
        return True
    if main.is_datetime_query(low):
        return True
    if main._extract_spotify_song(raw) is not None:
        return True
    prefixes = ("open ", "launch ", "start ", "close ", "play ", "note down ", "take a note ", "add note ", "add a note ", "remember that ")
    if low.startswith(prefixes) or low == "play":
        return True
    keywords = (
        "stop the song", "stop music", "stop the music", "pause the song", "pause music",
        "stop spotify", "pause spotify", "on my screen", "look at my screen", "read my screen",
        "explain my screen", "see my screen", "analyze my screen",
        "clipboard", "what did i copy", "what i copied",
        "timer", "screenshot", "capture screen",
        "battery", "system status", "pc status", "cpu usage", "ram usage",
        "volume", "brightness",
    )
    return any(k in low for k in keywords)


@app.get("/")
@app.get("/index.html")
@app.get("/server.py")
def index():
    for folder in (BASE, os.getcwd(), os.path.join(BASE, "mega-project--jarvis"), os.path.join(os.getcwd(), "mega-project--jarvis")):
        candidate = os.path.join(folder, "index.html")
        if os.path.isfile(candidate):
            with open(candidate, "r", encoding="utf-8") as fh:
                return Response(fh.read(), mimetype="text/html")
    return Response("index.html not found in deployment bundle.", status=404)


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
        persona=ai.get("persona", "butler"),
        cloud=bool(getattr(main, "IS_CLOUD", False)),
        supabase_ready=extras.is_supabase_connected(),
        gemini_configured=bool(main._get_api_key()),
        gemini_error=main.get_gemini_last_error(),
    )


@app.post("/api/provider")
def set_provider():
    mode = (request.get_json(silent=True) or {}).get("provider", "auto")
    updated = main.set_ai_provider(mode)
    ai = main.get_ai_status()
    return jsonify(
        provider=updated,
        ollama_model=ai["ollama_model"],
        ollama_ready=ai["ollama_ready"],
        persona=ai.get("persona", "butler"),
    )


@app.post("/api/persona")
def set_persona():
    mode = (request.get_json(silent=True) or {}).get("persona", "butler")
    updated = main.set_persona(mode)
    return jsonify(persona=updated, name=extras.PERSONAS[updated]["name"])


@app.post("/api/memory/clear")
def clear_memory():
    main.clear_memory()
    return jsonify(cleared=True)


@app.post("/api/stop")
def stop_task():
    """Cancel any currently running command, AI stream, or automation wait."""
    main.cancel_current_task()
    return jsonify(stopped=True, message="Task cancelled, Sir.")


@app.get("/api/history")
def get_history():
    return jsonify(messages=extras.list_messages(24), supabase_ready=extras.is_supabase_connected())


def _cloud_web_url(text: str) -> tuple[str | None, str | None]:
    """For Vercel cloud mode, return (reply, url_to_open) for web-open commands."""
    low = text.lower().strip()
    sites = {
        "open spotify": ("Launching Spotify app, Sir.", "spotify:"),
        "open youtube": ("Opening YouTube, Sir.", "https://youtube.com"),
        "open yt": ("Opening YouTube, Sir.", "https://youtube.com"),
        "open google": ("Opening Google, Sir.", "https://google.com"),
        "open github": ("Opening GitHub, Sir.", "https://github.com"),
        "open gmail": ("Opening Gmail, Sir.", "https://mail.google.com"),
        "open whatsapp": ("Opening WhatsApp Web, Sir.", "https://web.whatsapp.com"),
        "open instagram": ("Opening Instagram, Sir.", "https://instagram.com"),
        "open insta": ("Opening Instagram, Sir.", "https://instagram.com"),
        "open facebook": ("Opening Facebook, Sir.", "https://facebook.com"),
        "open fb": ("Opening Facebook, Sir.", "https://facebook.com"),
        "open reddit": ("Opening Reddit, Sir.", "https://reddit.com"),
        "open twitter": ("Opening X, Sir.", "https://twitter.com"),
        "open x": ("Opening X, Sir.", "https://twitter.com"),
        "open linkedin": ("Opening LinkedIn, Sir.", "https://linkedin.com"),
        "open netflix": ("Opening Netflix, Sir.", "https://netflix.com"),
        "open amazon": ("Opening Amazon, Sir.", "https://amazon.in"),
    }
    for k, pair in sites.items():
        if k in low:
            return pair
    if low.startswith("play "):
        song = text[5:].strip()
        if "spotify" in low:
            q = re.sub(r"\s+(?:in|on)\s+spotify$", "", song, flags=re.IGNORECASE).strip()
            return (f"Searching {q} in Spotify app, Sir.", f"spotify:search:{urllib.parse.quote(q)}")
        return (f"Opening {song} on YouTube, Sir.", f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(song)}")
    return None, None




@app.post("/api/transcribe")
def transcribe_audio():
    """Transcribe a browser-recorded audio clip (for Brave/Firefox/Safari where Web Speech API is unavailable)."""
    data = request.get_json(silent=True) or {}
    raw = str(data.get("audio") or "")
    mime = str(data.get("mime") or "audio/webm").split(";")[0].strip() or "audio/webm"
    if "," in raw:
        hdr, raw = raw.split(",", 1)
        if hdr.startswith("data:") and ";" in hdr:
            mime = hdr[5:].split(";", 1)[0] or mime
    if not raw:
        return jsonify(error="No audio received."), 400
    try:
        audio_bytes = base64.b64decode(raw)
    except Exception:
        return jsonify(error="Invalid audio payload."), 400

    api_key = main._get_api_key()
    if api_key and getattr(main, "genai", None) is not None and getattr(main, "types", None) is not None:
        for model_name in ("gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.0-flash"):
            try:
                client = main.genai.Client(api_key=api_key)
                part = main.types.Part.from_bytes(data=audio_bytes, mime_type=mime)
                resp = client.models.generate_content(
                    model=model_name,
                    contents=[part, "Transcribe this short spoken voice command verbatim. Output ONLY the exact spoken words with no quotes or extra text. If silent or unintelligible, return empty string."],
                )
                txt = (getattr(resp, "text", None) or "").strip().strip('"').strip("'")
                return jsonify(text=txt)
            except Exception as err:
                print(f"Transcribe warning ({model_name}): {err}")
    return jsonify(error="Voice transcription requires GEMINI_API_KEY in Vercel Environment Variables."), 503


@app.post("/api/vision")
def vision_endpoint():
    """Analyze a browser-captured screen snapshot (base64 JPEG) via Gemini Vision or local Ollama."""
    data = request.get_json(silent=True) or {}
    img_data = str(data.get("image") or "")
    question = str(data.get("question") or "Briefly describe what is on my screen and help if there is an error or question.").strip()
    if "," in img_data:
        img_data = img_data.split(",", 1)[1]
    if not img_data:
        return jsonify(error="No screen image received."), 400
    try:
        jpeg_bytes = base64.b64decode(img_data)
    except Exception:
        return jsonify(error="Invalid image data."), 400

    api_key = main._get_api_key()
    reply = ""
    if api_key and getattr(main, "genai", None) is not None and getattr(main, "types", None) is not None:
        for model_name in ("gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash"):
            try:
                client = main.genai.Client(api_key=api_key)
                part = main.types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg")
                resp = client.models.generate_content(
                    model=model_name,
                    contents=[part, f"{extras.get_system_instruction()}\n\nUser asks about their screen: {question}"],
                )
                txt = (getattr(resp, "text", None) or "").strip()
                if txt:
                    reply = txt
                    break
            except Exception as err:
                print(f"Cloud vision warning ({model_name}): {err}")

    if not reply:
        reply = (
            "I captured your screen, Sir, but Gemini Vision couldn't respond. "
            "Check that GEMINI_API_KEY is set in your Vercel Environment Variables."
        )

    extras.save_message("user", f"[Screen Vision] {question}", extras.get_persona())
    extras.save_message("assistant", reply, extras.get_persona())
    return jsonify(reply=reply)


@app.post("/api/stream")
def stream_command():
    """Stream AI replies word-by-word via Server-Sent Events (SSE), or run direct actions."""
    body = request.get_json(silent=True) or {}
    text = str(body.get("text", "")).strip()
    tz_name = body.get("tz") or None
    tz_offset = body.get("tz_offset")
    main.set_request_city(request.headers.get("x-vercel-ip-city", ""))
    if not text:
        return jsonify(error="Empty command"), 400

    def generate():
        with lock:
            replies.clear()
            main.clear_cancel()
            active_task["running"] = True
            active_task["label"] = text
            shutdown = False
            full_parts: list[str] = []
            try:
                low = text.lower()
                if low in {"thank you", "thanks", "thank you jarvis", "thanks jarvis"}:
                    msg = "You are welcome, Sir."
                    shutdown = True
                    full_parts.append(msg)
                    yield f"data: {json.dumps({'token': msg})}\n\n"
                elif getattr(main, "IS_CLOUD", False) and _cloud_web_url(text)[1]:
                    c_reply, c_url = _cloud_web_url(text)
                    full_parts.append(c_reply or "Opening, Sir.")
                    yield f"data: {json.dumps({'token': c_reply, 'open_url': c_url})}\n\n"
                elif _is_direct_action_command(text):
                    shutdown = bool(main.processcommand(text, tz_name=tz_name, tz_offset_min=tz_offset))
                    if not main.is_cancelled():
                        out = list(replies) or ["Done, Sir."]
                        joined = "\n".join(out)
                        full_parts.append(joined)
                        yield f"data: {json.dumps({'token': joined})}\n\n"
                else:
                    for token in main.stream_ai_reply(text):
                        if main.is_cancelled():
                            break
                        full_parts.append(token)
                        yield f"data: {json.dumps({'token': token})}\n\n"
            except Exception as err:
                yield f"data: {json.dumps({'error': str(err)})}\n\n"
            finally:
                cancelled = bool(main.is_cancelled())
                active_task["running"] = False
                active_task["label"] = ""
            final_txt = "".join(full_parts).strip()
            if final_txt and not cancelled:
                extras.save_message("user", text, extras.get_persona())
                extras.save_message("assistant", final_txt, extras.get_persona())
            yield f"data: {json.dumps({'done': True, 'full': final_txt, 'shutdown': shutdown, 'cancelled': cancelled})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/command")
def command():
    body = request.get_json(silent=True) or {}
    text = str(body.get("text", "")).strip()
    tz_name = body.get("tz") or None
    tz_offset = body.get("tz_offset")
    main.set_request_city(request.headers.get("x-vercel-ip-city", ""))
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
                shutdown = True
            else:
                shutdown = bool(main.processcommand(text, tz_name=tz_name, tz_offset_min=tz_offset))
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
    if sr is None or recognizer is None:
        return jsonify(error="Server microphone is only available when running locally on Windows. Switch to Mic: browser."), 400
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


# --- Live PC Telemetry & Controls ---
@app.get("/api/system")
def system_stats():
    st = extras.get_system_stats()
    st["notes"] = extras.list_notes()
    st["timers"] = extras.list_timers()
    return jsonify(st)


@app.post("/api/system/volume")
def system_volume():
    data = request.get_json(silent=True) or {}
    if "level" in data:
        ok = extras.set_volume(int(data["level"]))
        return jsonify(ok=ok, level=int(data["level"]))
    action = str(data.get("action", "")).lower()
    if action in {"up", "down", "mute"}:
        extras.adjust_volume(action, 4)
        return jsonify(ok=True, action=action)
    return jsonify(error="Provide level (0-100) or action (up/down/mute)"), 400


@app.post("/api/system/brightness")
def system_brightness():
    data = request.get_json(silent=True) or {}
    if "level" not in data:
        return jsonify(error="Provide level (0-100)"), 400
    lvl = max(0, min(100, int(data["level"])))
    ok = extras.set_brightness(lvl)
    return jsonify(ok=ok, level=lvl)


@app.post("/api/system/action")
def system_action():
    data = request.get_json(silent=True) or {}
    act = str(data.get("action", "")).lower()
    if act == "screenshot":
        path, _ = extras.capture_screenshot(save=True)
        return jsonify(ok=bool(path), message="Screenshot saved, Sir." if path else "Install Pillow for screenshots.")
    if act == "lock":
        ok = extras.lock_screen()
        return jsonify(ok=ok, message="Locking screen, Sir.")
    if act == "launch":
        app_name = str(data.get("app", ""))
        opened = extras.launch_app(app_name)
        return jsonify(ok=bool(opened), message=f"Opening {opened}, Sir." if opened else f"Unknown app: {app_name}")
    return jsonify(error="Unsupported action"), 400


# --- Persistent Quick Notes ---
@app.get("/api/notes")
def get_notes():
    return jsonify(notes=extras.list_notes())


@app.post("/api/notes")
def create_note():
    text = (request.get_json(silent=True) or {}).get("text", "").strip()
    if not text:
        return jsonify(error="Empty note"), 400
    note = extras.add_note(text)
    return jsonify(note=note, notes=extras.list_notes())


@app.delete("/api/notes/<note_id>")
def remove_note(note_id: str):
    extras.delete_note(note_id)
    return jsonify(notes=extras.list_notes())


# --- Live Countdown Timers ---
@app.get("/api/timers")
def get_timers():
    return jsonify(timers=extras.list_timers())


@app.post("/api/timers")
def create_timer():
    data = request.get_json(silent=True) or {}
    seconds = int(data.get("seconds", 300))
    label = str(data.get("label", "Focus Timer")).strip() or "Focus Timer"
    timer = extras.add_timer(label, seconds)
    return jsonify(timer=timer, timers=extras.list_timers())


@app.delete("/api/timers/<timer_id>")
def remove_timer(timer_id: str):
    extras.cancel_timer(timer_id)
    return jsonify(timers=extras.list_timers())


if __name__ == "__main__":
    threading.Timer(1.2, lambda: webbrowser.open("http://127.0.0.1:5000")).start()
    app.run(host="127.0.0.1", port=5000, threaded=True)
