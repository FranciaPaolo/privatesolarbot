# Telegram Local AI Assistant

A private Telegram bot that runs on your own machine (not AI Agencies, everything local). Send it text or voice messages:

- Ask about your **Tigo solar system** and it replies with a short live summary (production, battery, grid, consumption).
- Ask anything else and it just chats back.

The LLM and speech-to-text run locally. The only external services are Telegram and the Tigo API.

## How it works

```
Telegram (text / voice)
        │
        ▼
 [voice only] faster-whisper → transcript
        │
        ▼
 LangGraph agent (Ollama LLM) ──► needs solar data? ──► get_solar_status tool ──► Tigo API
        │
        ▼
   Reply in Telegram
```

| Part | Tool |
|------|------|
| Bot | `python-telegram-bot` |
| Speech-to-text | `faster-whisper` |
| LLM runtime | Ollama (default `qwen3:4b-instruct-2507-q4_K_M`) |
| Orchestration | LangGraph (agent + tool node, per-chat memory) |

Only the Telegram user IDs you whitelist can use the bot. For voice messages, the bot first echoes the transcript so you can spot errors.

## Setup

### 1. Prerequisites

- Python 3.10+
- [Ollama](https://ollama.com/download) installed and running
- A Tigo account with API access (token and system ID)

### 2. Pull the model

```bash
ollama pull qwen3:4b-instruct-2507-q4_K_M
```
Based on your hardware you can select a larger model, for now I start small, even with a non-thinking model to have better performance.

### 3. Create a Python environment and install dependencies

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Or with conda:

```bash
conda create -p venv python=3.12
conda activate ./venv
pip install -r requirements.txt
```

### 4. Set up Telegram

1. **Bot token**: open [@BotFather](https://t.me/BotFather), send `/newbot`, follow the prompts, and copy the token it gives you.
2. **Your user ID**: open [@userinfobot](https://t.me/userinfobot), send any message, and copy the numeric `Id`.
3. Start a chat with your new bot and press **Start**, otherwise it can't message you.

### 5. Create the `.env` file

Create `.env` in the same folder as `bot.py`. No quotes, no `export`:

```env
TELEGRAM_TOKEN=123456:ABC...
ALLOWED_USER_ID=123456789        # several users: 123456789,987654321

TIGO_API_TOKEN=your_tigo_token
TIGO_SYSTEM_ID=123

AGENT_MODEL=qwen3:4b-instruct-2507-q4_K_M
WHISPER_SIZE=small
```

Never commit this file: `.env` is included in `.gitignore`.

### 6. First run

```bash
python bot.py
```

The first start downloads the Whisper model, so it may take a moment. Then message your bot in Telegram.

## Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TELEGRAM_TOKEN` | yes | none | Bot token from BotFather |
| `ALLOWED_USER_ID` | yes | none | Allowed Telegram user ID(s), comma-separated |
| `TIGO_API_TOKEN` | for solar | none | Tigo API token |
| `TIGO_SYSTEM_ID` | for solar | none | Tigo system ID |
| `AGENT_MODEL` | no | `qwen3:4b-instruct-2507-q4_K_M` | Ollama model used by the agent |
| `WHISPER_SIZE` | no | `small` | Whisper model size (`base`, `small`, `medium`) |

## Usage

| You send | Bot does |
|----------|----------|
| "How are the solar panels doing?" | Calls the Tigo API and summarises the result |
| 🎙️ "Quanto stanno producendo i pannelli?" | Transcribes, then shows solar status |
| "Give me a tip for a shopping list" | Normal chat reply |
| `/reset` | Clears the conversation memory |

## Project structure

```
.
├── bot.py            # Bot, LangGraph agent, tools
├── actions/          # SolarAction, TigoApi, BotUtility
├── logger/           # Logging setup
├── .env              # Your secrets (not committed)
└── requirements.txt
```

## Extending

Add a new `@tool` function in `bot.py`, describe it clearly in its docstring, and append it to `TOOLS`. The agent decides when to call it. For tools that change things (calendar, messages), add a confirmation step first.

## Troubleshooting

- **`connection refused`**: Ollama isn't running (`ollama serve`) or the model isn't pulled (`ollama list`).
- **`Missing required variable`**: `.env` must be next to `bot.py` and contain `TELEGRAM_TOKEN` and `ALLOWED_USER_ID`.
- **Bot doesn't answer**: check that `ALLOWED_USER_ID` matches your Telegram ID, since other users are ignored.
- **"Tigo API not reachable"**: check `TIGO_API_TOKEN`, `TIGO_SYSTEM_ID` and your network.
- **Slow replies or poor transcription**: try `WHISPER_SIZE=base` (faster) or `medium` (more accurate).

## Privacy

LLM inference and transcription happen on your machine. Telegram still sees your messages, and the bot only calls the Tigo API.