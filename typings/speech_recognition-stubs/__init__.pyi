# pyright: reportMissingImports=false, reportMissingModuleSource=false, reportOptionalMemberAccess=false, reportAttributeAccessIssue=false, reportGeneralTypeIssues=false
from __future__ import annotations
"""
Type stub file for speech_recognition (Pylance / Pyright compatible).
"""

from collections.abc import Iterable
from typing import Any, Callable

__author__: str
__version__: str
__license__: str


class WaitTimeoutError(Exception): ...
class UnknownValueError(Exception): ...
class RequestError(Exception): ...
class TranscriptionNotReady(Exception): ...
class TranscriptionFailed(Exception): ...


class AudioData:
    frame_data: bytes
    sample_rate: int
    sample_width: int
    def __init__(self, frame_data: bytes, sample_rate: int, sample_width: int) -> None: ...
    def get_segment(self, start_ms: float | None = ..., end_ms: float | None = ...) -> AudioData: ...
    def get_raw_data(self, convert_rate: int | None = ..., convert_width: int | None = ...) -> bytes: ...
    def get_wav_data(self, convert_rate: int | None = ..., convert_width: int | None = ...) -> bytes: ...
    def get_aiff_data(self, convert_rate: int | None = ..., convert_width: int | None = ...) -> bytes: ...
    def get_flac_data(self, convert_rate: int | None = ..., convert_width: int | None = ...) -> bytes: ...


class AudioSource:
    def __init__(self) -> None: ...
    def __enter__(self) -> AudioSource: ...
    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None: ...


class Microphone(AudioSource):
    def __init__(
        self,
        device_index: int | None = ...,
        sample_rate: int | None = ...,
        chunk_size: int = ...,
    ) -> None: ...
    @staticmethod
    def get_pyaudio() -> Any: ...
    @staticmethod
    def list_microphone_names() -> list[str | None]: ...
    @staticmethod
    def list_working_microphones() -> dict[int, str]: ...
    def __enter__(self) -> Microphone: ...
    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None: ...


class AudioFile(AudioSource):
    def __init__(self, filename_or_fileobject: Any) -> None: ...
    def __enter__(self) -> AudioFile: ...
    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None: ...


WavFile = AudioFile


class Recognizer(AudioSource):
    energy_threshold: float
    dynamic_energy_threshold: bool
    dynamic_energy_adjustment_damping: float
    dynamic_energy_ratio: float
    pause_threshold: float
    operation_timeout: float | None
    phrase_threshold: float
    non_speaking_duration: float

    def __init__(self) -> None: ...
    def record(self, source: AudioSource, duration: float | None = ..., offset: float | None = ...) -> AudioData: ...
    def adjust_for_ambient_noise(self, source: AudioSource, duration: float = ...) -> None: ...
    def listen(
        self,
        source: AudioSource,
        timeout: float | None = ...,
        phrase_time_limit: float | None = ...,
        snowboy_configuration: tuple[str, Iterable[str]] | None = ...,
        stream: bool = ...,
    ) -> AudioData: ...
    def listen_in_background(
        self,
        source: AudioSource,
        callback: Callable[[Recognizer, AudioData], Any],
        phrase_time_limit: float | None = ...,
    ) -> Callable[[bool], None]: ...
    def recognize_google(
        self,
        audio_data: AudioData,
        key: str | None = ...,
        language: str = ...,
        show_all: bool = ...,
    ) -> str: ...
    def recognize_whisper(
        self,
        audio_data: AudioData,
        model: str = ...,
        show_dict: bool = ...,
        load_options: dict[str, Any] | None = ...,
        language: str | None = ...,
        translate: bool = ...,
        **transcribe_options: Any,
    ) -> str: ...
