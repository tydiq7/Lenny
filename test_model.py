"""Check that the configured model works for all three input types Lenny uses.

Run: python test_model.py
Run this after setting up your API key, and again after changing models in config.py.
"""
import io
import math
import struct
import sys
import wave

from PIL import Image, ImageDraw

import config
import llm_client
import speech


def _test_image():
    """A tiny picture with a word on it, so we can check the model actually reads images."""
    img = Image.new("RGB", (240, 80), "white")
    ImageDraw.Draw(img).text((20, 30), "ELASTICITY", fill="black")
    return img


def _test_audio():
    """One second of a 440 Hz tone as a WAV file (checks the audio path works, not speech accuracy)."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * t / 16000)))
                               for t in range(16000)))
    return buf.getvalue()


checks = [
    ("text", lambda: llm_client.ask_text("Reply with the single word: ready")),
    ("json", lambda: llm_client.ask_json('Return {"status": "ok"}')),
    ("image", lambda: llm_client.ask_text("What single word is written in this image?", images=[_test_image()])),
]


def _check_audio():
    """Check whichever voice path config.AUDIO_SOURCE selects."""
    if config.AUDIO_SOURCE == "model":
        return llm_client._call("Describe this audio clip in one short sentence.", audio=_test_audio())
    # Local Whisper: the first run downloads the model (~150 MB), so it can take a minute.
    # The test clip is a tone, not speech, so an empty transcript still means Whisper works.
    text = speech._transcribe_locally(speech._wav_to_samples(_test_audio()))
    return f"local Whisper loaded and ran (transcript: {text!r})"


checks.append(("audio", _check_audio))

print(f"Model: {config.MODEL_ID}\nFallback: {config.FALLBACK_MODEL_ID}\nVoice: {config.AUDIO_SOURCE}\n")
failed = False
for name, run in checks:
    try:
        print(f"OK     {name:5s} -> {str(run())[:80]}")
    except ImportError:
        failed = True
        print(f"FAILED {name:5s} -> faster-whisper isn't installed: python -m pip install faster-whisper")
    except Exception as e:
        failed = True
        print(f"FAILED {name:5s} -> {e}")
sys.exit(1 if failed else 0)
