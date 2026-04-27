import logging
from groq import Groq, RateLimitError
from config import settings

logger = logging.getLogger(__name__)

_keys = settings.groq_api_keys
_key_index = 0


def _next_key() -> str:
    global _key_index
    _key_index = (_key_index + 1) % len(_keys)
    return _keys[_key_index]


def chat_completion(messages: list, model: str = "llama-3.3-70b-versatile") -> str:
    """Call Groq chat completions, rotating to the next API key on rate-limit."""
    global _key_index
    tried = set()

    while len(tried) < len(_keys):
        key = _keys[_key_index]
        tried.add(_key_index)
        try:
            client = Groq(api_key=key)
            response = client.chat.completions.create(messages=messages, model=model)
            return response.choices[0].message.content
        except RateLimitError:
            logger.warning("Groq key index %d rate-limited, rotating.", _key_index)
            _next_key()

    raise RuntimeError("All Groq API keys are rate-limited.")
