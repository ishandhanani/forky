"""
State summary generation for three-way merge.

Uses LLM to generate structured state summaries from conversation history.
"""

import json
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
from .api_client import APIClient


@dataclass
class StateSummary:
    """
    Structured representation of conversation state at a point.
    
    Contains facts, assumptions, decisions, and other semantic elements
    extracted from conversation history.
    """
    facts: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    decisions: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    open_questions: List[str] = field(default_factory=list)
    definitions: Dict[str, str] = field(default_factory=dict)
    context_notes: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'StateSummary':
        """Deserialize from dictionary."""
        return cls(
            facts=data.get("facts", []),
            assumptions=data.get("assumptions", []),
            decisions=data.get("decisions", []),
            constraints=data.get("constraints", []),
            open_questions=data.get("open_questions", []),
            definitions=data.get("definitions", {}),
            context_notes=data.get("context_notes", [])
        )
    
    def is_empty(self) -> bool:
        """Check if summary has no content."""
        return (
            not self.facts and 
            not self.assumptions and 
            not self.decisions and 
            not self.constraints and 
            not self.open_questions and 
            not self.definitions and 
            not self.context_notes
        )


STATE_SUMMARY_PROMPT = '''Analyze the following conversation and extract a structured state summary.

<conversation>
{conversation}
</conversation>

Extract the current state of the conversation into the following structured format. 
Be precise and concise - only include items that are explicitly stated or strongly implied.

Output a valid JSON object with these fields:
- "facts": Array of established facts (things stated as true)
- "assumptions": Array of assumptions being made
- "decisions": Array of decisions that have been made
- "constraints": Array of constraints or limitations mentioned
- "open_questions": Array of unresolved questions
- "definitions": Object mapping terms to their definitions
- "context_notes": Array of important context notes

Example output:
{{
  "facts": ["The project uses Python 3.9", "Database is PostgreSQL"],
  "assumptions": ["Users have admin access"],
  "decisions": ["Use REST API instead of GraphQL"],
  "constraints": ["Must support legacy browsers"],
  "open_questions": ["What is the performance target?"],
  "definitions": {{"API": "Application Programming Interface"}},
  "context_notes": ["This is a refactoring of existing codebase"]
}}

If a category has no items, use an empty array [] or empty object {{}}.
Return ONLY the JSON object, no additional text.'''


def format_conversation_for_summary(messages: List[Dict[str, str]]) -> str:
    """
    Format conversation messages for the summary prompt.
    
    Args:
        messages: List of message dicts with role and content.
        
    Returns:
        Formatted string representation.
    """
    lines = []
    for msg in messages:
        role = msg.get("role", "unknown").capitalize()
        content = msg.get("content", "")
        lines.append(f"{role}: {content}")
    return "\n\n".join(lines)


def generate_state_summary(
    messages: List[Dict[str, str]], 
    api_client: Optional[APIClient] = None,
    provider: str = "anthropic"
) -> StateSummary:
    """
    Generate a state summary from conversation messages using LLM.
    
    Args:
        messages: Conversation history as list of {role, content} dicts.
        api_client: Optional API client (creates new one if not provided).
        provider: LLM provider to use.
        
    Returns:
        StateSummary extracted from the conversation.
    """
    if not messages:
        return StateSummary()
    
    if api_client is None:
        api_client = APIClient(provider=provider)
    
    # Format conversation
    conversation_text = format_conversation_for_summary(messages)
    prompt = STATE_SUMMARY_PROMPT.format(conversation=conversation_text)
    
    # Get LLM response
    try:
        response = api_client.get_response(prompt, [])
        
        # Parse JSON from response - use shared utility
        from .merge_utils_shared import extract_json_from_markdown
        json_str = extract_json_from_markdown(response)
        
        data = json.loads(json_str)
        return StateSummary.from_dict(data)
        
    except json.JSONDecodeError as e:
        print(f"Failed to parse state summary JSON: {e}")
        return StateSummary(context_notes=[f"Failed to parse: {response[:200]}"])
    except Exception as e:
        print(f"Error generating state summary: {e}")
        return StateSummary()


def get_cached_or_generate_summary(
    node_id: str,
    messages: List[Dict[str, str]],
    cache: Dict[str, StateSummary],
    api_client: Optional[APIClient] = None
) -> StateSummary:
    """
    Get cached summary or generate new one.
    
    Args:
        node_id: ID of the node for caching.
        messages: Conversation history.
        cache: Cache dictionary to check/update.
        api_client: Optional API client.
        
    Returns:
        StateSummary (cached or newly generated).
    """
    if node_id in cache:
        return cache[node_id]
    
    summary = generate_state_summary(messages, api_client)
    cache[node_id] = summary
    return summary
