from typing import Literal


class ConversationMemory: 
    #Keeps the full message history for one chat session. Passed to the LLM on every turn so it remembers the conversation.


    def __init__(self, system_prompt: str):
        self._history: list[dict] = [
            {"role": "system", "content": system_prompt}
        ]



    def add(self, role: Literal["user", "assistant", "tool"], content: str, **extra): 
        #this function Addsa new messages to the conversation history with these roles
        msg = {"role": role, "content": content}
        msg.update(extra)
        self._history.append(msg)

    def add_tool_message(self, tool_call_id: str, content: str):
        #adds a tool response message that is done by calling a tool by llm
        self._history.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content,
        })

    def messages(self) -> list[dict]: #gives the full conversation history
        return list(self._history) #Returns a copy of the message list