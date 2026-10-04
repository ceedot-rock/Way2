"""Unit tests for way2/voice.py — engines are faked; no audio hardware.

Run:  python3 -m unittest discover -s tests -v
"""

import os
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from way2 import voice
from way2.voice import VoiceError


def _make_fake_whisper(tmpdir, transcript="hello world"):
    """A fake `whisper` executable that writes a .txt like the real CLI."""
    path = os.path.join(tmpdir, "whisper")
    with open(path, "w") as f:
        f.write("#!/bin/sh\n"
                "outdir=\"$9\"\n"          # --output_dir value position
                "base=$(basename \"$1\")\n"
                "stem=${base%.*}\n"
                "echo \"" + transcript + "\" > \"$outdir/$stem.txt\"\n")
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
    return path


class TestTranscribeFile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_missing_file(self):
        with self.assertRaises(VoiceError) as ctx:
            voice.transcribe_file("/nope/not-here.wav")
        self.assertIn("Couldn't find", str(ctx.exception))

    @patch("shutil.which", return_value=None)
    def test_no_whisper_gives_plain_language_error(self, _):
        fake = os.path.join(self.tmp, "note.wav")
        open(fake, "wb").write(b"RIFF....")
        with self.assertRaises(VoiceError) as ctx:
            voice.transcribe_file(fake)
        self.assertIn("pip install openai-whisper", str(ctx.exception))

    def test_transcribe_with_fake_whisper(self):
        fake_whisper = _make_fake_whisper(self.tmp, "take the next exit")
        audio = os.path.join(self.tmp, "note.wav")
        open(audio, "wb").write(b"RIFF....")
        with patch("shutil.which", return_value=fake_whisper):
            self.assertEqual(voice.transcribe_file(audio), "take the next exit")

    def test_empty_transcript_is_an_error(self):
        fake_whisper = _make_fake_whisper(self.tmp, "")
        audio = os.path.join(self.tmp, "note.wav")
        open(audio, "wb").write(b"RIFF....")
        with patch("shutil.which", return_value=fake_whisper):
            with self.assertRaises(VoiceError) as ctx:
                voice.transcribe_file(audio)
            self.assertIn("couldn't hear any words", str(ctx.exception).lower())


class TestListen(unittest.TestCase):
    @patch("shutil.which", return_value=None)
    def test_no_mic_gives_fallback(self, _):
        with self.assertRaises(VoiceError) as ctx:
            voice.listen()
        msg = str(ctx.exception)
        self.assertIn("Microphone capture isn't available", msg)
        self.assertIn("type your command", msg)


class TestSpeak(unittest.TestCase):
    def test_empty_text(self):
        with self.assertRaises(VoiceError):
            voice.speak("   ")

    def test_missing_tts_bin(self):
        with patch.dict(os.environ, {"WAY2_TTS_BIN": "/nope/tts"}):
            # re-read env override the way the module does
            with patch("way2.voice.TTS_BIN", "/nope/tts"):
                with self.assertRaises(VoiceError) as ctx:
                    voice.speak("hello")
                self.assertIn("isn't installed", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
