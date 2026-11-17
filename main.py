import json
import os
import re
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime

import speech_recognition as sr
from google import genai
from google.genai import types
from gtts import gTTS

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

try:
    from pygame import mixer
except Exception:
    mixer = None

try:
    import pyautogui
except Exception:
    pyautogui = None

try:
    import pywhatkit
except Exception:
    pywhatkit = None

try:
    import musiclibrary
except Exception:
    musiclibrary = None

# Always resolve .env from the directory containing main.py (or its parent folder)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_env_files():
    """Load .env from current script directory or parent directory, with built-in parser fallback."""
    candidate_paths = [
        os.path.join(BASE_DIR, ".env"),
        os.path.join(os.path.dirname(BASE_DIR), ".env"),
    ]
    for env_path in candidate_paths:
        if os.path.isfile(env_path):
            if load_dotenv is not None:
                try:
                    load_dotenv(env_path, override=True)
                except Exception:
                    pass
            try:
                with open(env_path, "r", encoding="utf-8", errors="ignore") as f:
                    for raw_line in f:
                        line = raw_line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if k and v:
                            os.environ[k] = v
            except Exception:
                pass


_load_env_files()

SYSTEM_INSTRUCTION = (
    "You are Jarvis, a concise and helpful voice assistant. "
    "Address the user as Sir. "
    "Give short and crisp responses in plain text without markdown asterisks or bullet symbols, "
    "and avoid unnecessary explanations."
)

# Prioritized Gemini Flash models across 2026 & 2.5 families
CANDIDATE_MODELS = [
    m
    for m in [
        os.getenv("GEMINI_MODEL", "").strip(),
        "gemini-3.6-flash",
        "gemini-3.7-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.8-flash",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.0-flash",
    ]
    if m
]
CANDIDATE_MODELS = list(dict.fromkeys(CANDIDATE_MODELS))

WAKE_WORD_PATTERN = re.compile(
    r"\b(jarvis|jarvas|jervis|jarves|charvis|jarvice|gervais|jarvi)\b",
    re.IGNORECASE,
)

music_playing = False
recognizer = sr.Recognizer()
_mixer_initialized = False
_ai_lock = threading.Lock()
_active_chat = None
_active_client = None
_active_model = None
_conversation_history = []


def _ensure_mixer():
    """Initialize pygame mixer safely on demand without crashing headless/server environments."""
    global _mixer_initialized
    if _mixer_initialized or mixer is None:
        return _mixer_initialized
    try:
        mixer.init()
        _mixer_initialized = True
    except Exception as error:
        print(f"Audio mixer warning: {error}")
        _mixer_initialized = False
    return _mixer_initialized


_ensure_mixer()


def _get_api_key():
    """Retrieve and sanitize the Gemini API key from .env or environment variables."""
    _load_env_files()
    raw_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
    clean_key = raw_key.strip().strip('"').strip("'")
    if clean_key:
        os.environ["GEMINI_API_KEY"] = clean_key
    return clean_key


def _build_clients(api_key):
    """
    Build candidate google-genai clients:
    1. Standard Gemini Developer API client (generativelanguage.googleapis.com)
    2. Vertex AI / Agent Platform Express client (aiplatform.googleapis.com) for AQ.-prefixed keys
    """
    if not api_key:
        return []

    # Clear conflicting env vars that cause 401 OVERLOADED_CREDENTIALS in google-genai
    os.environ.pop("GOOGLE_API_KEY", None)
    os.environ.pop("GOOGLE_GENAI_USE_VERTEXAI", None)

    clients = []
    for use_vertex in (False, True):
        try:
            if use_vertex:
                clients.append(("vertexai", genai.Client(vertexai=True, api_key=api_key)))
            else:
                clients.append(("gemini_api", genai.Client(api_key=api_key)))
        except Exception:
            continue
    return clients


