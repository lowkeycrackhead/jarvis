# pyright: reportMissingImports=false, reportMissingModuleSource=false, reportOptionalMemberAccess=false, reportOptionalCall=false, reportAttributeAccessIssue=false, reportGeneralTypeIssues=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
from concurrent.futures import ThreadPoolExecutor, as_completed
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
from datetime import datetime, timedelta, timezone
from typing import Any

IS_CLOUD = bool(os.getenv("VERCEL") or os.getenv("VERCEL_ENV"))

if not IS_CLOUD:
    try:
        import pyaudio  # noqa: F401
    except ModuleNotFoundError:
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "PyAudio"])
            import pyaudio  # noqa: F401
        except Exception:
            pyaudio = None  # type: ignore[assignment]
else:
    pyaudio = None  # type: ignore[assignment]

import jarvis_extras as extras

try:
    import speech_recognition as sr
except Exception:
    sr = None  # type: ignore[assignment]

from dotenv import load_dotenv
from google import genai
from google.genai import types

try:
    from gtts import gTTS
except Exception:
    gTTS = None  # type: ignore[assignment]

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
    if IS_CLOUD:
        return  # Always use Vercel dashboard Environment Variables in cloud mode
    for env_path in (
        os.path.join(os.path.dirname(BASE_DIR), ".env"),
        os.path.join(BASE_DIR, ".env"),
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
                        if k and v and "put_your_" not in v.lower():
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

# Fast Flash models prioritized for low-latency voice responses
CANDIDATE_MODELS: list[str] = list(
    dict.fromkeys(
        m
        for m in [
            os.getenv("GEMINI_MODEL", "").strip(),
            "gemini-2.5-flash-lite",
            "gemini-2.5-flash",
            "gemini-2.0-flash-lite",
            "gemini-2.0-flash",
        ]
        if m
    )
)

# Local Ollama configuration (defaults to llama3.2:3b, ideal for 16 GB RAM + Intel Arc)
DEFAULT_OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b").strip() or "llama3.2:3b"
OLLAMA_BASE_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
# AI_PROVIDER: "auto" (Ollama local if running -> Gemini -> backup), "ollama", or "gemini"
ai_provider: str = os.getenv("AI_PROVIDER", "gemini" if IS_CLOUD else "auto").strip().lower() or ("gemini" if IS_CLOUD else "auto")
if ai_provider not in {"auto", "ollama", "gemini"}:
    ai_provider = "auto"

WAKE_WORD_PATTERN = re.compile(
    r"\b(jarvis|jarvas|jervis|jarves|charvis|jarvice|gervais|jarvi)\b",
    re.IGNORECASE,
)

music_playing: bool = False
spotify_playing: bool = False
recognizer = sr.Recognizer() if sr is not None else None
_mixer_initialized: bool = False
_ai_lock = threading.Lock()
_active_chat: Any = None
_gemini_key_rejected: bool = False
_gemini_checked_key: str = ""
_resolved_ollama_model: str | None = None
_ollama_last_probe: float = 0.0
_conversation_history: list[tuple[str, str]] = []

# Cooperative task cancellation event (triggered by server.py's /api/stop endpoint)
_cancel_event = threading.Event()


def set_ai_provider(mode: str) -> str:
    """Switch active AI routing mode between 'auto', 'ollama', and 'gemini'."""
    global ai_provider
    clean = str(mode or "").strip().lower()
    if clean in {"auto", "ollama", "gemini"}:
        ai_provider = clean
    return ai_provider


def get_ai_status() -> dict[str, Any]:
    """Return current AI engine configuration, detected Ollama model, and persona."""
    return {
        "provider": ai_provider,
        "ollama_model": _resolved_ollama_model or DEFAULT_OLLAMA_MODEL,
        "ollama_ready": bool(_probe_ollama_model(force=False)),
        "persona": extras.get_persona(),
    }


def set_persona(mode: str) -> str:
    """Switch Jarvis persona between 'butler', 'coder', and 'tutor'."""
    global _active_chat
    _active_chat = None
    return extras.set_persona(mode)


def clear_memory() -> None:
    """Clear multi-turn conversation history."""
    global _active_chat
    _conversation_history.clear()
    _active_chat = None


def cancel_current_task() -> None:
    """Signal any in-progress command, speech, or wait loop to abort immediately."""
    _cancel_event.set()
    if _mixer_initialized and mixer is not None:
        try:
            mixer.music.stop()
        except Exception:
            pass


def clear_cancel() -> None:
    """Reset the cancellation flag before starting a new command."""
    _cancel_event.clear()


def is_cancelled() -> bool:
    """Return True if the user requested to cancel the active task."""
    return _cancel_event.is_set()


def _cancellable_sleep(seconds: float) -> bool:
    """Sleep in short increments; returns True if cancelled mid-sleep."""
    deadline = time.monotonic() + max(0.0, seconds)
    while time.monotonic() < deadline:
        if _cancel_event.is_set():
            return True
        time.sleep(min(0.1, max(0.0, deadline - time.monotonic())))
    return _cancel_event.is_set()


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


_gemini_last_error: str = ""


def get_gemini_last_error() -> str:
    return _gemini_last_error


def _get_api_key() -> str:
    _load_env_files()
    raw = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
    clean = raw.strip().strip('"').strip("'")
    if "put_your_" in clean.lower():
        return ""
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


def _get_fast_config() -> Any:
    """Build a low-latency GenerateContentConfig (short output, minimal thinking)."""
    kwargs: dict[str, Any] = {
        "system_instruction": SYSTEM_INSTRUCTION,
        "max_output_tokens": 180,
        "temperature": 0.4,
    }
    try:
        if hasattr(types, "ThinkingConfig"):
            kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
    except Exception:
        pass
    try:
        return types.GenerateContentConfig(**kwargs)
    except Exception:
        return types.GenerateContentConfig(
            system_instruction=extras.get_system_instruction(),
            max_output_tokens=180,
        )


def _probe_ollama_model(force: bool = False) -> str | None:
    """
    Check if local Ollama is running at localhost:11434 and return the best available
    installed model (preferring OLLAMA_MODEL / llama3.2:3b / gemma3:4b / phi4-mini).
    Caches probe result for 15 seconds to keep voice replies instant.
    """
    global _resolved_ollama_model, _ollama_last_probe
    now = time.monotonic()
    if not force and (now - _ollama_last_probe) < 15.0:
        return _resolved_ollama_model

    _ollama_last_probe = now
    preferred = os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL).strip() or DEFAULT_OLLAMA_MODEL
    try:
        req = urllib.request.Request(f"{OLLAMA_BASE_URL}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=0.8) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            installed = [str(m.get("name", "")).strip() for m in (data.get("models") or []) if m.get("name")]
            if not installed:
                _resolved_ollama_model = None
                return None

            # Match preferred model first, then fast 3B/4B voice models, then first installed model
            priority = [preferred, "llama3.2:3b", "gemma3:4b", "phi4-mini", "llama3.2:1b"]
            for target in priority:
                t_low = target.lower()
                for name in installed:
                    if name.lower() == t_low or name.lower().startswith(t_low + ":"):
                        _resolved_ollama_model = name
                        return name
            _resolved_ollama_model = installed[0]
            return _resolved_ollama_model
    except Exception:
        _resolved_ollama_model = None
        return None


def _ask_ollama(prompt: str) -> str | None:
    """Query local Ollama (/api/chat) with fast voice settings and keep_alive."""
    if is_cancelled():
        return None
    model = _probe_ollama_model(force=False)
    if not model:
        return None
    try:
        messages = [{"role": "system", "content": extras.get_system_instruction()}]
        for u_msg, a_msg in _conversation_history[-8:]:
            messages.append({"role": "user", "content": u_msg})
            messages.append({"role": "assistant", "content": a_msg})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "keep_alive": "10m",
            "options": {
                "num_predict": 160,
                "temperature": 0.4,
            },
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{OLLAMA_BASE_URL}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=18) as resp:
            parsed = json.loads(resp.read().decode("utf-8", errors="ignore"))
            content = str((parsed.get("message") or {}).get("content") or "").strip()
            if content:
                return content
    except Exception as err:
        print(f"Ollama warning ({model}): {err}")
    return None


