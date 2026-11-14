"""Speech to text for voice answers (blurt, Feynman).

By default (config.AUDIO_SOURCE = "whisper") recordings are transcribed on this computer with
faster-whisper, an open-source Whisper model: free, private, and no API call. Set
AUDIO_SOURCE = "model" to send audio to the AI model instead (OpenRouter needs a $0.50+ credit
balance for that); local Whisper is then used as a fallback if the model call fails.
"""
import io
import wave

import numpy as np

import config
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


def _local_or_error(samples, message_if_missing):
    """Transcribe with local Whisper; if it isn't installed, raise SpeechError with the given message."""
    try:
        return _transcribe_locally(samples)
    except ImportError:
        raise SpeechError(message_if_missing)
    except Exception as e:
        raise SpeechError(f"Could not transcribe the recording: {e}")


def transcribe(wav_bytes):
    """WAV bytes -> text, using local Whisper or the AI model depending on config.AUDIO_SOURCE."""
    try:
        samples = _wav_to_samples(wav_bytes)
    except SpeechError:
        raise
    except Exception:
        raise SpeechError("Couldn't read that recording. Please record again.")
    if len(samples) < 16000 * 0.5:
        raise SpeechError("That recording was too short. Please try again.")

    if config.AUDIO_SOURCE == "model":
        try:
            text = llm_client.transcribe_audio(wav_bytes)
        except llm_client.LLMError as model_error:
            text = _local_or_error(samples, str(model_error))
    else:
        text = _local_or_error(samples, "Voice needs faster-whisper: run  python -m pip install faster-whisper")
    if not text:
        raise SpeechError("I couldn't hear any speech in that recording. Please try again.")
    return text
