from src.llm_client import get_chat_client, CHAT_MODEL, PROFILE
from src.semantic_search import retrieve
from src.conversational_memory import ConversationMemory
from src.followup_query import ALL_TOOLS, execute_tool

client = get_chat_client()

# gemma3n:e4b on Ollama does not support the tools parameter at the API layer.
# When running the local profile we drop tool calling entirely; the agent becomes
# RAG-only. The cloud profile keeps the full tool-call loop.
TOOLS_ENABLED = PROFILE == "cloud"

SYSTEM_PROMPT = """You are an Ecolab assistant.
You have access to a knowledge base of water treatment, hygiene, and sustainability documents,
and a tool that fetches live USGS water quality measurements by location.

Use the knowledge base for: concepts, best practices, regulations, research, and general questions.
Use get_water_quality for: real readings, current data, or location specific water quality numbers.
Use both together when a question needs context from documents AND live measurements.
"""

LOCAL_SYSTEM_PROMPT = """You are an Ecolab assistant.
You have access to a knowledge base of water treatment, hygiene, and sustainability documents.
Answer using only the provided context. If the question requires live water quality measurements
(real-time USGS readings) or other data not present in the context, state clearly that you cannot
fetch live data in this configuration.
"""


def chat(memory: ConversationMemory, user_message: str) -> str:
    chunks = retrieve(user_message)
    if chunks:
        context = "\n\n".join(f"[{c['source']}]\n{c['text']}" for c in chunks)
        augmented = f"Context from documents:\n{context}\n\nQuestion: {user_message}"
    else:
        augmented = user_message

    memory.add("user", augmented)

    while True:
        kwargs = {
            "model": CHAT_MODEL,
            "messages": memory.messages(),
        }
        if TOOLS_ENABLED:
            kwargs["tools"] = ALL_TOOLS
            kwargs["tool_choice"] = "auto"

        response = client.chat.completions.create(**kwargs)
        msg = response.choices[0].message

        if TOOLS_ENABLED and msg.tool_calls:
            memory.add("assistant", msg.content or "", tool_calls=msg.tool_calls)
            for tc in msg.tool_calls:
                result = execute_tool(tc.function.name, tc.function.arguments)
                memory.add_tool_message(tc.id, result)
            continue

        answer = msg.content or ""
        memory.add("assistant", answer)
        return answer