def _stream_ollama(prompt: str):
    """Stream tokens live from local Ollama (/api/chat with stream=True)."""
    if is_cancelled():
        return
    model = _probe_ollama_model(force=False)
    if not model:
        return
    messages = [{"role": "system", "content": extras.get_system_instruction()}]
    for u_msg, a_msg in _conversation_history[-8:]:
        messages.append({"role": "user", "content": u_msg})
        messages.append({"role": "assistant", "content": a_msg})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "keep_alive": "10m",
        "options": {"num_predict": 180, "temperature": 0.4},
    }
    req = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=22) as resp:
            for raw_line in resp:
                if is_cancelled():
                    return
                line = raw_line.decode("utf-8", errors="ignore").strip()
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except Exception:
                    continue
                token = str((chunk.get("message") or {}).get("content") or "")
                if token:
                    yield token
                if chunk.get("done"):
                    break
    except Exception as err:
        print(f"Ollama stream warning ({model}): {err}")


def stream_ai_reply(command: str):
    """Yield live reply chunks (word/token streaming) for the web HUD SSE endpoint."""
    prompt = str(command).strip()
    if not prompt:
        yield "Yes, Sir? How may I help you?"
        return
    if is_cancelled():
        return

    with _ai_lock:
        weather_ans = _weather_fallback(prompt)
        if weather_ans:
            _conversation_history.append((prompt, weather_ans))
            yield weather_ans
            return

        if ai_provider in {"ollama", "auto"}:
            collected: list[str] = []
            for tok in _stream_ollama(prompt):
                if is_cancelled():
                    return
                collected.append(tok)
                yield tok
            if collected:
                _conversation_history.append((prompt, "".join(collected).strip()))
                return
            if ai_provider == "ollama":
                yield (
                    f"Ollama is not running or '{DEFAULT_OLLAMA_MODEL}' is not pulled yet, Sir. "
                    f"Run 'ollama pull {DEFAULT_OLLAMA_MODEL}' and start Ollama."
                )
                return

        if ai_provider in {"gemini", "auto"} and not is_cancelled():
            gemini_ans = _ask_gemini(prompt)
            if gemini_ans:
                _conversation_history.append((prompt, gemini_ans))
                for part in re.findall(r"\S+\s*", gemini_ans):
                    if is_cancelled():
                        return
                    yield part
                return

        if is_cancelled():
            return
        backup = _fallback_ai_answer(prompt)
        if backup:
            _conversation_history.append((prompt, backup))
            yield backup


