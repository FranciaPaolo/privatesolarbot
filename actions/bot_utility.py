from ollama import AsyncClient, ResponseError
import logging
import re

logger = logging.getLogger(__name__)

class BotUtility:
    def __init__(self):
        self.llm = AsyncClient()  # talks to local Ollama (localhost:11434)

    @staticmethod
    def can_think(model: str) -> bool:
        m = model.lower()
        return "qwen3" in m and "instruct" not in m

    async def ask(self, model: str, system: str, user: str, **kwargs) -> str:
        thinking_model = self.can_think(model)
        if self.can_think(model):
            user = f"{user}\n/no_think"
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        extra = {"think": False} if thinking_model else {}

        try:
            resp = await self.llm.chat(
                model=model,
                messages=messages,
                keep_alive="30m",
                **extra,
                **kwargs,
            )
        except (TypeError, ResponseError):
            # only fall back for a genuine "think not supported" error
            logger.warning("Old Ollama client/server, retrying without 'think' option")
            resp = await self.llm.chat(model=model, messages=messages, keep_alive="30m", **kwargs)
        return self.strip_thinking(resp.message.content)

    # ---------- LLM helper: never lets reasoning through ----------
    @staticmethod
    def strip_thinking(text: str) -> str:
        """Remove any <think>...</think> block, or anything before a stray </think>."""
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        if "</think>" in text:
            text = text.split("</think>")[-1]
        return text.strip()