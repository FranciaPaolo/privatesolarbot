import os
import time
import logging
from langgraph.graph.state import CompiledStateGraph
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

IDLE_RESET_SECONDS = int(os.environ.get("IDLE_RESET_HOURS", "4")) * 3600
_last_seen: dict[str, float] = {}  # thread_id -> last message timestamp

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    graph = context.application.bot_data["graph"]
    thread_id = str(update.message.chat.id)
    await graph.checkpointer.adelete_thread(thread_id)
    await update.message.reply_text("🧹 Memory cleared, let's start fresh.")

async def reset_if_idle(thread_id: str, graph:CompiledStateGraph) -> bool:
    """Clear the chat memory if the last message was more than IDLE_RESET_SECONDS ago.
    Returns True if a reset happened."""
    now = time.monotonic()
    last = _last_seen.get(thread_id)
    _last_seen[thread_id] = now
    if last is not None and now - last > IDLE_RESET_SECONDS:
        await graph.checkpointer.adelete_thread(thread_id)
        logger.info("Chat %s idle for >%ss, memory cleared", thread_id, IDLE_RESET_SECONDS)
        return True
    return False