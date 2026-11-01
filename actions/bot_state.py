from typing import TypedDict

# This LangGraph state is not used
# it's for getting the intent and rephrasing messages to be shorter and more concise, using bullet points.
# for now the llm is used directly in bot.py, but this action can be used in the future if needed.

class State(TypedDict, total=False):
    text: str
    intent: str
    reply: str