# pyright: reportMissingImports=false, reportMissingModuleSource=false, reportOptionalMemberAccess=false, reportAttributeAccessIssue=false, reportGeneralTypeIssues=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
import glob
import importlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime
from typing import Any

try:
    import pyaudio  # noqa: F401
except ModuleNotFoundError:
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "PyAudio"])
        import pyaudio  # noqa: F401
    except Exception:
        pyaudio = None  # type: ignore[assignment]

import speech_recognition as sr
from dotenv import load_dotenv
from google import genai
from google.genai import types
from gtts import gTTS

try:
    from pygame import mixer
except Exception:
    mixer = None  # type: ignore[assignment]

try:
    import pyautogui
except Exception:
    pyautogui = None  # type: ignore[assignment]

try:
    import pywhatkit
except Exception:
    pywhatkit = None  # type: ignore[assignment]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_env_files() -> None:
    for env_path in (
        os.path.join(BASE_DIR, ".env"),
        os.path.join(os.path.dirname(BASE_DIR), ".env"),
    ):
        if os.path.isfile(env_path):
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

DEFAULT_MUSIC: dict[str, str] = {
    "the finest": "https://youtu.be/Ld9hW_ztn_c",
    "lip shade": "https://youtu.be/B85XuqXJCRY",
    "dusky": "https://youtu.be/acnHDzmxwyc",
    "piche tere": "https://youtu.be/SZisWzyBdHI",
    "kurbaan hua": "https://youtu.be/gCNmhrvplpw",
    "kath lagda": "https://youtu.be/nMozMETeCyw",
    "hood ambience": "https://youtu.be/qs61wmCGBhs",
    "city dreams": "https://youtu.be/OUUWLyfn3hY",
    "moodshift": "https://youtu.be/8cxMyUx-T74",
    "she aint easy": "https://youtu.be/p4s7iPXlGlI",
    "kaare": "https://youtu.be/kr_CAcR0Bz4",
    "headliner": "https://youtu.be/GE6w7DRyqcM",
}

CANDIDATE_MODELS: list[str] = list(
    dict.fromkeys(
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
    )
)

WAKE_WORD_PATTERN = re.compile(
    r"\b(jarvis|jarvas|jervis|jarves|charvis|jarvice|gervais|jarvi)\b",
    re.IGNORECASE,
)

music_playing: bool = False
spotify_playing: bool = False
recognizer = sr.Recognizer()
_mixer_initialized: bool = False
_ai_lock = threading.Lock()
_active_chat: Any = None
_gemini_key_rejected: bool = False
_conversation_history: list[tuple[str, str]] = []


def _ensure_mixer() -> bool:
    global _mixer_initialized
    if _mixer_initialized:
        return True
    if mixer is None:
        return False
    try:
        mixer.init()
        _mixer_initialized = True
    except Exception:
        _mixer_initialized = False
    return _mixer_initialized


_ensure_mixer()


def _get_api_key() -> str:
    _load_env_files()
    raw = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
    clean = raw.strip().strip('"').strip("'")
    if clean:
        os.environ["GEMINI_API_KEY"] = clean
    return clean


def _build_clients(api_key: str) -> list[Any]:
    if not api_key:
        return []
    os.environ.pop("GOOGLE_API_KEY", None)
    os.environ.pop("GOOGLE_GENAI_USE_VERTEXAI", None)
    clients: list[Any] = []
    for use_vertex in (False, True):
        try:
            if use_vertex:
                clients.append(genai.Client(vertexai=True, api_key=api_key))
            else:
                clients.append(genai.Client(api_key=api_key))
        except Exception:
            continue
    return clients


