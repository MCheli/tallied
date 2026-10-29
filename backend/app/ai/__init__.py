"""Claude integration: one client, model ids from settings, structured outputs, usage logging."""
from app.ai.client import AIError, AIUnavailable, ai_available, chat, extract, model_for  # noqa: F401
