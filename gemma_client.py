"""The only module that calls Gemma. Every feature uses ask_text / ask_json."""
import json
import os
import re

from dotenv import load_dotenv
from google import genai

import config

load_dotenv()

_client = None
_json_mode_ok = True  # flipped to False if the API rejects response_mime_type


class GemmaError(Exception):
    """Raised when Gemma fails; the UI shows it with st.error(...)."""


def _get_client():
    global _client
    if _client is None:
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise GemmaError("GEMINI_API_KEY is missing. Add it to your .env file.")
        _client = genai.Client(api_key=key)
    return _client


# Pictographs, symbols and joiners that render as emoji. Plain punctuation (dashes, bullets) is kept.
_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿⌀-⏿←-⇿️‍]+")


def strip_emoji(text):
    """Safety net: remove emoji from model output even if the 'no emojis' instruction is ignored."""
    return _EMOJI.sub("", text)


def _call(prompt, images=None, json_mode=False):
    """One raw API call. Images are PIL.Image objects placed next to the prompt text."""
    global _json_mode_ok
    # Shared instruction for every prompt in the app
    contents = [prompt + "\n\nDo not use emojis."] + list(images or [])
    cfg = None
    if json_mode and _json_mode_ok:
        cfg = {"response_mime_type": "application/json"}
    try:
        resp = _get_client().models.generate_content(
            model=config.MODEL_ID, contents=contents, config=cfg
        )
    except GemmaError:
        raise
    except Exception as e:
        if cfg is not None:
            # Gemma may not support JSON mode: stop using it and rely on the prompt alone.
            _json_mode_ok = False
            return _call(prompt, images, json_mode=False)
        raise GemmaError(f"Gemma API call failed: {e}")
    return strip_emoji(resp.text or "")


def ask_text(prompt: str, images: list | None = None) -> str:
    return _call(prompt, images).strip()


def _parse_json(text: str):
    """Strip ```json fences, then parse. Raises ValueError if it still isn't JSON."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    # Gemma sometimes wraps the one object we asked for in a list: [{...}]. Every schema here is an object.
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
        raise GemmaError("Gemma returned invalid JSON twice. Please try again.")
