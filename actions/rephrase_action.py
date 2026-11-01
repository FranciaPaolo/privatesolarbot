import os
import logging
from actions.bot_state import State
from actions.bot_utility import BotUtility

# This action is not used
# it's for rephrasing messages to be shorter and more concise, using bullet points.
# for now the llm is used directly in bot.py, but this action can be used in the future if needed.

logger = logging.getLogger(__name__)

WRITER_MODEL = os.environ.get("WRITER_MODEL", "qwen3:8b")
bot_utility = BotUtility()

async def rephrase(state: State) -> State:
    text = state["text"]
    logger.info("Rephrasing: %s", text)
    # REPHRASE_PROMPT = """Rewrite the message in a short way use bullet points, in the same
    # language as the message. Keep only essential info, no commentary, do not invent details."""
    REPHRASE_PROMPT = """Rewrite the message as short bullet points, in the same language.

Rules:
- If items share the same action never repeat the verb in the bullet points.
- Keep names, times, dates and numbers exactly as written.
- Fix obvious typos. Do not invent details.
- No commentary.

Examples:

Message: Devo comprare latte, formaggio e patate
• latte,
• formaggio
• patate

Message: Domani devo chiamare Marco per il preventivo e poi passare in posta, ah e ricordami la riunione alle 15
• Chiamare Marco (preventivo), domani
• Passare in posta
• Riunione alle 15

Message: I need to send the report to Anna before Friday and book a table for four on Saturday
• Send report to Anna, by Friday
• Book table for 4, Saturday
"""

    reply = await bot_utility.ask(
        WRITER_MODEL,
        REPHRASE_PROMPT,
        text,
        options={"temperature": 0.2, "num_predict": 200},
    )
    logger.info("Rephrased: %s", reply)
    return {"reply": reply}
