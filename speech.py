"""Speech to text for voice answers (blurt, Feynman).

The main model (see config.py) accepts audio directly, so the recording is sent to it for a
transcript. If that fails (e.g. the free model is rate-limited) and faster-whisper is installed,
the recording is transcribed locally instead. faster-whisper is optional: install it with
`pip install faster-whisper` if you want the offline fallback.
"""
import io
import wave

import numpy as np

import llm_client

WHISPER_MODEL = "base.en"  # small English model, ~150 MB, downloaded once on first use
_whisper = None


class SpeechError(Exception):
    """Raised when the recording can't be transcribed; the UI shows it with st.error(...)."""


def _wav_to_samples(wav_bytes):
    """Decode a 16-bit PCM WAV (what st.audio_input records) to mono float32 at 16 kHz,
    which is what Whisper expects. Done by hand so we don't depend on ffmpeg/PyAV."""
    with wave.open(io.BytesIO(wav_bytes)) as w:
        rate, channels, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        frames = w.readframes(w.getnframes())
    if width != 2:
        raise SpeechError("Unsupported audio format; please record again.")
    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)  # mix down to mono
    if rate != 16000:
        # Simple linear resampling is plenty for speech
        n = int(len(audio) * 16000 / rate)
        audio = np.interp(np.linspace(0, len(audio) - 1, n), np.arange(len(audio)), audio).astype(np.float32)
    return audio


def _transcribe_locally(samples):
    """Offline fallback with faster-whisper. Raises ImportError if it isn't installed."""
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel  # optional dependency
        _whisper = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
    segments, _ = _whisper.transcribe(samples, language="en", vad_filter=True)
    return " ".join(s.text.strip() for s in segments).strip()


def transcribe(wav_bytes):
    """WAV bytes -> text. Tries the AI model first, then local Whisper if available."""
    try:
        samples = _wav_to_samples(wav_bytes)
    except SpeechError:
        raise
    except Exception:
        raise SpeechError("Couldn't read that recording. Please record again.")
    if len(samples) < 16000 * 0.5:
        raise SpeechError("That recording was too short. Please try again.")

    try:
        text = llm_client.transcribe_audio(wav_bytes)
    except llm_client.LLMError as model_error:
        try:
            text = _transcribe_locally(samples)
        except ImportError:
            raise SpeechError(str(model_error))
        except Exception as e:
            raise SpeechError(f"Could not transcribe the recording: {e}")
    if not text:
        raise SpeechError("I couldn't hear any speech in that recording. Please try again.")
    return text