def speak(text: str) -> None:
    if is_cancelled():
        return
    clean = re.sub(r"[*_#~>`]+", " ", str(text or ""))
    clean = re.sub(r"\s+", " ", clean).strip()
    if not clean:
        return
    if not _ensure_mixer() or mixer is None or gTTS is None:
        print(f"Jarvis: {clean}")
        return
    temp_path: str | None = None
    try:
        fd, temp_path = tempfile.mkstemp(prefix="jarvis_response_", suffix=".mp3", dir=BASE_DIR)
        os.close(fd)
        gTTS(text=clean, lang="en", slow=False).save(temp_path)
        if is_cancelled():
            return
        mixer.music.load(temp_path)
        mixer.music.play()
        while mixer.music.get_busy():
            if is_cancelled():
                mixer.music.stop()
                break
            time.sleep(0.08)
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
                    time.sleep(0.08)


_current_request_city: str = ""


def set_request_city(city: str | None) -> None:
    global _current_request_city
    _current_request_city = urllib.parse.unquote(str(city or "")).strip()


def _weather_fallback(prompt: str) -> str | None:
    if not any(w in prompt.lower() for w in ("weather", "temperature", "forecast")):
        return None
    city = ""
    m = re.search(r"\b(?:in|at|for)\s+([a-zA-Z][a-zA-Z\s.-]{1,40}?)(?:\s+(?:today|now|right now|please|sir))?[?.!,]*$", prompt.strip(), flags=re.IGNORECASE)
    if m:
        city = m.group(1).strip()
    elif _current_request_city:
        city = _current_request_city
    loc = urllib.parse.quote(city) if city else ""
    try:
        req = urllib.request.Request(
            f"https://wttr.in/{loc}?m&format=%C,+%t+(feels+like+%f),+humidity+%h",
            headers={"User-Agent": "curl/8.0"},
        )
        with urllib.request.urlopen(req, timeout=3.5) as resp:
            info = resp.read().decode("utf-8", errors="ignore").strip()
            if info and "<" not in info and "Unknown" not in info:
                where = f" in {city}" if city else ""
                return f"The weather{where} right now is {info}, Sir."
    except Exception:
        pass
    return None


