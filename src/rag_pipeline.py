import os
from dotenv import load_dotenv
from openai import AzureOpenAI

from src.semantic_search import retrieve
from src.conversational_memory import ConversationMemory
from src.followup_query import ALL_TOOLS, execute_tool

load_dotenv()
#this is taken from the .md file from teams
client = AzureOpenAI(
    api_version="2024-12-01-preview",
    azure_endpoint="https://cds-ds-openai-001-x.openai.azure.com/",
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
)
#passed to llm so it acts like the prompt, we are giving the llm a role
SYSTEM_PROMPT = """You are an Ecolab assistant.
You have access to a knowledge base of water treatment, hygiene, and sustainability documents,
and a tool that fetches live USGS water quality measurements by location.

Use the knowledge base for: concepts, best practices, regulations, research, and general questions.
Use get_water_quality for: real readings, current data, or location specific water quality numbers.
Use both together when a question needs context from documents AND live measurements.
"""


def chat(memory: ConversationMemory, user_message: str) -> str:
    #retrieve relevant document chunks
    chunks = retrieve(user_message)
    if chunks:
        context = "\n\n".join(f"[{c['source']}]\n{c['text']}" for c in chunks)
        augmented = f"Context from documents:\n{context}\n\nQuestion: {user_message}"
    else:
        augmented = user_message

    memory.add("user", augmented)


    #the model will request a tool if required then we execute it and call the model again.
    #qe keep looping until the model returns a plain text answer.
    while True:
        response = client.chat.completions.create(
            model="gpt-5.4-nano",   # deployment name from the spec
            messages=memory.messages(),
            tools=ALL_TOOLS,
            tool_choice="auto",
        )
        msg = response.choices[0].message

        if msg.tool_calls:
            #model wants to call a tool — execute each one and append results
            memory.add("assistant", msg.content or "", tool_calls=msg.tool_calls)
            for tc in msg.tool_calls:
                result = execute_tool(tc.function.name, tc.function.arguments)
                memory.add_tool_result(tc.id, result)
            continue  #go back to the top and call the model again

        #no tool call — this is the final answer
        answer = msg.content or ""
        memory.add("assistant", answer)
        return answer