import os
from typing import List, Dict
import anthropic
from anthropic import Anthropic

class ClaudeClient:
    """
    A client for interacting with the Claude API.
    """

    def __init__(self):
        """
        Initializes the Claude API client.
        Raises an exception if the API key is not found in environment variables.
        """
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in environment variables")
        self.client = Anthropic(api_key=api_key)
        self.model = "claude-3-5-sonnet-20240620"

    def get_response(self, message: str, conversation_history: List[Dict[str, str]] = None) -> str:
        """
        Sends a message to Claude and returns the response.

        Args:
            message (str): The message to send to Claude.
            conversation_history (List[Dict[str, str]], optional): Previous conversation history.

        Returns:
            str: Claude's response.
        """
        messages = self._prepare_messages(message, conversation_history)

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=messages
            )
            return response.content[0].text
        except anthropic.APIError as e:
            print(f"An error occurred while communicating with the Claude API: {e}")
            return "I'm sorry, but I encountered an error while processing your request."

    def _prepare_messages(self, message: str, conversation_history: List[Dict[str, str]] = None) -> List[Dict[str, str]]:
        """
        Prepares the messages to be sent to the Claude API.

        Args:
            message (str): The new message to be sent.
            conversation_history (List[Dict[str, str]], optional): Previous conversation history.

        Returns:
            List[Dict[str, str]]: Prepared messages for the API request.
        """
        prepared_messages = []

        if conversation_history:
            prepared_messages.extend(conversation_history)

        prepared_messages.append({"role": "human", "content": message})

        return prepared_messages

    def summarize(self, conversation: List[str]) -> str:
        """
        Summarizes a given conversation using Claude.

        Args:
            conversation (List[str]): A list of conversation messages to summarize.

        Returns:
            str: A summary of the conversation.
        """
        summary_prompt = "Please summarize the key points of the following conversation:\n\n" + "\n".join(conversation)
        return self.get_response(summary_prompt)