def _pollinations_post(prompt: str) -> str | None:
    try:
        messages = [{"role": "system", "content": extras.get_system_instruction()}]
        for u_msg, a_msg in _conversation_history[-8:]:
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
        with urllib.request.urlopen(req, timeout=5.5) as resp:
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
    return None


def _wikipedia_summary(prompt: str) -> str | None:
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
        with urllib.request.urlopen(req, timeout=3.5) as resp:
            sdata = json.loads(resp.read().decode("utf-8", errors="ignore"))
            results = ((sdata.get("query") or {}).get("search")) or []
            if results:
                title = results[0].get("title", "")
                sum_url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(title)
                sreq = urllib.request.Request(
                    sum_url, headers={"User-Agent": "JarvisVoiceAssistant/1.0"}
                )
                with urllib.request.urlopen(sreq, timeout=3.5) as sresp:
                    sum_data = json.loads(sresp.read().decode("utf-8", errors="ignore"))
                    extract = str(sum_data.get("extract") or "").strip()
                    if extract:
                        sentences = re.split(r"(?<=[.!?])\s+", extract)
                        short_extract = " ".join(sentences[:2]).strip()
                        return f"{short_extract} Sir."
    except Exception:
        pass
    return None


def _fallback_ai_answer(prompt: str) -> str:
    """Race fast backup providers in parallel so answers arrive in ~1-3 seconds."""
    if is_cancelled():
        return ""

    weather_ans = _weather_fallback(prompt)
    if weather_ans:
        return weather_ans

    tasks = [_pollinations_post]
    if re.match(r"^(?:what|who|where|when|explain|define|tell me about)\b", prompt.strip(), re.IGNORECASE):
        tasks.append(_wikipedia_summary)

    pool = ThreadPoolExecutor(max_workers=len(tasks))
    try:
        futures = [pool.submit(fn, prompt) for fn in tasks]
        for fut in as_completed(futures, timeout=6.0):
            if is_cancelled():
                return ""
            try:
                ans = fut.result()
                if ans:
                    return ans
            except Exception:
                continue
    except Exception:
        pass
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    return "I am online and ready to assist you, Sir."


def _ask_gemini(prompt: str) -> str | None:
    global _active_chat, _gemini_key_rejected, _gemini_checked_key

    if _active_chat is not None:
        try:
            resp = _active_chat.send_message(prompt)
            reply = str(resp.text or "").strip()
            if reply:
                return reply
        except Exception:
            _active_chat = None

    api_key = _get_api_key()
    if api_key != _gemini_checked_key:
        _gemini_checked_key = api_key
        _gemini_key_rejected = False

    if api_key and not _gemini_key_rejected:
        config = _get_fast_config()
        auth_failed_all = True
        for cand_client in _build_clients(api_key):
            if is_cancelled():
                return ""
            for model_name in CANDIDATE_MODELS:
                if is_cancelled():
                    return ""
                try:
                    chat_session = cand_client.chats.create(model=model_name, config=config)
                    resp = chat_session.send_message(prompt)
                    reply = str(resp.text or "").strip()
                    if reply:
                        _active_chat = chat_session
                        return reply
                except Exception as err:
                    global _gemini_last_error
                    err_s = str(err)
                    _gemini_last_error = f"{model_name}: {err_s[:180]}"
                    print(f"Gemini warning ({model_name}): {err_s[:180]}")
                    if any(code in err_s for code in ("401", "UNAUTHENTICATED", "403")):
                        break
                    auth_failed_all = False
                    continue
        if auth_failed_all:
            _gemini_key_rejected = True
    return None


def generate_ai_reply(command: str) -> str:
    prompt = str(command).strip()
    if not prompt:
        return "Yes, Sir? How may I help you?"
    if is_cancelled():
        return ""

    with _ai_lock:
        if is_cancelled():
            return ""

        # Weather queries use live weather lookup first (local Ollama doesn't have live weather)
        weather_ans = _weather_fallback(prompt)
        if weather_ans:
            _conversation_history.append((prompt, weather_ans))
            return weather_ans

        # 1. If provider is "ollama" or "auto", try local Ollama first if running
        if ai_provider in {"ollama", "auto"}:
            ollama_ans = _ask_ollama(prompt)
            if ollama_ans:
                _conversation_history.append((prompt, ollama_ans))
                return ollama_ans
            if ai_provider == "ollama":
                return (
                    f"Ollama is not running or '{DEFAULT_OLLAMA_MODEL}' is not pulled yet, Sir. "
                    f"Run 'ollama pull {DEFAULT_OLLAMA_MODEL}' and start Ollama."
                )

        # 2. Try Gemini cloud API
        if ai_provider in {"gemini", "auto"} and not is_cancelled():
            gemini_ans = _ask_gemini(prompt)
            if gemini_ans:
                _conversation_history.append((prompt, gemini_ans))
                return gemini_ans

        if is_cancelled():
            return ""

        # 3. Fast parallel web fallback
        backup = _fallback_ai_answer(prompt)
        if backup:
            _conversation_history.append((prompt, backup))
            return backup
        return ""