def speak(text: str) -> None:
    clean = re.sub(r"[*_#~>`]+", " ", str(text or ""))
    clean = re.sub(r"\s+", " ", clean).strip()
    if not clean:
        return
    if not _ensure_mixer() or mixer is None:
        print(f"Jarvis: {clean}")
        return
    temp_path: str | None = None
    try:
        fd, temp_path = tempfile.mkstemp(prefix="jarvis_response_", suffix=".mp3", dir=BASE_DIR)
        os.close(fd)
        gTTS(text=clean, lang="en", slow=False).save(temp_path)
        mixer.music.load(temp_path)
        mixer.music.play()
        while mixer.music.get_busy():
            time.sleep(0.1)
        mixer.music.unload()
    except Exception:
        pass
    finally:
        if temp_path and os.path.exists(temp_path):
            for _ in range(3):
                try:
                    os.remove(temp_path)
                    break
                except OSError:
                    time.sleep(0.1)


def _weather_fallback(prompt: str) -> str | None:
    if not any(w in prompt.lower() for w in ("weather", "temperature", "forecast")):
        return None
    try:
        req = urllib.request.Request(
            "https://wttr.in/?format=%C,+%t+(feels+like+%f),+humidity+%h",
            headers={"User-Agent": "curl/8.0"},
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            info = resp.read().decode("utf-8", errors="ignore").strip()
            if info and "<" not in info and "Unknown" not in info:
                return f"The weather right now is {info}, Sir."
    except Exception:
        pass
    return "The skies look clear and pleasant right now, Sir."


def _fallback_ai_answer(prompt: str) -> str | None:
    weather_ans = _weather_fallback(prompt)
    if weather_ans and "right now is" in weather_ans:
        return weather_ans

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
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8", errors="ignore").strip()
            try:
                parsed = json.loads(raw)
                choices = parsed.get("choices") or []
                if choices:
                    content = str((choices[0].get("message") or {}).get("content") or "").strip()
                    if content:
                        return content
            except Exception:
                if raw and "<!DOCTYPE" not in raw and "<html" not in raw.lower():
                    return raw
    except Exception:
        pass

    try:
        full_prompt = f"{SYSTEM_INSTRUCTION}\nUser: {prompt}\nJarvis:"
        encoded = urllib.parse.quote(full_prompt)
        req = urllib.request.Request(
            f"https://text.pollinations.ai/{encoded}",
            headers={"User-Agent": "JarvisVoiceAssistant/1.0"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            reply = resp.read().decode("utf-8", errors="ignore").strip()
            if reply and "<!DOCTYPE" not in reply and "<html" not in reply.lower():
                return reply
    except Exception:
        pass

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
        with urllib.request.urlopen(req, timeout=6) as resp:
            sdata = json.loads(resp.read().decode("utf-8", errors="ignore"))
            results = ((sdata.get("query") or {}).get("search")) or []
            if results:
                title = results[0].get("title", "")
                sum_url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(title)
                sreq = urllib.request.Request(
                    sum_url, headers={"User-Agent": "JarvisVoiceAssistant/1.0"}
                )
                with urllib.request.urlopen(sreq, timeout=6) as sresp:
                    sum_data = json.loads(sresp.read().decode("utf-8", errors="ignore"))
                    extract = str(sum_data.get("extract") or "").strip()
                    if extract:
                        sentences = re.split(r"(?<=[.!?])\s+", extract)
                        short_extract = " ".join(sentences[:2]).strip()
                        return f"{short_extract} Sir."
    except Exception:
        pass

    if weather_ans:
        return weather_ans
    return "I am online and ready to assist you, Sir."


def generate_ai_reply(command: str) -> str:
    global _active_chat, _gemini_key_rejected
    prompt = str(command).strip()
    if not prompt:
        return "Yes, Sir? How may I help you?"

    with _ai_lock:
        if _active_chat is not None:
            try:
                resp = _active_chat.send_message(prompt)
                reply = str(resp.text or "").strip()
                if reply:
                    _conversation_history.append((prompt, reply))
                    return reply
            except Exception:
                _active_chat = None

        api_key = _get_api_key()
        if api_key and not _gemini_key_rejected:
            config = types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION)
            auth_failed_all = True
            for cand_client in _build_clients(api_key):
                failures = 0
                for model_name in CANDIDATE_MODELS:
                    try:
                        chat_session = cand_client.chats.create(model=model_name, config=config)
                        resp = chat_session.send_message(prompt)
                        reply = str(resp.text or "").strip()
                        if reply:
                            _active_chat = chat_session
                            _conversation_history.append((prompt, reply))
                            return reply
                    except Exception as err:
                        if any(code in str(err) for code in ("401", "UNAUTHENTICATED", "403")):
                            failures += 1
                            if failures >= 1:
                                break
                        else:
                            auth_failed_all = False
                        continue
            if auth_failed_all:
                _gemini_key_rejected = True

        backup = _fallback_ai_answer(prompt)
        if backup:
            _conversation_history.append((prompt, backup))
            return backup
        return "I am here and ready to assist you, Sir."


def aiprocess(command: str) -> str:
    reply = generate_ai_reply(command)
    print(reply)
    speak(reply)
    return reply


def is_datetime_query(command: str) -> bool:
    cmd = re.sub(r"[?.!,;:]+", "", command.lower()).strip()
    if cmd in {
        "time",
        "date",
        "day",
        "today",
        "current time",
        "current date",
        "time and date",
        "date and time",
        "todays date",
        "today's date",
        "date today",
    }:
        return True
    if any(
        t in cmd
        for t in (
            "weather",
            "temperature",
            "forecast",
            "news",
            "history",
            "fact",
            "joke",
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
    ]
    return any(re.search(p, cmd) for p in patterns)


def current_datetime_response(command: str) -> str:
    now = datetime.now()
    cmd = command.lower()
    if "time" in cmd and any(w in cmd for w in ("date", "day", "today")):
        return f"It is {now.strftime('%I:%M %p')}, {now.strftime('%A, %B %d, %Y')}, Sir."
    if "time" in cmd:
        return f"It is {now.strftime('%I:%M %p')}, Sir."
    if "day" in cmd and "date" not in cmd:
        return f"Today is {now.strftime('%A')}, Sir."
    return f"Today is {now.strftime('%A, %B %d, %Y')}, Sir."


def _lookup_music_link(song_query: str) -> str | None:
    target = song_query.strip().lower()
    if target in DEFAULT_MUSIC:
        return DEFAULT_MUSIC[target]
    try:
        mod = importlib.import_module("musiclibrary")
        music_dict = getattr(mod, "music", {})
        for k, v in music_dict.items():
            if str(k).strip().lower() == target:
                return str(v)
    except Exception:
        pass
    return None


def _is_spotify_running() -> bool:
    """Check if Spotify.exe is currently running on Windows."""
    if os.name != "nt":
        return False
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", "IMAGENAME eq Spotify.exe"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return "spotify.exe" in out.lower()
    except Exception:
        return False


def _find_spotify_executable() -> str | None:
    """Locate Spotify.exe or Spotify.lnk across standard, Store, and Start Menu paths on Windows."""
    if os.name != "nt":
        return None
    candidates = [
        os.path.expandvars(r"%APPDATA%\Spotify\Spotify.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\Spotify.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Spotify\Spotify.exe"),
        os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Spotify.lnk"),
        os.path.expandvars(r"%PROGRAMDATA%\Microsoft\Windows\Start Menu\Programs\Spotify.lnk"),
    ]
    pkg_matches = glob.glob(
        os.path.expandvars(r"%LOCALAPPDATA%\Packages\SpotifyAB.SpotifyMusic*\LocalCache\Roaming\Spotify\Spotify.exe")
    )
    candidates.extend(pkg_matches)
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None


def _focus_spotify_window() -> None:
    """Bring the Spotify desktop window to the foreground on Windows."""
    if os.name != "nt":
        return
    try:
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-WindowStyle",
                "Hidden",
                "-Command",
                "(New-Object -ComObject WScript.Shell).AppActivate('Spotify') | Out-Null",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
    except Exception:
        pass


def _launch_spotify_app(uri: str | None = None) -> bool:
    """
    Reliably launch and focus the pre-installed Spotify desktop app on Windows
    using executable paths, Start Menu AppID, or Windows Search fallback.
    """
    if os.name != "nt":
        webbrowser.open(uri or "spotify:")
        return True

    launched = False

    # 1. Try direct executable or shortcut path first
    exe_path = _find_spotify_executable()
    if exe_path:
        try:
            if exe_path.lower().endswith(".exe"):
                args = [exe_path] + ([f"--uri={uri}"] if uri else [])
                subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                startfile_fn = getattr(os, "startfile", None)
                if callable(startfile_fn):
                    startfile_fn(exe_path)
            launched = True
        except Exception:
            pass

    # 2. Try launching via Windows Start Menu AppsFolder (works for Microsoft Store & Desktop installs)
    if not launched:
        try:
            ps_cmd = (
                "$app = Get-StartApps | Where-Object { $_.Name -like '*Spotify*' } | Select-Object -First 1; "
                "if ($app) { Start-Process ('shell:AppsFolder\\' + $app.AppID) }"
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_cmd],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=4,
            )
        except Exception:
            pass

    time.sleep(1.2)

    # 3. If Spotify.exe still isn't running, open it via Windows Start Menu key + typing "spotify"
    if not _is_spotify_running() and pyautogui is not None:
        try:
            pyautogui.press("win")
            time.sleep(0.7)
            pyautogui.write("spotify", interval=0.05)
            time.sleep(0.8)
            pyautogui.press("enter")
            launched = True
        except Exception:
            pass

    _focus_spotify_window()
    return launched


def open_spotify_app() -> None:
    """Open or focus the installed Spotify desktop application."""
    speak("Opening Spotify, Sir.")
    _launch_spotify_app()


def play_on_spotify(song_query: str) -> None:
    """
    Open the pre-installed Spotify desktop app, search for the song via Spotify's
    Ctrl+K Quick Search spotlight modal, and play the #1 top result directly via Shift+Enter.
    """
    global music_playing, spotify_playing
    song = song_query.strip()
    if not song:
        speak("Please tell me the song name to play on Spotify, Sir.")
        return

    speak(f"Playing {song} on Spotify, Sir.")
    was_running = _is_spotify_running()

    # Launch or focus the Spotify desktop app
    _launch_spotify_app()

    if pyautogui is not None:
        # Wait for the Spotify desktop window to be ready and focused
        time.sleep(2.0 if was_running else 5.0)
        _focus_spotify_window()
        time.sleep(0.4)
        try:
            # Open Spotify Desktop's built-in Quick Search modal (Ctrl+K)
            pyautogui.hotkey("ctrl", "k")
            time.sleep(0.6)
            # Clear any existing text in Quick Search and type the song query
            pyautogui.hotkey("ctrl", "a")
            time.sleep(0.1)
            pyautogui.press("backspace")
            time.sleep(0.1)
            pyautogui.write(song, interval=0.04)
            # Wait for Spotify to populate and auto-highlight the #1 top matching song
            time.sleep(1.8)
            # Shift+Enter immediately plays the #1 highlighted top result
            pyautogui.hotkey("shift", "enter")
            time.sleep(0.3)
            # Close the Ctrl+K search modal if it remains open
            pyautogui.press("esc")
        except Exception:
            pass

    music_playing = True
    spotify_playing = True


def _extract_spotify_song(raw_command: str) -> str | None:
    """
    If the command asks to play a song in/on Spotify, return the extracted song name
    (or '' if no song name was given). Return None if it is not a Spotify play command.
    """
    patterns = [
        r"^(?:open\s+spotify\s+and\s+)?play\s+(.+?)\s+(?:in|on|from|using)\s+spotify$",
        r"^(?:open\s+spotify\s+and\s+)?play\s+(?:in|on|from|using)\s+spotify\s+(.+)$",
        r"^open\s+spotify\s+and\s+play\s+(.+)$",
        r"^spotify\s+play\s+(.+)$",
    ]
    for pat in patterns:
        m = re.match(pat, raw_command.strip(), flags=re.IGNORECASE)
        if m:
            return m.group(1).strip()

    if re.match(r"^play\s+(?:in|on|from)?\s*spotify$", raw_command.strip(), flags=re.IGNORECASE):
        return ""
    return None


def processcommand(c: str) -> bool:
    global music_playing, spotify_playing
    if not c or not str(c).strip():
        return False
    raw = (
        re.sub(
            r"^(?:hey\s+|ok\s+|hi\s+|hello\s+)?(?:jarvis|jarvas|jervis|jarves|charvis|jarvice)\b[\s,.!?:;-]*",
            "",
            str(c).strip(),
            flags=re.IGNORECASE,
        ).strip()
        or str(c).strip()
    )
    command = raw.lower().strip()

    if command in {"stop", "exit", "quit", "shutdown", "shut down"}:
        speak("Shutting down, Sir.")
        return True
    if command in {"thank you", "thanks", "thank you jarvis", "thanks jarvis"}:
        speak("You are welcome, Sir.")
        return True
    if any(
        p in command
        for p in (
            "stop the song",
            "stop music",
            "stop the music",
            "pause the song",
            "pause music",
            "stop spotify",
            "pause spotify",
        )
    ):
        if music_playing or "spotify" in command:
            if pyautogui is not None:
                try:
                    if spotify_playing or "spotify" in command:
                        pyautogui.press("playpause")
                    else:
                        pyautogui.press("space")
                except Exception:
                    pass
            music_playing = False
            spotify_playing = False
            speak("Music stopped, Sir.")
        else:
            speak("No music is currently playing, Sir.")
        return False
    if is_datetime_query(command):
        speak(current_datetime_response(command))
        return False

    # Check for "play [song] in/on spotify" or "open spotify and play [song]" first
    spotify_song = _extract_spotify_song(raw)
    if spotify_song is not None:
        play_on_spotify(spotify_song)
        return False

    if "open spotify" in command or "launch spotify" in command or "start spotify" in command:
        open_spotify_app()
    elif "open google" in command:
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
        song = raw[4:].strip()
        if song:
            speak(f"Playing {song}, Sir.")
            link = _lookup_music_link(song)
            playonyt_fn = getattr(pywhatkit, "playonyt", None) if pywhatkit is not None else None
            if link:
                webbrowser.open(link)
            elif callable(playonyt_fn):
                try:
                    playonyt_fn(song)
                except Exception:
                    webbrowser.open("https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(song))
            else:
                webbrowser.open("https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(song))
            music_playing = True
            spotify_playing = False
        else:
            speak("Please tell me the song name, Sir.")
    else:
        aiprocess(raw)
    return False


if __name__ == "__main__":
    speak("Initializing Jarvis....")
    r = sr.Recognizer()
    calibrated = False
    while True:
        print("recognizing")
        command = ""
        try:
            with sr.Microphone() as source:
                if not calibrated:
                    r.adjust_for_ambient_noise(source, duration=0.5)
                    calibrated = True
                print("listening...")
                audio = r.listen(source, timeout=4, phrase_time_limit=6)
            word = r.recognize_google(audio)
            print(repr(word))
            match = WAKE_WORD_PATTERN.search(word)
            if match:
                inline_cmd = word[match.end() :].lstrip(" ,.!?:;-").strip()
                if inline_cmd:
                    command = inline_cmd
                else:
                    speak("Yes Sir")
                    with sr.Microphone() as source:
                        print("jarvis active")
                        audio = r.listen(source, timeout=6, phrase_time_limit=12)
                    command = r.recognize_google(audio)
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
