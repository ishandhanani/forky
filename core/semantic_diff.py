"""
Semantic diff computation for three-way merge.

Computes structured differences between two state summaries.
"""

import json
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
from .state_summary import StateSummary
from .api_client import APIClient


@dataclass
class FactChange:
    """Represents a change to a fact."""
    from_value: str
    to_value: str


@dataclass
class SemanticDiff:
    """
    Structured representation of semantic differences between two states.
    
    Tracks additions, updates, and removals across all semantic categories.
    """
    added_facts: List[str] = field(default_factory=list)
    updated_facts: List[Dict[str, str]] = field(default_factory=list)  # [{from, to}]
    removed_facts: List[str] = field(default_factory=list)
    
    new_assumptions: List[str] = field(default_factory=list)
    revised_assumptions: List[Dict[str, str]] = field(default_factory=list)
    removed_assumptions: List[str] = field(default_factory=list)
    
    new_decisions: List[str] = field(default_factory=list)
    reversed_decisions: List[str] = field(default_factory=list)
    
    new_constraints: List[str] = field(default_factory=list)
    removed_constraints: List[str] = field(default_factory=list)
    
    questions_answered: List[str] = field(default_factory=list)
    new_open_questions: List[str] = field(default_factory=list)
    
    definition_changes: Dict[str, Dict[str, str]] = field(default_factory=dict)
    new_definitions: Dict[str, str] = field(default_factory=dict)
    removed_definitions: List[str] = field(default_factory=list)
    
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'SemanticDiff':
        """Deserialize from dictionary."""
        return cls(
            added_facts=data.get("added_facts", []),
            updated_facts=data.get("updated_facts", []),
            removed_facts=data.get("removed_facts", []),
            new_assumptions=data.get("new_assumptions", []),
            revised_assumptions=data.get("revised_assumptions", []),
            removed_assumptions=data.get("removed_assumptions", []),
            new_decisions=data.get("new_decisions", []),
            reversed_decisions=data.get("reversed_decisions", []),
            new_constraints=data.get("new_constraints", []),
            removed_constraints=data.get("removed_constraints", []),
            questions_answered=data.get("questions_answered", []),
            new_open_questions=data.get("new_open_questions", []),
            definition_changes=data.get("definition_changes", {}),
            new_definitions=data.get("new_definitions", {}),
            removed_definitions=data.get("removed_definitions", []),
            notes=data.get("notes", [])
        )
    
    def is_empty(self) -> bool:
        """Check if diff has no changes."""
        return (
            not self.added_facts and
            not self.updated_facts and
            not self.removed_facts and
            not self.new_assumptions and
            not self.revised_assumptions and
            not self.removed_assumptions and
            not self.new_decisions and
            not self.reversed_decisions and
            not self.new_constraints and
            not self.removed_constraints and
            not self.questions_answered and
            not self.new_open_questions and
            not self.definition_changes and
            not self.new_definitions and
            not self.removed_definitions and
            not self.notes
        )


SEMANTIC_DIFF_PROMPT = '''Compare the BASE state to the HEAD state and identify all semantic differences.

<base_state>
{base_state}
</base_state>

<head_state>
{head_state}
</head_state>

Identify what changed from BASE to HEAD. Output a valid JSON object with these fields:

- "added_facts": New facts in HEAD not in BASE
- "updated_facts": Array of {{"from": "old", "to": "new"}} for modified facts
- "removed_facts": Facts in BASE but not in HEAD
- "new_assumptions": New assumptions in HEAD
- "revised_assumptions": Array of {{"from": "old", "to": "new"}} for modified assumptions
- "removed_assumptions": Assumptions removed in HEAD
- "new_decisions": New decisions made in HEAD
- "reversed_decisions": Decisions from BASE that were reversed
- "new_constraints": New constraints in HEAD
- "removed_constraints": Constraints removed in HEAD
- "questions_answered": Open questions from BASE that got answered
- "new_open_questions": New questions raised in HEAD
- "definition_changes": Object mapping term to {{"from": "old def", "to": "new def"}}
- "new_definitions": Object mapping new terms to definitions
- "removed_definitions": Array of terms that were removed
- "notes": Any important observations about the diff

If unsure whether something is new vs restated, put it in "notes".
Use empty arrays [] and objects {{}} for categories with no changes.
Return ONLY the JSON object, no additional text.'''