def aiprocess(command: str) -> str:
    reply = generate_ai_reply(command)
    if is_cancelled() or not reply:
        return ""
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


def _now_for_user(tz_name: str | None = None, tz_offset_min: int | None = None) -> datetime:
    """Return current datetime in the user's browser timezone (falls back to system local time)."""
    if tz_name:
        try:
            from zoneinfo import ZoneInfo
            return datetime.now(ZoneInfo(str(tz_name).strip()))
        except Exception:
            pass
    if tz_offset_min is not None:
        try:
            # JS Date.getTimezoneOffset() is minutes behind UTC (e.g. -330 for IST UTC+05:30)
            offset = timezone(timedelta(minutes=-int(tz_offset_min)))
            return datetime.now(timezone.utc).astimezone(offset)
        except Exception:
            pass
    return datetime.now()


def current_datetime_response(
    command: str,
    tz_name: str | None = None,
    tz_offset_min: int | None = None,
) -> str:
    now = _now_for_user(tz_name=tz_name, tz_offset_min=tz_offset_min)
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


def _get_spotify_pids() -> set[int]:
    """Return all running Spotify.exe PIDs on Windows (uses psutil or tasklist, no 64-bit handle bugs)."""
    pids: set[int] = set()
    try:
        import psutil  # type: ignore[import-not-found]
        for proc in psutil.process_iter(["pid", "name"]):
            if (proc.info.get("name") or "").lower() == "spotify.exe":
                pids.add(int(proc.info["pid"]))
        if pids:
            return pids
    except Exception:
        pass
    if os.name == "nt":
        try:
            out = subprocess.check_output(
                ["tasklist", "/FI", "IMAGENAME eq Spotify.exe", "/FO", "CSV", "/NH"],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=3,
            )
            for line in out.splitlines():
                parts = [c.strip().strip('"') for c in line.split(",")]
                if len(parts) >= 2 and parts[0].lower() == "spotify.exe" and parts[1].isdigit():
                    pids.add(int(parts[1]))
        except Exception:
            pass
    return pids


def _is_spotify_foreground() -> bool:
    """Return True ONLY if the currently focused Windows foreground window belongs to Spotify.exe."""
    if os.name != "nt":
        return False
    pids = _get_spotify_pids()
    if not pids:
        return False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetForegroundWindow.argtypes = []
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD

        fg = user32.GetForegroundWindow()
        if not fg:
            return False
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(fg, ctypes.byref(pid))
        return pid.value in pids
    except Exception:
        return False


