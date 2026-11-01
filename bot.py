"""
Telegram bot + LangGraph + Ollama + faster-whisper

Flow:
  text/voice -> (Whisper for voice/audio) -> agent (LLM + tool routing)
      -> solar-related prompt -> get_solar_status tool -> Tigo API -> summary
      -> unrelated prompt -> normal chat reply (no tool call)
"""
import asyncio
import json
import logging
import os
import tempfile
from pathlib import Path
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from faster_whisper import WhisperModel
from langgraph.graph import START, MessagesState, StateGraph
from langchain_core.messages import HumanMessage, SystemMessage, trim_messages
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from langchain_ollama import ChatOllama
from langgraph.prebuilt import ToolNode, tools_condition
from telegram import Chat, Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters
from telegram.constants import ChatAction
from telegram.ext import CommandHandler

from actions.solar_action import SolarAction
from actions.tigoapi import TigoApi
from actions.bot_utility import BotUtility
from logger.log_setup import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

# Silence the noisy libraries, keep your own logs at INFO
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# ---------- Config (loaded from the .env file next to bot.py) ----------
load_dotenv(Path(__file__).resolve().parent / ".env")

def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"Missing required variable '{name}' in your .env file.")
    return value


TELEGRAM_TOKEN = require_env("TELEGRAM_TOKEN")
ALLOWED_USER_IDS = {int(x) for x in require_env("ALLOWED_USER_ID").split(",")}
AGENT_MODEL = os.environ.get("AGENT_MODEL", "qwen3:4b-instruct-2507-q4_K_M")
WHISPER_SIZE = os.environ.get("WHISPER_SIZE", "small")
TIGO_API_TOKEN = os.environ.get("TIGO_API_TOKEN", None)
TIGO_SYSTEM_ID = os.environ.get("TIGO_SYSTEM_ID", None)

# Not yet used, but can be used to route between different LLMs for different tasks
# ROUTER_MODEL = os.environ.get("ROUTER_MODEL", "qwen3:4b") # determine the intent of the user message
# WRITER_MODEL = os.environ.get("WRITER_MODEL", "qwen3:8b") # response generation, summarization, rephrasing, etc.

solar_status = SolarAction(system_id=TIGO_SYSTEM_ID, tigo_api=TigoApi(token=TIGO_API_TOKEN))
whisper = WhisperModel(WHISPER_SIZE, device="cpu", compute_type="int8")
bot_utility = BotUtility()

def _num(value):
    try:
        return round(float(value), 1)
    except (TypeError, ValueError):
        return None

# ---------- Tools ----------
@tool
async def get_solar_status() -> str:
    """Get the live status of the user's home Tigo solar (photovoltaic) system:
    current production, energy produced today, battery level and usage,
    grid power and home consumption. Call this whenever the user asks about
    their solar panels, impianto, inverter, battery, production or energy."""
    try:
        logger.info("Calling Solar API with tool...")
        data = await asyncio.to_thread(solar_status.get_status)
        logger.info("Solar API response: %s", data)
    except Exception as exc:
        logger.exception("Solar API error: %s", exc)
        return json.dumps({"error": "Tigo API not reachable"})

    return json.dumps({
        "solar_production_now_kw": _num(data.get("solar_kw")),
        "produced_energy_today_kwh": _num(data.get("produced_energy_today_kwh")),
        "consumed_energy_today_kwh": _num(data.get("consumed_energy_today_kwh")),
        "battery_usage_kw": _num(data.get("battery_consumption_kw")),
        "battery_charge_pct": _num(data.get("battery_pct")),
        "grid_kw": _num(data.get("grid_kw")),
        "home_consumption_kw": _num(data.get("home_consumptions_kw")),
    })

TOOLS = [get_solar_status]

