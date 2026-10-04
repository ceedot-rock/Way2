"""Way2 — voice in and voice out.

Speech-to-text is local OpenAI Whisper (open-source, MIT license, runs
fully offline). Text-to-speech shells out to the `tts` CLI. Both are
optional: every voice function raises VoiceError with a plain-language
message when its engine isn't available, so the text loop keeps working.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

WHISPER_MODEL = os.environ.get("WAY2_WHISPER_MODEL", "tiny")
TTS_BIN = os.environ.get("WAY2_TTS_BIN", "/opt/hatch/bin/tts")


class VoiceError(Exception):
    """The voice engine isn't available or couldn't do the job."""


def whisper_available() -> bool:
    return shutil.which("whisper") is not None


def transcribe_file(path: str) -> str:
    """transcribe_file(path) -> str. Local Whisper CLI, English, tiny model.

    Raises VoiceError if Whisper isn't installed, the file can't be read,
    or no words were heard.
    """
    if not path or not os.path.exists(path):
        raise VoiceError(f"Couldn't find the audio file: {path}")
    whisper_bin = shutil.which("whisper")
    if whisper_bin is None:
        raise VoiceError(
            "The speech engine isn't installed here. "
            "Install it with `pip install openai-whisper`, or type your "
            "command instead.")
    tmpdir = tempfile.mkdtemp(prefix="way2-audio-")
    try:
        proc = subprocess.run(
            [whisper_bin, path,
             "--model", WHISPER_MODEL,
             "--language", "en",
             "--output_format", "txt",
             "--output_dir", tmpdir,
             "--fp16", "False"],
            capture_output=True, text=True, timeout=180)
        stem = os.path.splitext(os.path.basename(path))[0]
        txt_path = os.path.join(tmpdir, stem + ".txt")
        if proc.returncode != 0 or not os.path.exists(txt_path):
            detail = (proc.stderr or "").strip().splitlines()
            raise VoiceError(
                "Transcription failed: " + (detail[-1] if detail else "unknown error"))
        with open(txt_path, encoding="utf-8") as f:
            text = f.read().strip()
        if not text:
            raise VoiceError("I couldn't hear any words in that recording.")
        return text
    except subprocess.TimeoutExpired as e:
        raise VoiceError("Transcription took too long — try a shorter clip.") from e
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def listen(max_seconds: int = 10) -> str:
    """Record from the mic and transcribe. Falls back with a clear message
    when microphone capture isn't available in this environment."""
    arecord = shutil.which("arecord")
    if arecord is None:
        raise VoiceError(
            "Microphone capture isn't available in this environment. "
            "Save a voice recording as an audio file and I'll transcribe it — "
            "or just type your command.")
    tmp = tempfile.mktemp(prefix="way2-mic-", suffix=".wav")
    try:
        proc = subprocess.run(
            [arecord, "-d", str(max_seconds), "-f", "cd", "-t", "wav", tmp],
            capture_output=True, timeout=max_seconds + 10)
        if proc.returncode != 0 or not os.path.exists(tmp):
            raise VoiceError("Couldn't record from the microphone.")
        return transcribe_file(tmp)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def speak(text: str) -> str:
    """Speak text aloud. Returns the path of the synthesized audio file.

    Synthesizes with the `tts` CLI, then plays it back if an audio player
    (ffplay) is available. Raises VoiceError if synthesis fails.
    """
    text = (text or "").strip()
    if not text:
        raise VoiceError("Nothing to say.")
    if not (os.path.exists(TTS_BIN) or shutil.which(TTS_BIN)):
        raise VoiceError(
            "The speech voice isn't installed here. "
            "Your response is printed below instead.")
    out = tempfile.mktemp(prefix="way2-say-", suffix=".mp3")
    proc = subprocess.run(
        [TTS_BIN, "speak", "--text", text, "--output", out],
        capture_output=True, text=True, timeout=120)
    if proc.returncode != 0 or not os.path.exists(out):
        raise VoiceError("Couldn't synthesize speech.")
    player = shutil.which("ffplay")
    if player:
        # Best effort: don't let a headless box hang the conversation.
        subprocess.run([player, "-nodisp", "-autoexit", "-loglevel", "quiet", out],
                       timeout=120)
    return out