def _focus_spotify_window(retries: int = 10, maximize: bool = True) -> bool:
    """Un-minimize, maximize, bring Spotify to front (no Alt key!), and verify it owns keyboard focus."""
    if os.name != "nt":
        return False
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsWindow.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.IsIconic.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.BringWindowToTop.argtypes = [wintypes.HWND]
    user32.BringWindowToTop.restype = wintypes.BOOL
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    user32.SetWindowPos.restype = wintypes.BOOL
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    user32.AttachThreadInput.restype = wintypes.BOOL
    kernel32.GetCurrentThreadId.argtypes = []
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD

    SW_SHOWMAXIMIZED = 3
    SW_RESTORE = 9
    HWND_TOPMOST = wintypes.HWND(-1)
    HWND_NOTOPMOST = wintypes.HWND(-2)
    SWP_NOMOVE = 0x0002
    SWP_NOSIZE = 0x0001
    SWP_SHOWWINDOW = 0x0040

    def _find_spotify_hwnd() -> int:
        pids = _get_spotify_pids()
        if not pids:
            return 0
        best_hwnd = 0
        best_area = -1

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def _enum_cb(hwnd, _lparam):
            nonlocal best_hwnd, best_area
            if not user32.IsWindow(hwnd):
                return True
            if user32.GetWindowTextLengthW(hwnd) <= 0:
                return True
            pid = wintypes.DWORD(0)
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value not in pids:
                return True
            if not (user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd)):
                return True
            rect = wintypes.RECT()
            area = 0
            if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                area = max(0, rect.right - rect.left) * max(0, rect.bottom - rect.top)
            if area > best_area:
                best_area = area
                best_hwnd = int(hwnd)
            return True

        user32.EnumWindows(_enum_cb, 0)
        return best_hwnd

    for _ in range(max(1, retries)):
        if is_cancelled():
            return False
        hwnd = _find_spotify_hwnd()
        if hwnd:
            try:
                if user32.IsIconic(hwnd):
                    user32.ShowWindow(hwnd, SW_RESTORE)
                if maximize:
                    user32.ShowWindow(hwnd, SW_SHOWMAXIMIZED)

                # Pop above browser/VS Code cleanly via TOPMOST -> NOTOPMOST without tapping Alt
                flags = SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW
                user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags)
                user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, flags)

                fg_hwnd = user32.GetForegroundWindow()
                cur_tid = kernel32.GetCurrentThreadId()
                fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None) if fg_hwnd else 0
                target_tid = user32.GetWindowThreadProcessId(hwnd, None)

                if fg_tid and fg_tid != cur_tid:
                    user32.AttachThreadInput(fg_tid, cur_tid, True)
                if target_tid and target_tid != cur_tid:
                    user32.AttachThreadInput(target_tid, cur_tid, True)

                user32.BringWindowToTop(hwnd)
                user32.SetForegroundWindow(hwnd)

                if fg_tid and fg_tid != cur_tid:
                    user32.AttachThreadInput(fg_tid, cur_tid, False)
                if target_tid and target_tid != cur_tid:
                    user32.AttachThreadInput(target_tid, cur_tid, False)

                time.sleep(0.15)
                if _is_spotify_foreground():
                    return True

                # Fallback: click safe empty area of Spotify title bar to give it real OS keyboard focus
                if pyautogui is not None:
                    rect = wintypes.RECT()
                    if user32.GetWindowRect(hwnd, ctypes.byref(rect)) and (rect.right - rect.left) > 300:
                        safe_x = rect.left + (rect.right - rect.left) // 2
                        safe_y = rect.top + 14
                        pyautogui.click(safe_x, safe_y)
                        time.sleep(0.15)
                        if _is_spotify_foreground():
                            return True
            except Exception as err:
                print(f"Spotify focus warning: {err}")
        if _cancellable_sleep(0.35):
            return False
    return _is_spotify_foreground()


def _launch_spotify_app(uri: str | None = None) -> bool:
    if os.name != "nt":
        webbrowser.open(uri or "spotify:")
        return True

    launched = False
    was_running = _is_spotify_running()

    if was_running:
        try:
            startfile_fn = getattr(os, "startfile", None)
            if callable(startfile_fn):
                startfile_fn(uri or "spotify:")
                launched = True
        except Exception:
            pass

    if not launched:
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

    if not launched:
        try:
            startfile_fn = getattr(os, "startfile", None)
            if callable(startfile_fn):
                startfile_fn(uri or "spotify:")
                launched = True
        except Exception:
            pass

    if _cancellable_sleep(0.8 if was_running else 2.2):
        return False

    _focus_spotify_window(retries=10, maximize=True)
    return launched


def open_spotify_app() -> None:
    speak("Opening Spotify, Sir.")
    if not is_cancelled():
        _launch_spotify_app()