def _clean_text_for_speech(text):
    """Strip Markdown symbols so gTTS reads natural sentences instead of saying 'asterisk'."""
    if not text:
        return ""
    cleaned = re.sub(r"```[\s\S]*?```", " ", str(text))
    cleaned = re.sub(r"`([^`]*)`", r"\1", cleaned)
    cleaned = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", cleaned)
    cleaned = re.sub(r"[*_#~>|]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def speak(text):
    """Convert text to speech and play it aloud."""
    clean_text = _clean_text_for_speech(text)
    if not clean_text:
        return

    if not _ensure_mixer():
        print(f"Jarvis: {clean_text}")
        return

    temp_path = None
    try:
        fd, temp_path = tempfile.mkstemp(prefix="jarvis_response_", suffix=".mp3", dir=BASE_DIR)
        os.close(fd)

        tts = gTTS(text=clean_text, lang="en", slow=False)
        tts.save(temp_path)

        mixer.music.load(temp_path)
        mixer.music.play()

        while mixer.music.get_busy():
            time.sleep(0.1)

        try:
            mixer.music.unload()
        except Exception:
            pass
    except Exception as error:
        print(f"TTS error: {error}")
    finally:
        if temp_path and os.path.exists(temp_path):
            for _ in range(3):
                try:
                    os.remove(temp_path)
                    break
                except OSError:
                    time.sleep(0.1)


def _direct_gemini_rest(api_key, prompt):
    """
    Direct REST fallback to Gemini API & Vertex AI Express Mode using x-goog-api-key,
    bypassing any SDK header/version quirks.
    """
    if not api_key:
        return None

    contents = []
    for u_msg, a_msg in _conversation_history[-4:]:
        contents.append({"role": "user", "parts": [{"text": u_msg}]})
        contents.append({"role": "model", "parts": [{"text": a_msg}]})
    contents.append({"role": "user", "parts": [{"text": prompt}]})

    payload = json.dumps(
        {
            "system_instruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
            "contents": contents,
        }
    ).encode("utf-8")

    endpoints = [
        "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        "https://aiplatform.googleapis.com/v1/publishers/google/models/{model}:generateContent",
    ]

    for url_tpl in endpoints:
        for model_name in CANDIDATE_MODELS[:5]:
            url = url_tpl.format(model=model_name)
            req = urllib.request.Request(
                url,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": api_key,
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                    candidates = data.get("candidates") or []
                    if candidates:
                        parts = (candidates[0].get("content") or {}).get("parts") or []
                        text = "".join(p.get("text", "") for p in parts).strip()
                        if text:
                            return text
            except urllib.error.HTTPError as http_err:
                if http_err.code in (401, 403):
                    break
                continue
            except Exception:
                continue
    return None


def _fallback_ai_answer(command):
    """
    Keyless backup AI/knowledge responder used only if all Gemini API endpoints
    reject the key (e.g., 401 UNAUTHENTICATED or 429 quota exceeded) so Jarvis
    never fails to answer a question.
    """
    prompt = str(command).strip()
    if not prompt:
        return "How can I help you, Sir?"

    # 1. OpenAI-compatible keyless POST endpoint (Pollinations)
    try:
        messages = [{"role": "system", "content": SYSTEM_INSTRUCTION}]
        for u_msg, a_msg in _conversation_history[-4:]:
            messages.append({"role": "user", "content": u_msg})
            messages.append({"role": "assistant", "content": a_msg})
        messages.append({"role": "user", "content": prompt})

        body = json.dumps({"model": "openai", "messages": messages}).encode("utf-8")
        req = urllib.request.Request(
            "https://text.pollinations.ai/openai",
            data=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "JarvisVoiceAssistant/1.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            raw = resp.read().decode("utf-8", errors="ignore").strip()
            try:
                parsed = json.loads(raw)
                choices = parsed.get("choices") or []
                if choices:
                    content = ((choices[0].get("message") or {}).get("content") or "").strip()
                    if content:
                        return content
            except Exception:
                if raw and "<!DOCTYPE" not in raw:
                    return raw
    except Exception:
        pass

    # 2. Pollinations GET text fallback
    try:
        full_prompt = f"{SYSTEM_INSTRUCTION}\nUser: {prompt}\nJarvis:"
        encoded = urllib.parse.quote(full_prompt)
        req = urllib.request.Request(
            f"https://text.pollinations.ai/{encoded}",
            headers={"User-Agent": "JarvisVoiceAssistant/1.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            reply = resp.read().decode("utf-8", errors="ignore").strip()
            if reply and "<!DOCTYPE" not in reply:
                return reply
    except Exception:
        pass

    # 3. Wikipedia REST / Search API for factual questions
    try:
        clean_q = re.sub(
            r"^(?:what\s+is|what\s+are|who\s+is|who\s+was|tell\s+me\s+about|explain|define)\s+",
            "",
            prompt,
            flags=re.IGNORECASE,
        ).strip(" ?.!,")
        search_url = (
            "https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch="
            + urllib.parse.quote_plus(clean_q or prompt)
            + "&utf8=&format=json&srlimit=1"
        )
        req = urllib.request.Request(
            search_url, headers={"User-Agent": "JarvisVoiceAssistant/1.0"}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            sdata = json.loads(resp.read().decode("utf-8", errors="ignore"))
            results = ((sdata.get("query") or {}).get("search")) or []
            if results:
                title = results[0].get("title", "")
                sum_url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(title)
                sreq = urllib.request.Request(
                    sum_url, headers={"User-Agent": "JarvisVoiceAssistant/1.0"}
                )
                with urllib.request.urlopen(sreq, timeout=8) as sresp:
                    sum_data = json.loads(sresp.read().decode("utf-8", errors="ignore"))
                    extract = (sum_data.get("extract") or "").strip()
                    if extract:
                        sentences = re.split(r"(?<=[.!?])\s+", extract)
                        short_extract = " ".join(sentences[:2]).strip()
                        return f"{short_extract} Sir."
    except Exception:
        pass

    return None


def generate_ai_reply(command):
    """
    Send the user's question to Gemini and return a clean spoken reply.
    Tries:
      1. Active multi-turn Gemini chat session
      2. Standard Gemini API + Vertex AI Express Mode across candidate Flash models
      3. Direct REST API call with x-goog-api-key header
      4. Backup AI/knowledge responder if the API key is unauthorized or out of quota
    """
    global _active_chat, _active_client, _active_model

    prompt = str(command).strip()
    if not prompt:
        return "Yes, Sir? How may I help you?"

    config = types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION)

    with _ai_lock:
        # 1. Fast path: use verified working chat session
        if _active_chat is not None:
            try:
                response = _active_chat.send_message(prompt)
                reply = (response.text or "").strip()
                if reply:
                    _conversation_history.append((prompt, reply))
                    return reply
            except Exception as error:
                print(f"Resetting active Gemini chat ({_active_model}): {error}")
                _active_chat = None

        # 2. Try google-genai SDK across candidate clients and models
        api_key = _get_api_key()
        last_error = None

        if api_key:
            for mode_name, cand_client in _build_clients(api_key):
                auth_failures_on_gateway = 0
                for model_name in CANDIDATE_MODELS:
                    try:
                        chat_session = cand_client.chats.create(
                            model=model_name,
                            config=config,
                        )
                        response = chat_session.send_message(prompt)
                        reply = (response.text or "").strip()
                        if reply:
                            _active_client = cand_client
                            _active_model = model_name
                            _active_chat = chat_session
                            _conversation_history.append((prompt, reply))
                            return reply
                    except Exception as err:
                        last_error = err
                        err_text = str(err)
                        if "401" in err_text or "UNAUTHENTICATED" in err_text or "403" in err_text:
                            auth_failures_on_gateway += 1
                            if auth_failures_on_gateway >= 2:
                                break
                        continue

            # 3. Try direct REST API call in case SDK headers conflicted
            rest_reply = _direct_gemini_rest(api_key, prompt)
            if rest_reply:
                _conversation_history.append((prompt, rest_reply))
                return rest_reply

        if last_error is not None:
            print(f"Gemini API warning: {last_error}")

        # 4. Keyless AI fallback so Jarvis still answers every question seamlessly
        backup_reply = _fallback_ai_answer(prompt)
        if backup_reply:
            _conversation_history.append((prompt, backup_reply))
            return backup_reply

        if not api_key:
            return (
                "Sir, your GEMINI_API_KEY is missing from the .env file. "
                "Please add a valid key from Google AI Studio."
            )
        return "Sorry, Sir, I could not reach the AI service right now. Please check your internet connection or Gemini API key."


def aiprocess(command):
    """Process general questions with the AI assistant and speak the response."""
    try:
        reply = generate_ai_reply(command)
        print(reply)
        speak(reply)
        return reply
    except Exception as error:
        print(f"Gemini error: {error}")
        speak("Sorry, I could not process that request, Sir.")
        return None


def is_datetime_query(command):
    """
    Check if the command is genuinely asking for the current time, date, or day,
    without falsely intercepting general questions like 'how is the weather today'
    or 'what is spacetime'.
    """
    cmd = re.sub(r"[?.!,;:]+", "", command.lower()).strip()

    exact_matches = {
        "time",
        "date",
        "day",
        "today",
        "current time",
        "current date",
        "current day",
        "time and date",
        "date and time",
        "todays date",
        "today's date",
        "date today",
        "time now",
        "what time",
        "what date",
        "what day",
    }
    if cmd in exact_matches:
        return True

    # Never intercept weather, news, history, sports, or general knowledge questions
    if any(
        topic in cmd
        for topic in (
            "weather",
            "temperature",
            "forecast",
            "news",
            "headline",
            "history",
            "fact",
            "joke",
            "quote",
            "market",
            "stock",
            "match",
            "score",
            "spacetime",
            "complexity",
            "dilation",
            "update",
            "candidate",
            "birthday",
            "holiday",
        )
    ):
        return False

    patterns = [
        r"^(?:what|whats|what's|tell me|give me|check|show)\s+(?:is\s+)?(?:the\s+)?(?:current\s+)?(?:time|date|day)(?:\s+(?:and\s+(?:date|time)|it\s+is|is\s+it|today|now|please|sir))*$",
        r"^what\s+(?:time|date|day)\s+is\s+(?:it|today)(?:\s+(?:now|please|sir))*$",
        r"^what\s+is\s+(?:today|today's\s+date|todays\s+date)(?:\s+(?:please|sir))*$",
        r"^(?:whats|what's)\s+(?:the\s+time|the\s+date|the\s+day|today's\s+date|todays\s+date)(?:\s+(?:now|please|sir))*$",
        r"^which\s+day\s+is\s+(?:it|today)(?:\s+(?:now|please|sir))*$",
        r"^(?:tell\s+me\s+|what\s+is\s+)?(?:the\s+)?(?:time\s+and\s+date|date\s+and\s+time)(?:\s+(?:today|now|please|sir))*$",
    ]
    return any(re.search(p, cmd) for p in patterns)


def current_datetime_response(command):
    """Return a spoken response for a time, date, or day request."""
    now = datetime.now()
    cmd = command.lower()

    has_time = bool(re.search(r"\btime\b", cmd))
    has_date = bool(re.search(r"\bdate\b", cmd))
    has_day = bool(re.search(r"\b(day|today)\b", cmd))

    if has_time and (has_date or has_day):
        return f"It is {now.strftime('%I:%M %p')}, {now.strftime('%A, %B %d, %Y')}, Sir."
    if has_time:
        return f"It is {now.strftime('%I:%M %p')}, Sir."
    if has_day and not has_date:
        return f"Today is {now.strftime('%A')}, Sir."
    return f"Today is {now.strftime('%A, %B %d, %Y')}, Sir."


def _lookup_music_link(song_query):
    """Look up a song case-insensitively in musiclibrary.py if available."""
    if musiclibrary is None or not hasattr(musiclibrary, "music"):
        return None
    target = song_query.strip().lower()
    for name, url in musiclibrary.music.items():
        if name.strip().lower() == target:
            return url
    return None


def processcommand(c):
    """Route a spoken or typed command to built-in actions or the Gemini AI agent."""
    global music_playing

    if not c or not str(c).strip():
        return False

    raw_command = str(c).strip()
    # Strip optional leading wake word if the user said "Jarvis, <command>"
    cleaned = re.sub(
        r"^(?:hey\s+|ok\s+|hi\s+|hello\s+)?(?:jarvis|jarvas|jervis|jarves|charvis|jarvice)\b[\s,.!?:;-]*",
        "",
        raw_command,
        flags=re.IGNORECASE,
    ).strip()
    if cleaned:
        raw_command = cleaned

    command = raw_command.lower().strip()

    if command in {"stop", "exit", "quit", "shutdown", "shut down", "goodbye", "bye"}:
        speak("Shutting down, Sir.")
        return True

    if command in {"thank you", "thanks", "thank you jarvis", "thanks jarvis"}:
        speak("You are welcome, Sir.")
        return True

    if any(phrase in command for phrase in ("stop the song", "stop music", "stop the music", "pause the song", "pause music")):
        if music_playing:
            if pyautogui is not None:
                try:
                    pyautogui.press("space")
                except Exception as error:
                    print(f"Media key warning: {error}")
            music_playing = False
            speak("Music stopped, Sir.")
        else:
            speak("No music is currently playing, Sir.")
        return False

    if is_datetime_query(command):
        speak(current_datetime_response(command))
        return False

    if "open google" in command:
        webbrowser.open("https://google.com")
    elif "open facebook" in command:
        webbrowser.open("https://facebook.com")
    elif "open whatsapp" in command:
        webbrowser.open("https://web.whatsapp.com")
    elif "open instagram" in command:
        webbrowser.open("https://instagram.com")
    elif "open twitter" in command or "open x" in command:
        webbrowser.open("https://twitter.com")
    elif "open gmail" in command:
        webbrowser.open("https://mail.google.com")
    elif "open github" in command:
        webbrowser.open("https://github.com")
    elif "open reddit" in command:
        webbrowser.open("https://reddit.com")
    elif "open youtube" in command:
        webbrowser.open("https://youtube.com")
    elif command == "play" or command.startswith("play "):
        song = raw_command[4:].strip()
        if song:
            speak(f"Playing {song}, Sir.")
            direct_link = _lookup_music_link(song)
            if direct_link:
                webbrowser.open(direct_link)
                music_playing = True
            elif pywhatkit is not None:
                try:
                    pywhatkit.playonyt(song)
                    music_playing = True
                except Exception:
                    search_url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(song)
                    webbrowser.open(search_url)
                    music_playing = True
            else:
                search_url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(song)
                webbrowser.open(search_url)
                music_playing = True
        else:
            speak("Please tell me the song name, Sir.")
    else:
        # Let the Gemini AI agent handle all other questions and commands
        aiprocess(raw_command)

    return False


if __name__ == "__main__":
    speak("Initializing Jarvis....")
    r = sr.Recognizer()
    mic_calibrated = False

    while True:
        print("recognizing")
        try:
            with sr.Microphone() as source:
                if not mic_calibrated:
                    r.adjust_for_ambient_noise(source, duration=0.5)
                    mic_calibrated = True
                print("listening...")
                audio = r.listen(source, timeout=4, phrase_time_limit=6)

            word = r.recognize_google(audio)
            print(repr(word))

            match = WAKE_WORD_PATTERN.search(word)
            if match:
                inline_command = word[match.end():].lstrip(" ,.!?:;-").strip()
                if inline_command:
                    command = inline_command
                else:
                    speak("Yes Sir")
                    with sr.Microphone() as source:
                        print("jarvis active")
                        audio = r.listen(source, timeout=6, phrase_time_limit=12)
                    command = r.recognize_google(audio)
                    print(repr(command))

                if "thank you" in command.lower() or "thanks" in command.lower():
                    speak("You are welcome, Sir.")
                    break

                if processcommand(command):
                    break

        except (sr.WaitTimeoutError, sr.UnknownValueError):
            continue
        except KeyboardInterrupt:
            speak("Shutting down, Sir.")
            break
        except Exception as e:
            print(f"google error; {e}")
