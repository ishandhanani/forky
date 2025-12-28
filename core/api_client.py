import os
import json
from typing import List, Dict, Optional
import anthropic
from anthropic import Anthropic
import openai
from openai import OpenAI
from dotenv import load_dotenv

class APIClient:
    def __init__(self, provider: str = "anthropic"):
        load_dotenv()
        self.provider = provider
        
        if self.provider == "anthropic":
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY not found in environment variables")
            self.client = Anthropic(api_key=api_key)
            self.model = "claude-3-5-sonnet-20240620"
            
        elif self.provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY not found in environment variables")
            self.client = OpenAI(api_key=api_key)
            self.model = "gpt-4o"
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    def get_response(self, message: str, conversation_history: Optional[List[Dict[str, str]]] = None) -> str:
        """
        Sends a message to the LLM and gets a response.

        Args:
            message (str): The message to send.
            conversation_history (List[Dict[str, str]]): Previous conversation history.

        Returns:
            str: The LLM's response.
        """
        if conversation_history is None:
            conversation_history = []

        if self.provider == "anthropic":
            return self._get_claude_response(message, conversation_history)
        elif self.provider == "openai":
            return self._get_openai_response(message, conversation_history)
        return ""

    def _get_claude_response(self, message: str, conversation_history: List[Dict[str, str]]) -> str:
        system_message = "You are Claude, an AI assistant created by Anthropic to be helpful, harmless, and honest."
        
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system_message,
                messages=conversation_history + [{"role": "user", "content": message}]
            )
            return response.content[0].text
        except anthropic.APIError as e:
            print(f"An error occurred while communicating with the Claude API: {e}")
            return "I'm sorry, but I encountered an error while processing your request."

    def _get_openai_response(self, message: str, conversation_history: List[Dict[str, str]]) -> str:
        system_message = {"role": "system", "content": "You are a helpful assistant."}
        
        messages = [system_message] + conversation_history + [{"role": "user", "content": message}]
        print("DEBUG: Sending messages to OpenAI:", json.dumps(messages, indent=2))
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"An error occurred while communicating with the OpenAI API: {e}")
            return "I'm sorry, but I encountered an error while processing your request."

    def summarize(self, conversation: List[str], merge_prompt: str) -> str:
        summary_prompt = merge_prompt + "\n\n" + "\n".join(conversation)
        print("SUMMARY PROMPT: ", summary_prompt)
        return self.get_response(summary_prompt)

# Backward compatibility alias if needed, but I'll update usage.
ClaudeClient = APIClient 