def play_on_spotify(song_query: str) -> None:
    global music_playing, spotify_playing
    song = song_query.strip()
    if not song:
        speak("Please tell me the song name to play on Spotify, Sir.")
        return

    speak(f"Playing {song} on Spotify, Sir.")
    if is_cancelled():
        return
    was_running = _is_spotify_running()
    _launch_spotify_app()

    if pyautogui is not None:
        if _cancellable_sleep(0.8 if was_running else 3.2):
            return
        focused = _focus_spotify_window(retries=8, maximize=True)
        if _cancellable_sleep(0.35):
            return
        # HARD SAFETY GUARD: only send Ctrl+K / Shift+Enter if Spotify is confirmed as the active foreground window
        if focused and _is_spotify_foreground():
            try:
                pyautogui.press("esc")
                time.sleep(0.15)
                pyautogui.hotkey("ctrl", "k")
                if _cancellable_sleep(0.6):
                    return
                pyautogui.hotkey("ctrl", "a")
                time.sleep(0.1)
                pyautogui.press("backspace")
                time.sleep(0.1)
                pyautogui.write(song, interval=0.03)
                if _cancellable_sleep(1.6):
                    return
                if _is_spotify_foreground():
                    pyautogui.hotkey("shift", "enter")
                    time.sleep(0.25)
                    pyautogui.press("esc")
            except Exception as err:
                print(f"Spotify automation warning: {err}")
        else:
            # Safe fallback: open Spotify directly to the search page without sending stray keystrokes
            try:
                startfile_fn = getattr(os, "startfile", None)
                if callable(startfile_fn):
                    startfile_fn(f"spotify:search:{urllib.parse.quote(song)}")
            except Exception:
                pass

    music_playing = True
    spotify_playing = True


def _extract_spotify_song(raw_command: str) -> str | None:
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


