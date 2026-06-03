import json
import re

from src.client_factory import get_chat_client, get_chat_model, LLM_PROFILE
from src.semantic_search import retrieve
from src.conversational_memory import ConversationMemory
from src.followup_query import ALL_TOOLS, execute_tool

SYSTEM_PROMPT = """You are an Ecolab assistant.
You have access to a knowledge base of water treatment, hygiene, and sustainability documents,
and a tool that fetches live USGS water quality measurements by location.

Use the knowledge base for: concepts, best practices, regulations, research, and general questions.
Use get_water_quality for: real readings, current data, or location specific water quality numbers.
Use both together when a question needs context from documents AND live measurements.
"""

# Appended to the system prompt when using local model (no native tool support).
# The model must emit a TOOL_CALL line that we parse and execute manually.
_LOCAL_TOOL_SYSTEM_SUFFIX = """

You have access to ONE tool: get_water_quality
Use it ONLY when the user asks for real, current, or location-specific water quality readings.
Do NOT call it for general or conceptual questions.

To call the tool, output EXACTLY this on its own line and nothing else in that response:
TOOL_CALL: {"name": "get_water_quality", "arguments": {"state_fips": "<2-digit FIPS>", "parameter": "<pH|Temperature|Nitrate|Dissolved oxygen|Turbidity>"}}

State FIPS codes: Alabama=01, Alaska=02, Arizona=04, Arkansas=05, California=06, Colorado=08,
Connecticut=09, Delaware=10, Florida=12, Georgia=13, Hawaii=15, Idaho=16, Illinois=17,
Indiana=18, Iowa=19, Kansas=20, Kentucky=21, Louisiana=22, Maine=23, Maryland=24,
Massachusetts=25, Michigan=26, Minnesota=27, Mississippi=28, Missouri=29, Montana=30,
Nebraska=31, Nevada=32, New Hampshire=33, New Jersey=34, New Mexico=35, New York=36,
North Carolina=37, North Dakota=38, Ohio=39, Oklahoma=40, Oregon=41, Pennsylvania=42,
Rhode Island=44, South Carolina=45, South Dakota=46, Tennessee=47, Texas=48, Utah=49,
Vermont=50, Virginia=51, Washington=53, West Virginia=54, Wisconsin=55, Wyoming=56.

After the tool result is appended, continue with your final answer.
"""

_TOOL_CALL_RE = re.compile(r"TOOL_CALL:\s*(\{.*\})", re.DOTALL)


def _local_system_prompt() -> str:
    return SYSTEM_PROMPT + _LOCAL_TOOL_SYSTEM_SUFFIX


def _parse_local_tool_call(text: str) -> dict | None:
    m = _TOOL_CALL_RE.search(text)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def _chat_cloud(memory: ConversationMemory, client, model: str) -> str:
    """Standard OpenAI tool-call loop for cloud profile."""
    while True:
        response = client.chat.completions.create(
            model=model,
            messages=memory.messages(),
            tools=ALL_TOOLS,
            tool_choice="auto",
        )
        msg = response.choices[0].message

        if msg.tool_calls:
            memory.add("assistant", msg.content or "", tool_calls=msg.tool_calls)
            for tc in msg.tool_calls:
                result = execute_tool(tc.function.name, tc.function.arguments)
                memory.add_tool_result(tc.id, result)
            continue

        answer = msg.content or ""
        memory.add("assistant", answer)
        return answer


def _chat_local(memory: ConversationMemory, client, model: str) -> str:
    """Prompt-based tool-call loop for local profile (gemma3n has no native tools API)."""
    max_iterations = 4
    for _ in range(max_iterations):
        response = client.chat.completions.create(
            model=model,
            messages=memory.messages(),
        )
        text = response.choices[0].message.content or ""

        tool_call = _parse_local_tool_call(text)
        if tool_call:
            memory.add("assistant", text)
            result = execute_tool(tool_call["name"], json.dumps(tool_call.get("arguments", {})))
            # Inject tool result as a user-visible context line so the model can use it
            memory.add("user", f"Tool result for {tool_call['name']}:\n{result}\n\nNow answer the original question.")
            continue

        memory.add("assistant", text)
        return text

    # Exceeded max iterations — return last response
    return text


def chat(memory: ConversationMemory, user_message: str) -> str:
    chunks = retrieve(user_message)
    if chunks:
        context = "\n\n".join(f"[{c['source']}]\n{c['text']}" for c in chunks)
        augmented = f"Context from documents:\n{context}\n\nQuestion: {user_message}"
    else:
        augmented = user_message

    memory.add("user", augmented)

    client = get_chat_client()
    model = get_chat_model()

    if LLM_PROFILE == "local":
        return _chat_local(memory, client, model)
    return _chat_cloud(memory, client, model)


def make_memory() -> ConversationMemory:
    """Return a fresh ConversationMemory with the right system prompt for the active profile."""
    system = _local_system_prompt() if LLM_PROFILE == "local" else SYSTEM_PROMPT
    return ConversationMemory(system)