def compute_semantic_diff(
    base_summary: StateSummary,
    head_summary: StateSummary,
    api_client: Optional[APIClient] = None,
    provider: str = "anthropic"
) -> SemanticDiff:
    """
    Compute semantic diff between base and head states using LLM.
    
    Args:
        base_summary: The base/ancestor state.
        head_summary: The head/current state.
        api_client: Optional API client.
        provider: LLM provider to use.
        
    Returns:
        SemanticDiff capturing all changes from base to head.
    """
    if base_summary.is_empty() and head_summary.is_empty():
        return SemanticDiff()
    
    if api_client is None:
        api_client = APIClient(provider=provider)
    
    # Format states as JSON for the prompt
    base_json = json.dumps(base_summary.to_dict(), indent=2)
    head_json = json.dumps(head_summary.to_dict(), indent=2)
    
    prompt = SEMANTIC_DIFF_PROMPT.format(
        base_state=base_json,
        head_state=head_json
    )
    
    try:
        response = api_client.get_response(prompt, [])
        
        # Parse JSON from response
        json_str = response.strip()
        if json_str.startswith("```"):
            lines = json_str.split("\n")
            json_lines = []
            in_block = False
            for line in lines:
                if line.startswith("```"):
                    in_block = not in_block
                    continue
                if in_block or not line.startswith("```"):
                    json_lines.append(line)
            json_str = "\n".join(json_lines)
        
        data = json.loads(json_str)
        return SemanticDiff.from_dict(data)
        
    except json.JSONDecodeError as e:
        print(f"Failed to parse semantic diff JSON: {e}")
        return SemanticDiff(notes=[f"Failed to parse diff: {response[:200]}"])
    except Exception as e:
        print(f"Error computing semantic diff: {e}")
        return SemanticDiff()


def compute_simple_diff(base_summary: StateSummary, head_summary: StateSummary) -> SemanticDiff:
    """
    Compute a simple set-based diff without LLM call.
    
    Less accurate but faster - useful for caching or fallback.
    
    Args:
        base_summary: The base state.
        head_summary: The head state.
        
    Returns:
        SemanticDiff with basic set differences.
    """
    diff = SemanticDiff()
    
    # Facts
    base_facts = set(base_summary.facts)
    head_facts = set(head_summary.facts)
    diff.added_facts = list(head_facts - base_facts)
    diff.removed_facts = list(base_facts - head_facts)
    
    # Assumptions
    base_assumptions = set(base_summary.assumptions)
    head_assumptions = set(head_summary.assumptions)
    diff.new_assumptions = list(head_assumptions - base_assumptions)
    diff.removed_assumptions = list(base_assumptions - head_assumptions)
    
    # Decisions
    base_decisions = set(base_summary.decisions)
    head_decisions = set(head_summary.decisions)
    diff.new_decisions = list(head_decisions - base_decisions)
    diff.reversed_decisions = list(base_decisions - head_decisions)
    
    # Constraints
    base_constraints = set(base_summary.constraints)
    head_constraints = set(head_summary.constraints)
    diff.new_constraints = list(head_constraints - base_constraints)
    diff.removed_constraints = list(base_constraints - head_constraints)
    
    # Questions
    base_questions = set(base_summary.open_questions)
    head_questions = set(head_summary.open_questions)
    diff.new_open_questions = list(head_questions - base_questions)
    diff.questions_answered = list(base_questions - head_questions)
    
    # Definitions
    base_defs = set(base_summary.definitions.keys())
    head_defs = set(head_summary.definitions.keys())
    
    for term in head_defs - base_defs:
        diff.new_definitions[term] = head_summary.definitions[term]
    
    diff.removed_definitions = list(base_defs - head_defs)
    
    for term in base_defs & head_defs:
        if base_summary.definitions[term] != head_summary.definitions[term]:
            diff.definition_changes[term] = {
                "from": base_summary.definitions[term],
                "to": head_summary.definitions[term]
            }
    
    return diff
