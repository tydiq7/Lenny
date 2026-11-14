"""The only module that calls the AI model. Every feature uses ask_text / ask_json / transcribe_audio.

It speaks the OpenAI-compatible chat API, which most providers (OpenRouter, Groq, Together,
a local Ollama or vLLM server, ...) accept. So switching model or provider is a change to
config.py, not to this file or any feature.
"""
import base64
import io
import json
import os
import re

from dotenv import load_dotenv
from openai import APIConnectionError, APIStatusError, OpenAI, RateLimitError

import config

load_dotenv()

_client = None
_json_mode_ok = {}  # model id -> False once that model rejects JSON mode


class LLMError(Exception):
    """Raised when the model call fails; the UI shows it with st.error(...)."""


def _api_key():
    """Read the key from the environment (.env locally), else from Streamlit secrets (when deployed)."""
    key = os.getenv(config.API_KEY_ENV)
    if not key:
        try:
            import streamlit as st
            key = st.secrets.get(config.API_KEY_ENV)
        except Exception:
            key = None
    if not key:
        raise LLMError(f"{config.API_KEY_ENV} is missing. Add it to your .env file (see README).")
    return key


def _get_client():
    """Create the API client once and reuse it."""
    global _client
    if _client is None:
        # max_retries=1: retry a dropped connection once, but don't burn free-tier requests on repeats
        _client = OpenAI(base_url=config.BASE_URL, api_key=_api_key(), max_retries=1)
    return _client


# Pictographs, symbols and joiners that render as emoji. Plain punctuation (dashes, bullets) is kept.
_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿⌀-⏿←-⇿️‍]+")


def strip_emoji(text):
    """Safety net: remove emoji from model output even if the 'no emojis' instruction is ignored."""
    return _EMOJI.sub("", text)


def _strip_thinking(text):
    """Reasoning models sometimes put their thinking inside <think>...</think>. Keep only the answer."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _image_part(img):
    """PIL image -> an image message part (base64 PNG data URL)."""
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}


def _audio_part(wav_bytes):
    """WAV bytes -> an audio message part (base64)."""
    return {"type": "input_audio", "input_audio": {"data": base64.b64encode(wav_bytes).decode(), "format": "wav"}}


def _build_messages(prompt, images=None, audio=None):
    """One user message: the prompt text, then any images, then any audio."""
    parts = [{"type": "text", "text": prompt + "\n\nDo not use emojis."}]
    parts += [_image_part(img) for img in (images or [])]
    if audio is not None:
        parts.append(_audio_part(audio))
    return [{"role": "user", "content": parts}]


def _friendly(e):
    """Turn an API exception into a message a student can act on."""
    if isinstance(e, RateLimitError):
        return ("Lenny runs on a free AI model with a request limit, and it's been reached. "
                "Wait a minute and try again.")
    if isinstance(e, APIConnectionError):
        return "Couldn't reach the AI model. Check your internet connection and try again."
    if isinstance(e, APIStatusError) and e.status_code in (401, 403):
        return f"The API key was rejected. Check {config.API_KEY_ENV} (see README)."
    return f"The AI model call failed: {e}"


def _call_model(model, messages, json_mode):
    """One raw API call to one model. Returns the answer text."""
    kwargs = {"model": model, "messages": messages, "max_tokens": config.MAX_TOKENS}
    use_json = json_mode and _json_mode_ok.get(model, True)
    if use_json:
        kwargs["response_format"] = {"type": "json_object"}
    try:
        resp = _get_client().chat.completions.create(**kwargs)
    except APIStatusError as e:
        if use_json and e.status_code == 400:
            # This model doesn't support JSON mode: remember that and rely on the prompt alone.
            _json_mode_ok[model] = False
            return _call_model(model, messages, json_mode=False)
        raise
    text = resp.choices[0].message.content or ""
    return strip_emoji(_strip_thinking(text))


def _call(prompt, images=None, audio=None, json_mode=False):
    """Try the main model; on failure try the fallback (unless the request has audio, which it can't take)."""
    messages = _build_messages(prompt, images, audio)
    models = [config.MODEL_ID]
    if config.FALLBACK_MODEL_ID and audio is None:
        models.append(config.FALLBACK_MODEL_ID)
    last_error = None
    for model in models:
        try:
            text = _call_model(model, messages, json_mode)
            if text:
                return text
            last_error = LLMError("The model returned an empty answer. Please try again.")
        except LLMError:
            raise
        except Exception as e:
            last_error = e
    raise last_error if isinstance(last_error, LLMError) else LLMError(_friendly(last_error))


def ask_text(prompt: str, images: list | None = None) -> str:
    """Ask for a plain-text answer. images: optional list of PIL images."""
    return _call(prompt, images).strip()


def _parse_json(text: str):
    """Strip ```json fences, then parse. Raises ValueError if it still isn't JSON."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    # Models sometimes wrap the one object we asked for in a list: [{...}]. Every schema here is an object.
    if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):
        data = data[0]
    return data


def ask_json(prompt: str, images: list | None = None):
    """Ask for JSON. Retries once with the bad output shown to the model."""
    full = prompt + "\n\nRespond with ONLY valid JSON matching the schema. No markdown, no commentary."
    raw = _call(full, images, json_mode=True)
    try:
        return _parse_json(raw)
    except ValueError:
        pass
    retry = "Your previous output was not valid JSON. Return only the corrected JSON:\n" + raw
    raw2 = _call(retry, json_mode=True)
    try:
        return _parse_json(raw2)
    except ValueError:
        raise LLMError("The model returned invalid JSON twice. Please try again.")


def transcribe_audio(wav_bytes: bytes) -> str:
    """Send a WAV recording to the model and get back a verbatim transcript."""
    prompt = ("Transcribe the attached recording of a student speaking, word for word. "
              "Do not fix mistakes, summarize, or answer anything they say. Output only the transcript.")
    return _call(prompt, audio=wav_bytes).strip()
