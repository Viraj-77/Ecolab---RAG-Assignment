from __future__ import annotations

from typing import Any, Literal


MessageRole = Literal["system", "user", "assistant", "tool"]


class ConversationMemory:
    """
    Lightweight conversation memory for one chat session.

    Purpose:
    - Stores system prompt
    - Stores augmented RAG user prompts
    - Stores assistant answers
    - Stores tool-call results for Azure mode

    Note:
    Visible Streamlit messages are stored separately in st.session_state.messages.
    This memory stores internal LLM messages.
    """

    VALID_ROLES = {"system", "user", "assistant", "tool"}

    def __init__(
        self,
        system_prompt: str,
        max_messages: int = 20,
    ):
        if not system_prompt or not system_prompt.strip():
            raise ValueError("system_prompt cannot be empty.")

        if max_messages < 4:
            raise ValueError("max_messages must be at least 4.")

        self.system_prompt = system_prompt.strip()
        self.max_messages = max_messages

        self._history: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": self.system_prompt,
            }
        ]

    def _validate_role(self, role: str) -> None:
        if role not in self.VALID_ROLES:
            raise ValueError(
                f"Invalid message role `{role}`. "
                f"Allowed roles: {sorted(self.VALID_ROLES)}"
            )

    def _trim_history(self) -> None:
        """
        Keep memory bounded for lower token usage.

        Always keeps the system prompt.
        Keeps the latest max_messages after system prompt.
        """
        system_message = self._history[0]
        remaining_messages = self._history[1:]

        if len(remaining_messages) > self.max_messages:
            remaining_messages = remaining_messages[-self.max_messages :]

        self._history = [system_message] + remaining_messages

    def add(
        self,
        role: Literal["user", "assistant", "tool"],
        content: str,
        **extra: Any,
    ) -> None:
        """
        Add message to memory.

        Use:
        - role="user" for augmented RAG question
        - role="assistant" for model response
        - role="tool" for tool result
        """
        self._validate_role(role)

        if content is None:
            content = ""

        message: dict[str, Any] = {
            "role": role,
            "content": str(content),
        }

        message.update(extra)

        self._history.append(message)
        self._trim_history()

    def add_user_message(self, content: str) -> None:
        self.add("user", content)

    def add_assistant_message(self, content: str, **extra: Any) -> None:
        self.add("assistant", content, **extra)

    def add_tool_message(self, tool_call_id: str, content: str) -> None:
        """
        Add OpenAI-compatible tool result message.
        """
        if not tool_call_id:
            tool_call_id = "unknown_tool_call"

        self._history.append(
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": str(content or ""),
            }
        )

        self._trim_history()

    def add_tool_result(self, tool_call_id: str, content: str) -> None:
        """
        Alias used by rag_pipeline.py.
        """
        self.add_tool_message(tool_call_id, content)

    def messages(self) -> list[dict[str, Any]]:
        """
        Return copy of messages for LLM call.
        """
        return [dict(message) for message in self._history]

    def reset(self, system_prompt: str | None = None) -> None:
        """
        Reset memory.

        If system_prompt is not provided, keeps the original system prompt.
        """
        if system_prompt is not None:
            if not system_prompt.strip():
                raise ValueError("system_prompt cannot be empty.")
            self.system_prompt = system_prompt.strip()

        self._history = [
            {
                "role": "system",
                "content": self.system_prompt,
            }
        ]

    def clear(self) -> None:
        """
        Alias for reset().
        """
        self.reset()

    def last_messages(self, count: int = 5) -> list[dict[str, Any]]:
        """
        Return last N non-system messages.
        """
        if count <= 0:
            return []

        return [dict(message) for message in self._history[1:][-count:]]

    def __len__(self) -> int:
        return len(self._history)

    def __repr__(self) -> str:
        return f"ConversationMemory(messages={len(self._history)}, max_messages={self.max_messages})"