import os
from typing import List, Dict
import anthropic
from anthropic import Anthropic
from dotenv import load_dotenv

class ClaudeClient:
    def __init__(self):
        load_dotenv()
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in environment variables")
        self.client = Anthropic(api_key=api_key)
        self.model = "claude-3-5-sonnet-20240620"

    def get_response(self, message: str, conversation_history: List[Dict[str, str]] = None) -> str:
        messages = self._prepare_messages(message, conversation_history)

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=15,
                messages=messages
            )
            return response.content[0].text
        except anthropic.APIError as e:
            print(f"An error occurred while communicating with the Claude API: {e}")
            return "I'm sorry, but I encountered an error while processing your request."

    def _prepare_messages(self, message: str, conversation_history: List[Dict[str, str]] = None) -> List[Dict[str, str]]:
        prepared_messages = []

        if conversation_history:
            # Ensure the first message has the "user" role
            if conversation_history[0]["role"] != "user":
                prepared_messages.append({"role": "user", "content": "Start of conversation"})
            prepared_messages.extend(conversation_history)

        # Add the new message
        prepared_messages.append({"role": "user", "content": message})

        return prepared_messages

    def summarize(self, conversation: List[str]) -> str:
        summary_prompt = "Please summarize the key points of the following conversation:\n\n" + "\n".join(conversation)
        return self.get_response(summary_prompt)