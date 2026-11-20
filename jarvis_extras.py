# pyright: reportMissingImports=false, reportMissingModuleSource=false, reportOptionalMemberAccess=false, reportAttributeAccessIssue=false, reportGeneralTypeIssues=false
"""
jarvis_extras.py - Interactive Windows PC controls, live telemetry, Screen Vision,
Clipboard tools, Personas, and persistent Notes & Timers for J.A.R.V.I.S.
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.request
import uuid
from typing import Any

try:
    import psutil  # type: ignore[import-not-found]
except Exception:
    psutil = None

try:
    from PIL import ImageGrab  # type: ignore[import-not-found]
except Exception:
    ImageGrab = None

try:
    import pyautogui  # type: ignore[import-not-found]
except Exception:
    pyautogui = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "jarvis_data.json")
SCREENSHOT_DIR = os.path.join(BASE_DIR, "screenshots")

_data_lock = threading.Lock()
_current_persona: str = os.getenv("JARVIS_PERSONA", "butler").strip().lower() or "butler"

PERSONAS: dict[str, dict[str, str]] = {
    "butler": {
        "name": "Butler",
        "prompt": (
            "You are Jarvis, a sharp, warm, and witty personal AI assistant. "
            "Respond in 1 to 3 concise spoken sentences with plain text only (no markdown, bullets, or asterisks). "
            "Address the user as Sir when natural."
        ),
    },
    "coder": {
        "name": "Coder",
        "prompt": (
            "You are Jarvis in Coding Buddy mode—a crisp, practical software engineer. "
            "Give direct, actionable answers for Python, web dev, debugging, and tools in 2 to 4 clear sentences. "
            "Avoid filler and keep explanations easy to follow."
        ),
    },
    "tutor": {
        "name": "Study Tutor",
        "prompt": (
            "You are Jarvis in Study Tutor mode—a clear, encouraging engineering and science tutor. "
            "Break concepts down step by step with simple real-world analogies in 2 to 4 plain sentences."
        ),
    },
}

if _current_persona not in PERSONAS:
    _current_persona = "butler"


def get_persona() -> str:
    return _current_persona


def set_persona(mode: str) -> str:
    global _current_persona
    clean = str(mode or "").strip().lower()
    aliases = {
        "jarvis": "butler",
        "default": "butler",
        "code": "coder",
        "coding": "coder",
        "dev": "coder",
        "study": "tutor",
        "teacher": "tutor",
    }
    clean = aliases.get(clean, clean)
    if clean in PERSONAS:
        _current_persona = clean
    return _current_persona


def get_system_instruction() -> str:
    return PERSONAS.get(_current_persona, PERSONAS["butler"])["prompt"]


# --- Persistent Notes & Timers (jarvis_data.json) ---
def _load_data() -> dict[str, Any]:
    default_data: dict[str, Any] = {"notes": [], "timers": []}
    if not os.path.isfile(DATA_FILE):
        return default_data
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as fh:
            parsed = json.load(fh)
            if isinstance(parsed, dict):
                return {
                    "notes": list(parsed.get("notes") or []),
                    "timers": list(parsed.get("timers") or []),
                }
    except Exception:
        pass
    return default_data


def _save_data(data: dict[str, Any]) -> None:
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    except Exception:
        pass


def list_notes() -> list[dict[str, Any]]:
    with _data_lock:
        return list(_load_data()["notes"])


def add_note(text: str) -> dict[str, Any]:
    clean = str(text or "").strip()
    note = {
        "id": uuid.uuid4().hex[:8],
        "text": clean,
        "created_at": time.strftime("%I:%M %p · %b %d"),
    }
    with _data_lock:
        data = _load_data()
        data["notes"].insert(0, note)
        data["notes"] = data["notes"][:50]
        _save_data(data)
    return note


def delete_note(note_id: str) -> bool:
    with _data_lock:
        data = _load_data()
        before = len(data["notes"])
        data["notes"] = [n for n in data["notes"] if n.get("id") != note_id]
        _save_data(data)
        return len(data["notes"]) < before


def list_timers() -> list[dict[str, Any]]:
    now = time.time()
    with _data_lock:
        data = _load_data()
        active = [t for t in data["timers"] if float(t.get("ends_at", 0)) > now - 5]
        if len(active) != len(data["timers"]):
            data["timers"] = active
            _save_data(data)
        return active


def add_timer(label: str, seconds: int) -> dict[str, Any]:
    secs = max(5, min(86400, int(seconds)))
    now = time.time()
    timer = {
        "id": uuid.uuid4().hex[:8],
        "label": str(label or "Timer").strip() or "Timer",
        "duration": secs,
        "started_at": now,
        "ends_at": now + secs,
    }
    with _data_lock:
        data = _load_data()
        data["timers"].append(timer)
        _save_data(data)
    return timer


def cancel_timer(timer_id: str) -> bool:
    with _data_lock:
        data = _load_data()
        before = len(data["timers"])
        data["timers"] = [t for t in data["timers"] if t.get("id") != timer_id]
        _save_data(data)
        return len(data["timers"]) < before


def parse_timer_seconds(text: str) -> tuple[int | None, str]:
    """Parse phrases like 'set a 5 minute timer for coffee' -> (300, 'coffee')."""
    low = text.lower()
    total = 0
    for val, unit in re.findall(r"(\d+)\s*(hours?|hrs?|hr|h|minutes?|mins?|min|m|seconds?|secs?|sec|s)\b", low):
        n = int(val)
        if unit.startswith("h"):
            total += n * 3600
        elif unit.startswith("m"):
            total += n * 60
        else:
            total += n
    if total <= 0:
        return None, "Timer"
    label_match = re.search(r"\b(?:for|called|named)\s+(.+)$", text, flags=re.IGNORECASE)
    label = label_match.group(1).strip() if label_match else "Focus Timer"
    # Avoid capturing the duration itself as the label
    if re.fullmatch(r"\d+\s*(?:hours?|hrs?|minutes?|mins?|seconds?|secs?)", label, flags=re.IGNORECASE):
        label = "Focus Timer"
    return total, label


# --- Live PC Telemetry & Windows Controls ---
def _run_ps(script: str, timeout: float = 3.5) -> str:
    if os.name != "nt":
        return ""
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", script],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return (res.stdout or "").strip()
    except Exception:
        return ""


def get_brightness() -> int | None:
    if os.name != "nt":
        return None
    out = _run_ps(
        "(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness -ErrorAction SilentlyContinue | Select-Object -First 1).CurrentBrightness",
        timeout=2.5,
    )
    try:
        return int(out)
    except Exception:
        return None


def set_brightness(level: int) -> bool:
    pct = max(0, min(100, int(level)))
    if os.name != "nt":
        return False
    _run_ps(
        f"$m = Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods -ErrorAction SilentlyContinue | Select-Object -First 1; "
        f"if ($m) {{ Invoke-CimMethod -InputObject $m -MethodName WmiSetBrightness -Arguments @{{Timeout=1; Brightness={pct}}} | Out-Null }}",
        timeout=3.0,
    )
    return True


def set_volume(level: int) -> bool:
    """Set Windows master volume (0-100) cleanly via CoreAudio COM in PowerShell."""
    pct = max(0, min(100, int(level)))
    if os.name != "nt":
        return False
    ps = (
        "Add-Type -TypeDefinition @'\n"
        "using System.Runtime.InteropServices;\n"
        "[Guid(\"5CDF2C82-841E-4546-9722-0CF74078229A\"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]\n"
        "interface IAudioEndpointVolume {\n"
        "  int f(); int g(); int h(); int i();\n"
        "  int SetMasterVolumeLevelScalar(float fLevel, System.Guid pguidEventContext);\n"
        "  int j(); int GetMasterVolumeLevelScalar(out float pfLevel);\n"
        "}\n"
        "[Guid(\"D666063F-1587-4E43-81F1-B948E807363F\"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]\n"
        "interface IMMDevice { int Activate(ref System.Guid id, int clsCtx, int activationParams, out IAudioEndpointVolume aev); }\n"
        "[Guid(\"A95664D2-9614-4F35-A746-DE8DB63617E6\"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]\n"
        "interface IMMDeviceEnumerator { int GetDefaultAudioEndpoint(int dataFlow, int role, out IMMDevice endpoint); }\n"
        "[ComImport, Guid(\"BCDE0395-E52F-467C-8E3D-C4579291692E\")] class MMDeviceEnumeratorComObject {}\n"
        "public class AudioCtl {\n"
        "  public static void SetVol(float v) {\n"
        "    var en = (IMMDeviceEnumerator)(new MMDeviceEnumeratorComObject());\n"
        "    IMMDevice dev; en.GetDefaultAudioEndpoint(0, 1, out dev);\n"
        "    var iid = typeof(IAudioEndpointVolume).GUID;\n"
        "    IAudioEndpointVolume ep; dev.Activate(ref iid, 23, 0, out ep);\n"
        "    ep.SetMasterVolumeLevelScalar(v, System.Guid.Empty);\n"
        "  }\n"
        "}\n"
        "'@; "
        f"[AudioCtl]::SetVol({pct / 100.0:.2f})"
    )
    _run_ps(ps, timeout=4.0)
    return True


def adjust_volume(direction: str, steps: int = 5) -> None:
    if pyautogui is not None:
        key = "volumeup" if direction == "up" else "volumedown" if direction == "down" else "volumemute"
        count = 1 if key == "volumemute" else max(1, steps)
        for _ in range(count):
            try:
                pyautogui.press(key)
            except Exception:
                break


def get_system_stats() -> dict[str, Any]:
    stats: dict[str, Any] = {
        "cpu": None,
        "ram_pct": None,
        "ram_used_gb": None,
        "ram_total_gb": None,
        "battery_pct": None,
        "battery_plugged": None,
        "brightness": get_brightness(),
        "persona": _current_persona,
    }
    if psutil is not None:
        try:
            stats["cpu"] = round(psutil.cpu_percent(interval=0.1))
            vm = psutil.virtual_memory()
            stats["ram_pct"] = round(vm.percent)
            stats["ram_used_gb"] = round(vm.used / (1024 ** 3), 1)
            stats["ram_total_gb"] = round(vm.total / (1024 ** 3), 1)
            batt = psutil.sensors_battery()
            if batt is not None:
                stats["battery_pct"] = round(batt.percent)
                stats["battery_plugged"] = bool(batt.power_plugged)
        except Exception:
            pass
    elif os.name == "nt":
        # Lightweight PowerShell fallback if psutil isn't installed yet
        out = _run_ps(
            "$c = (Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average; "
            "$o = Get-CimInstance Win32_OperatingSystem; "
            "$tot = [math]::Round($o.TotalVisibleMemorySize / 1MB, 1); "
            "$used = [math]::Round(($o.TotalVisibleMemorySize - $o.FreePhysicalMemory) / 1MB, 1); "
            "$rp = [math]::Round(($used / $tot) * 100); "
            "$b = Get-CimInstance Win32_Battery | Select-Object -First 1; "
            "$bp = if ($b) { $b.EstimatedChargeRemaining } else { -1 }; "
            "Write-Output \"$c|$rp|$used|$tot|$bp\"",
            timeout=3.0,
        )
        parts = out.split("|")
        if len(parts) == 5:
            try:
                stats["cpu"] = round(float(parts[0]))
                stats["ram_pct"] = int(parts[1])
                stats["ram_used_gb"] = float(parts[2])
                stats["ram_total_gb"] = float(parts[3])
                if int(parts[4]) >= 0:
                    stats["battery_pct"] = int(parts[4])
            except Exception:
                pass
    return stats


def lock_screen() -> bool:
    if os.name != "nt":
        return False
    try:
        subprocess.Popen(["rundll32.exe", "user32.dll,LockWorkStation"])
        return True
    except Exception:
        return False


def launch_app(app_name: str) -> str | None:
    low = app_name.lower().strip()
    apps: dict[str, tuple[str, list[str]]] = {
        "vs code": ("VS Code", ["cmd", "/c", "start", "", "code"]),
        "vscode": ("VS Code", ["cmd", "/c", "start", "", "code"]),
        "visual studio code": ("VS Code", ["cmd", "/c", "start", "", "code"]),
        "chrome": ("Google Chrome", ["cmd", "/c", "start", "", "chrome"]),
        "edge": ("Microsoft Edge", ["cmd", "/c", "start", "", "msedge"]),
        "notepad": ("Notepad", ["notepad.exe"]),
        "calculator": ("Calculator", ["calc.exe"]),
        "calc": ("Calculator", ["calc.exe"]),
        "explorer": ("File Explorer", ["explorer.exe"]),
        "file explorer": ("File Explorer", ["explorer.exe"]),
        "task manager": ("Task Manager", ["taskmgr.exe"]),
        "terminal": ("Windows Terminal", ["cmd", "/c", "start", "", "wt"]),
        "settings": ("Windows Settings", ["cmd", "/c", "start", "", "ms-settings:"]),
    }
    for key, (label, cmd) in apps.items():
        if key in low:
            if os.name == "nt":
                try:
                    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return label
                except Exception:
                    pass
    return None


def close_app(app_name: str) -> str | None:
    low = app_name.lower().strip()
    procs: dict[str, tuple[str, str]] = {
        "chrome": ("Google Chrome", "chrome.exe"),
        "edge": ("Microsoft Edge", "msedge.exe"),
        "notepad": ("Notepad", "notepad.exe"),
        "spotify": ("Spotify", "Spotify.exe"),
        "vs code": ("VS Code", "Code.exe"),
        "vscode": ("VS Code", "Code.exe"),
        "calculator": ("Calculator", "CalculatorApp.exe"),
    }
    for key, (label, exe) in procs.items():
        if key in low and os.name == "nt":
            try:
                subprocess.run(["taskkill", "/IM", exe, "/F"], capture_output=True, timeout=4, check=False)
                return label
            except Exception:
                pass
    return None


# --- Clipboard ---
def get_clipboard_text() -> str:
    if os.name == "nt":
        txt = _run_ps("Get-Clipboard -Raw", timeout=2.5)
        if txt:
            return txt.strip()
    try:
        import tkinter as tk  # built-in
        root = tk.Tk()
        root.withdraw()
        txt = root.clipboard_get()
        root.destroy()
        return str(txt).strip()
    except Exception:
        return ""


# --- Screenshot & Screen Vision ---
def capture_screenshot(save: bool = True) -> tuple[str | None, bytes | None]:
    """Capture desktop screenshot; returns (saved_path, jpeg_bytes)."""
    saved_path = None
    jpeg_bytes = None
    try:
        if ImageGrab is not None:
            img = ImageGrab.grab()
            if save:
                os.makedirs(SCREENSHOT_DIR, exist_ok=True)
                saved_path = os.path.join(SCREENSHOT_DIR, f"jarvis_{time.strftime('%Y%m%d_%H%M%S')}.png")
                img.save(saved_path)
            img.thumbnail((1280, 1280))
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="JPEG", quality=82)
            jpeg_bytes = buf.getvalue()
            return saved_path, jpeg_bytes
    except Exception:
        pass
    return saved_path, jpeg_bytes


def analyze_screen(
    question: str,
    ollama_url: str = "http://127.0.0.1:11434",
    gemini_key: str = "",
    genai_module: Any = None,
    types_module: Any = None,
) -> str:
    """Capture screen and ask Gemini or a local Ollama vision model to explain it."""
    saved_path, jpeg_bytes = capture_screenshot(save=False)
    if not jpeg_bytes:
        return "I couldn't capture your screen, Sir. Make sure Pillow is installed (pip install Pillow)."

    prompt = question.strip() or "Briefly describe what is on my screen and help if there is an error or question."

    # 1. Try Gemini Vision first if API key is present
    if gemini_key and genai_module is not None and types_module is not None:
        try:
            client = genai_module.Client(api_key=gemini_key)
            part = types_module.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg")
            resp = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[part, f"{get_system_instruction()}\n\nUser asks about their screen: {prompt}"],
            )
            txt = (getattr(resp, "text", None) or "").strip()
            if txt:
                return txt
        except Exception as err:
            print(f"Gemini vision warning: {err}")

    # 2. Try local Ollama vision model (e.g. gemma3:4b, llama3.2-vision, llava, minicpm-v)
    try:
        req = urllib.request.Request(f"{ollama_url}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            tags = json.loads(resp.read().decode("utf-8", errors="ignore"))
        installed = [str(m.get("name", "")) for m in (tags.get("models") or [])]
        vision_model = None
        for cand in ("gemma3:4b", "gemma3", "llama3.2-vision", "llava", "minicpm-v", "qwen2.5vl"):
            for name in installed:
                if name.lower().startswith(cand):
                    vision_model = name
                    break
            if vision_model:
                break
        if vision_model:
            b64 = base64.b64encode(jpeg_bytes).decode("ascii")
            payload = {
                "model": vision_model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": get_system_instruction()},
                    {"role": "user", "content": prompt, "images": [b64]},
                ],
                "options": {"num_predict": 180},
            }
            vreq = urllib.request.Request(
                f"{ollama_url}/api/chat",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(vreq, timeout=30) as vresp:
                parsed = json.loads(vresp.read().decode("utf-8", errors="ignore"))
                content = str((parsed.get("message") or {}).get("content") or "").strip()
                if content:
                    return content
    except Exception as err:
        print(f"Ollama vision warning: {err}")

    return (
        "Screen captured, Sir, but no vision model is active. "
        "Add a GEMINI_API_KEY in .env or run 'ollama pull gemma3:4b' for local screen vision."
    )