def processcommand(c: str, tz_name: str | None = None, tz_offset_min: int | None = None) -> bool:
    global music_playing, spotify_playing
    clear_cancel()
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
    if command in {"use ollama", "switch to ollama", "ollama mode"}:
        set_ai_provider("ollama")
        speak(f"Switched to local Ollama using {DEFAULT_OLLAMA_MODEL}, Sir.")
        return False
    if command in {"use gemini", "switch to gemini", "gemini mode"}:
        set_ai_provider("gemini")
        speak("Switched to Gemini cloud mode, Sir.")
        return False
    if command in {"use auto", "auto ai", "auto mode"}:
        set_ai_provider("auto")
        speak("Switched to automatic AI routing, Sir.")
        return False
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
        speak(current_datetime_response(command, tz_name=tz_name, tz_offset_min=tz_offset_min))
        return False

    # Persona & memory voice commands
    if command in {"coder mode", "coding mode", "switch to coder", "be a coder"}:
        set_persona("coder")
        speak("Switched to Coding Buddy mode, Sir.")
        return False
    if command in {"tutor mode", "study mode", "switch to tutor", "study tutor"}:
        set_persona("tutor")
        speak("Switched to Study Tutor mode, Sir.")
        return False
    if command in {"butler mode", "jarvis mode", "normal mode", "default mode"}:
        set_persona("butler")
        speak("Back to standard Jarvis Butler mode, Sir.")
        return False
    if command in {"clear memory", "forget conversation", "reset memory"}:
        clear_memory()
        speak("Conversation memory cleared, Sir.")
        return False

    # Screen Vision ("what's on my screen", "read my screen", "explain my screen")
    if any(p in command for p in ("on my screen", "look at my screen", "read my screen", "explain my screen", "see my screen", "analyze my screen")):
        ans = extras.analyze_screen(
            raw,
            ollama_url=OLLAMA_BASE_URL,
            gemini_key=_get_api_key(),
            genai_module=genai,
            types_module=types,
        )
        if not is_cancelled():
            speak(ans)
        return False

    # Clipboard tools
    if any(p in command for p in ("summarize my clipboard", "explain my clipboard", "summarize what i copied", "explain what i copied")):
        clip = extras.get_clipboard_text()
        if not clip:
            speak("Your clipboard is empty, Sir.")
        else:
            aiprocess(f"Summarize this clipboard text clearly in 2 to 3 sentences: {clip[:3000]}")
        return False
    if any(p in command for p in ("read my clipboard", "what is in my clipboard", "what did i copy")):
        clip = extras.get_clipboard_text()
        speak(f"Your clipboard says: {clip[:320]}" if clip else "Your clipboard is empty, Sir.")
        return False

    # Timers
    if "timer" in command and any(w in command for w in ("set", "start", "create")):
        secs, label = extras.parse_timer_seconds(raw)
        if secs:
            extras.add_timer(label, secs)
            mins = secs // 60
            rem = secs % 60
            dur_txt = f"{mins} minute{'s' if mins != 1 else ''}" + (f" and {rem} seconds" if rem else "") if mins else f"{rem} seconds"
            speak(f"Timer set for {dur_txt}, Sir.")
        else:
            speak("Tell me how long the timer should be, Sir—for example, set a 5 minute timer.")
        return False

    # Quick Notes
    note_match = re.match(r"^(?:note down|take a note|add a? ?note|remember that)\s+(.+)$", raw, flags=re.IGNORECASE)
    if note_match:
        note_txt = note_match.group(1).strip()
        extras.add_note(note_txt)
        speak(f"Noted: {note_txt}")
        return False
    if command in {"read my notes", "show my notes", "list notes", "my notes"}:
        notes = extras.list_notes()
        if not notes:
            speak("You don't have any saved notes yet, Sir.")
        else:
            preview = "; ".join(n["text"] for n in notes[:4])
            speak(f"You have {len(notes)} notes. Latest: {preview}")
        return False

    # PC Controls & Telemetry
    if any(p in command for p in ("take a screenshot", "capture screen", "screenshot")):
        path, _ = extras.capture_screenshot(save=True)
        speak("Screenshot saved, Sir." if path else "I couldn't take a screenshot, Sir. Make sure Pillow is installed.")
        return False
    if command in {"lock screen", "lock my pc", "lock computer", "lock laptop"}:
        speak("Locking your screen, Sir.")
        extras.lock_screen()
        return False
    if any(p in command for p in ("battery", "system status", "pc status", "cpu usage", "ram usage")):
        st = extras.get_system_stats()
        parts = []
        if st["cpu"] is not None:
            parts.append(f"CPU is at {st['cpu']}%")
        if st["ram_pct"] is not None:
            parts.append(f"RAM is at {st['ram_pct']}% ({st['ram_used_gb']} of {st['ram_total_gb']} GB)")
        if st["battery_pct"] is not None:
            plug = "and charging" if st["battery_plugged"] else "on battery"
            parts.append(f"battery is at {st['battery_pct']}% {plug}")
        speak((", ".join(parts) + ", Sir.") if parts else "System telemetry isn't available yet—install psutil, Sir.")
        return False

    vol_set = re.search(r"(?:set\s+)?volume\s+(?:to\s+)?(\d{1,3})", command)
    if vol_set:
        lvl = max(0, min(100, int(vol_set.group(1))))
        extras.set_volume(lvl)
        speak(f"Volume set to {lvl} percent, Sir.")
        return False
    if "volume up" in command or "increase volume" in command:
        extras.adjust_volume("up", 5)
        speak("Turned volume up, Sir.")
        return False
    if "volume down" in command or "decrease volume" in command or "lower volume" in command:
        extras.adjust_volume("down", 5)
        speak("Turned volume down, Sir.")
        return False
    if command in {"mute", "mute volume", "unmute", "unmute volume"}:
        extras.adjust_volume("mute", 1)
        speak("Toggled mute, Sir.")
        return False

    br_set = re.search(r"(?:set\s+)?brightness\s+(?:to\s+)?(\d{1,3})", command)
    if br_set:
        lvl = max(0, min(100, int(br_set.group(1))))
        extras.set_brightness(lvl)
        speak(f"Brightness set to {lvl} percent, Sir.")
        return False

    if command.startswith("close "):
        closed = extras.close_app(command[6:])
        if closed:
            speak(f"Closed {closed}, Sir.")
            return False

    if command.startswith("open ") and "spotify" not in command:
        launched = extras.launch_app(command[5:])
        if launched:
            speak(f"Opening {launched}, Sir.")
            return False

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
            if is_cancelled():
                return False
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
    active = False
    while True:
        print("jarvis active — listening..." if active else "standby — say 'Jarvis' to activate...")
        try:
            with sr.Microphone() as source:
                if not calibrated:
                    r.adjust_for_ambient_noise(source, duration=0.5)
                    calibrated = True
                audio = r.listen(source, timeout=6 if active else 4, phrase_time_limit=12 if active else 6)
            word = r.recognize_google(audio)
            print(repr(word))
            if not active:
                match = WAKE_WORD_PATTERN.search(word)
                if not match:
                    continue
                active = True
                inline_cmd = word[match.end() :].lstrip(" ,.!?:;-").strip()
                if not inline_cmd:
                    speak("Yes Sir, I am active.")
                    continue
                command = inline_cmd
            else:
                command = word.strip()

            if not command:
                continue
            if processcommand(command):
                active = False
        except (sr.WaitTimeoutError, sr.UnknownValueError):
            continue
        except KeyboardInterrupt:
            speak("Shutting down, Sir.")
            break
        except Exception as e:
            print(f"google error; {e}")