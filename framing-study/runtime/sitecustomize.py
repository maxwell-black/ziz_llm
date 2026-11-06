"""Child-interpreter routing for the native OpenAI model id.

Harbor and tests/judge.py call litellm with ``openai/gpt-5.4-mini``.
This study has an OpenRouter key and no platform.openai.com key, so the
id is aliased to OpenRouter inside the child process. Anthropic and
Gemini keep their own endpoints. Loaded only when this directory is on
PYTHONPATH.
"""

import os

if os.environ.get("OPENROUTER_API_KEY"):
    try:
        import litellm

        litellm.model_alias_map["openai/gpt-5.4-mini"] = "openrouter/openai/gpt-5.4-mini"
    except Exception:
        pass
