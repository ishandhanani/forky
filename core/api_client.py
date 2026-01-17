import os
import json
from typing import List, Dict, Optional, Any, Union
import anthropic
from anthropic import Anthropic
import openai
from openai import OpenAI
from dotenv import load_dotenv


class APIClient:
    """
    Multi-provider LLM API client supporting Anthropic (Claude) and OpenAI (GPT).
    
    Supports both text-only and multimodal (images + documents) requests.
    """
    
    def __init__(self, provider: str = "anthropic", model: Optional[str] = None):
        load_dotenv()
        
        # If model is provided, try to infer provider or respect explicit provider
        if model:
            self.model = model
            if "gpt" in model.lower():
                self.provider = "openai"
            elif "claude" in model.lower():
                self.provider = "anthropic"
            else:
                self.provider = provider
        else:
            self.provider = provider
            # Set default models
            if self.provider == "anthropic":
                self.model = "claude-3-5-sonnet-20240620"
            elif self.provider == "openai":
                self.model = "gpt-4o"

        if self.provider == "anthropic":
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY not found in environment variables")
            self.client = Anthropic(api_key=api_key)
            
        elif self.provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY not found in environment variables")
            self.client = OpenAI(api_key=api_key)
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    def get_response(
        self, 
        message: str, 
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        attachments: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """
        Sends a message to the LLM and gets a response.

        Args:
            message: The message to send.
            conversation_history: Previous conversation history.
            attachments: Optional list of attachments [{type, name, mime_type, data}].

        Returns:
            The LLM's response.
        """
        if conversation_history is None:
            conversation_history = []

        if self.provider == "anthropic":
            return self._get_claude_response(message, conversation_history, attachments)
        elif self.provider == "openai":
            return self._get_openai_response(message, conversation_history, attachments)
        return ""

    def get_response_stream(
        self, 
        message: str, 
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        attachments: Optional[List[Dict[str, Any]]] = None
    ):
        """
        Stream response from the LLM.
        
        Args:
            message: The message to send.
            conversation_history: Previous conversation history.
            attachments: Optional list of attachments [{type, name, mime_type, data}].
            
        Yields:
            Chunks of the response text.
        """
        if conversation_history is None:
            conversation_history = []

        if self.provider == "anthropic":
            yield from self._get_claude_response_stream(message, conversation_history, attachments)
        elif self.provider == "openai":
            yield from self._get_openai_response_stream(message, conversation_history, attachments)

    def _build_multimodal_content_anthropic(
        self, 
        message: str, 
        attachments: Optional[List[Dict[str, Any]]]
    ) -> Union[str, List[Dict[str, Any]]]:
        """
        Builds multimodal content block for Anthropic API.
        
        Args:
            message: The text message.
            attachments: List of attachments.
            
        Returns:
            Either a string (text only) or a list of content blocks (multimodal).
        """
        if not attachments:
            return message
        
        content = []
        
        # Add attachments first
        for att in attachments:
            if att["type"] == "image":
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": att["mime_type"],
                        "data": att["data"]
                    }
                })
            elif att["type"] == "document":
                # Add document content as text with file context
                content.append({
                    "type": "text",
                    "text": f"[Attached file: {att['name']}]\n```\n{att['data']}\n```"
                })
        
        # Add the actual message last
        content.append({
            "type": "text",
            "text": message
        })
        
        return content

    def _build_multimodal_content_openai(
        self, 
        message: str, 
        attachments: Optional[List[Dict[str, Any]]]
    ) -> Union[str, List[Dict[str, Any]]]:
        """
        Builds multimodal content block for OpenAI API.
        
        Args:
            message: The text message.
            attachments: List of attachments.
            
        Returns:
            Either a string (text only) or a list of content blocks (multimodal).
        """
        if not attachments:
            return message
        
        content = []
        
        # Add attachments first
        for att in attachments:
            if att["type"] == "image":
                content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{att['mime_type']};base64,{att['data']}"
                    }
                })
            elif att["type"] == "document":
                # Add document content as text with file context
                content.append({
                    "type": "text",
                    "text": f"[Attached file: {att['name']}]\n```\n{att['data']}\n```"
                })
        
        # Add the actual message last
        content.append({
            "type": "text",
            "text": message
        })
        
        return content

    def _get_claude_response(
        self, 
        message: str, 
        conversation_history: List[Dict[str, Any]],
        attachments: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """Gets a non-streaming response from Claude."""
        system_message = "You are Claude, an AI assistant created by Anthropic to be helpful, harmless, and honest."
        
        # Build the user message with multimodal content if needed
        user_content = self._build_multimodal_content_anthropic(message, attachments)
        
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system_message,
                messages=conversation_history + [{"role": "user", "content": user_content}]
            )
            return response.content[0].text
        except anthropic.APIError as e:
            print(f"An error occurred while communicating with the Claude API: {e}")
            return "I'm sorry, but I encountered an error while processing your request."

    def _get_claude_response_stream(
        self, 
        message: str, 
        conversation_history: List[Dict[str, Any]],
        attachments: Optional[List[Dict[str, Any]]] = None
    ):
        """Gets a streaming response from Claude."""
        system_message = "You are Claude, an AI assistant created by Anthropic to be helpful, harmless, and honest."
        
        # Build the user message with multimodal content if needed
        user_content = self._build_multimodal_content_anthropic(message, attachments)
        
        try:
            with self.client.messages.stream(
                model=self.model,
                max_tokens=4096,
                system=system_message,
                messages=conversation_history + [{"role": "user", "content": user_content}]
            ) as stream:
                for text in stream.text_stream:
                    yield text
        except anthropic.APIError as e:
            print(f"An error occurred while communicating with the Claude API: {e}")
            yield "I'm sorry, but I encountered an error while processing your request."

    def _get_openai_response(
        self, 
        message: str, 
        conversation_history: List[Dict[str, Any]],
        attachments: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """Gets a non-streaming response from OpenAI."""
        system_message = {"role": "system", "content": "You are a helpful assistant."}
        
        # Build the user message with multimodal content if needed
        user_content = self._build_multimodal_content_openai(message, attachments)
        
        messages = [system_message] + conversation_history + [{"role": "user", "content": user_content}]
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"An error occurred while communicating with the OpenAI API: {e}")
            return "I'm sorry, but I encountered an error while processing your request."

    def _get_openai_response_stream(
        self, 
        message: str, 
        conversation_history: List[Dict[str, Any]],
        attachments: Optional[List[Dict[str, Any]]] = None
    ):
        """Gets a streaming response from OpenAI."""
        system_message = {"role": "system", "content": "You are a helpful assistant."}
        
        # Build the user message with multimodal content if needed
        user_content = self._build_multimodal_content_openai(message, attachments)
        
        messages = [system_message] + conversation_history + [{"role": "user", "content": user_content}]
        
        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True
            )
            for chunk in stream:
                if chunk.choices[0].delta.content is not None:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            print(f"An error occurred while communicating with the OpenAI API: {e}")
            yield "I'm sorry, but I encountered an error while processing your request."

    def summarize(self, conversation: List[str], merge_prompt: str) -> str:
        """Summarizes a conversation using the LLM."""
        summary_prompt = merge_prompt + "\n\n" + "\n".join(conversation)
        print("SUMMARY PROMPT: ", summary_prompt)
        return self.get_response(summary_prompt)


# Backward compatibility alias if needed, but I'll update usage.
ClaudeClient = APIClient 