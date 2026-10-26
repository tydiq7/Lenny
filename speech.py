"""Speech to text. Gemma 4 on the Gemini API does not accept audio ("Audio input modality is not
enabled for this model"), so voice answers are transcribed locally with faster-whisper (DESIGN.md's
fallback), and the transcript then goes to Gemma like any typed answer."""
import io
import wave

import numpy as np

MODEL_NAME = "base.en"  # small English model, ~150 MB, downloaded once on first use
_model = None


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


def transcribe(wav_bytes):
    """WAV bytes -> text. The first call loads (and the very first run downloads) the model."""
    global _model
    try:
        samples = _wav_to_samples(wav_bytes)
        if len(samples) < 16000 * 0.5:
            raise SpeechError("That recording was too short. Please try again.")
        if _model is None:
            from faster_whisper import WhisperModel  # imported here so the app starts even if it's missing
            _model = WhisperModel(MODEL_NAME, device="cpu", compute_type="int8")
        segments, _ = _model.transcribe(samples, language="en", vad_filter=True)
        text = " ".join(s.text.strip() for s in segments).strip()
    except SpeechError:
        raise
    except Exception as e:
        raise SpeechError(f"Could not transcribe the recording: {e}")
    if not text:
        raise SpeechError("I couldn't hear any speech in that recording. Please try again.")
    return text