SYSTEM_PROMPT = """You are a friendly assistant chatting with the owner of a home solar system on Telegram.
- Always reply in the same language the user writes in (Italian or English).
- When the user asks about their solar panels, impianto, inverter, battery, production or energy,
  call the get_solar_status tool, then summarise the result in a short, readable message
  (you can use a few emojis and bullet points). Report only the numbers returned by the tool.
- If the tool returns an error, say that the Tigo API is not reachable right now.
- For anything else (shopping lists, notes, general questions), just chat normally and be concise.
  Never call the tool for unrelated topics (e.g. "la batteria del telefono", "il pannello della cucina").
- Never invent data. Plain text only, no markdown headers."""

llm = ChatOllama(
    model=AGENT_MODEL,
    temperature=0.3,
    keep_alive="30m",
    reasoning=False,  # qwen3: disable <think> output
)
llm_with_tools = llm.bind_tools(TOOLS)

async def agent(state: MessagesState) -> dict:
    # keep only the last ~20 messages so the context never grows unbounded
    history = trim_messages(
        state["messages"],
        strategy="last",
        max_tokens=20,
        token_counter=len,  # count messages, not tokens
        start_on="human",
        include_system=False,
    )
    response = await llm_with_tools.ainvoke([SystemMessage(SYSTEM_PROMPT)] + history)
    return {"messages": [response]}

@asynccontextmanager
async def typing(chat: Chat):
    """Show 'typing...' in Telegram for as long as the block is running.
    Telegram clears the indicator after ~5s, so it is refreshed every 4s."""

    async def keep_typing() -> None:
        while True:
            try:
                await chat.send_action(ChatAction.TYPING)
            except Exception:
                pass  # a failed indicator must never break the bot
            await asyncio.sleep(4)

    task = asyncio.create_task(keep_typing())
    try:
        yield
    finally:
        task.cancel()

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    thread_id = str(update.message.chat.id)
    await graph.checkpointer.adelete_thread(thread_id)
    await update.message.reply_text("🧹 Memory cleared, let's start fresh.")


builder = StateGraph(MessagesState)
builder.add_node("agent", agent)
builder.add_node("tools", ToolNode(TOOLS))
builder.add_edge(START, "agent")
builder.add_conditional_edges("agent", tools_condition)  # -> "tools" or END
builder.add_edge("tools", "agent")
graph = builder.compile(checkpointer=MemorySaver())  # per-chat memory (RAM)


# ---------- Telegram ----------
def transcribe(path: str) -> str:
    segments, _info = whisper.transcribe(path, vad_filter=True)
    return " ".join(s.text.strip() for s in segments).strip()


async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    text = msg.text

    async with typing(msg.chat):
        if msg.voice or msg.audio:
            logger.info("Transcribing audio...")
            media = msg.voice or msg.audio
            tg_file = await media.get_file()
            with tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, "audio.ogg")
                await tg_file.download_to_drive(path)
                text = await asyncio.to_thread(transcribe, path)
            if not text:
                await msg.reply_text("🎙️ I couldn't understand the audio.")
                return
            await msg.reply_text(f"🎙️ {text}")  # echo transcript to spot errors

        logger.info(f"Request... message: {text}")

        try:
            result = await graph.ainvoke(
                {"messages": [HumanMessage(text)]},
                config={
                    "configurable": {"thread_id": str(msg.chat.id)}, # per-chat memory
                    "recursion_limit": 8,  # guard against tool-call loops
                },
            )
            reply = bot_utility.strip_thinking(result["messages"][-1].content)
            logger.info(f"Replying... response: {reply}")
        except Exception as exc:
            logger.exception("Agent error: %s", exc)
            reply = ""
        await msg.reply_text(reply or "⚠️ No response, please try again.")


def main() -> None:
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    only_me = filters.User(user_id=ALLOWED_USER_IDS)

    # Handlers
    app.add_handler(CommandHandler("reset", reset, filters=only_me)) # reset memory via /reset chat command
    app.add_handler(
        MessageHandler(
            only_me & (filters.TEXT & ~filters.COMMAND | filters.VOICE | filters.AUDIO),
            handle
        )
    )
    app.run_polling()


if __name__ == "__main__":
    main()