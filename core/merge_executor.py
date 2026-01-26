"""
Three-way semantic merge executor.

Combines base state with two semantic diffs to produce merged state with conflict detection.
"""

import json
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
from .state_summary import StateSummary
from .semantic_diff import SemanticDiff
from .api_client import APIClient


@dataclass
class MergeConflict:
    """Represents a conflict between two branches."""
    topic: str
    base: str
    a_change: str
    b_change: str
    resolution: str = "unresolved"
    rationale: str = ""

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return asdict(self)


@dataclass
class MergeProvenance:
    """Tracks origin of items in merged state."""
    from_a: List[str] = field(default_factory=list)
    from_b: List[str] = field(default_factory=list)
    from_base: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return asdict(self)


@dataclass
class MergeResult:
    """Result of three-way merge operation."""
    merged_state: StateSummary
    conflicts: List[MergeConflict] = field(default_factory=list)
    provenance: MergeProvenance = field(default_factory=MergeProvenance)
    success: bool = True
    error: Optional[str] = None

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "merged_state": self.merged_state.to_dict(),
            "conflicts": [c.to_dict() for c in self.conflicts],
            "provenance": self.provenance.to_dict(),
            "success": self.success,
            "error": self.error
        }
    
    def has_conflicts(self) -> bool:
        """Check if merge has unresolved conflicts."""
        return any(c.resolution == "unresolved" for c in self.conflicts)


MERGE_EXECUTION_PROMPT = '''You are performing a three-way merge of conversation states.

<base_state>
{base_state}
</base_state>

<diff_from_branch_a>
{diff_a}
</diff_from_branch_a>

<diff_from_branch_b>
{diff_b}
</diff_from_branch_b>

Apply both diffs to the base state to produce a merged state.

CONFLICT DETECTION:
A conflict exists when:
1. Both diffs modify the same item differently
2. One removes something the other updates
3. Both add contradictory items on the same topic

For conflicts, do NOT auto-resolve. Mark them as unresolved.

OUTPUT FORMAT (JSON):
{{
  "merged_state": {{
    "facts": [...],
    "assumptions": [...],
    "decisions": [...],
    "constraints": [...],
    "open_questions": [...],
    "definitions": {{}},
    "context_notes": [...]
  }},
  "conflicts": [
    {{
      "topic": "description of conflicting item",
      "base": "original value or 'not present'",
      "a_change": "what branch A did",
      "b_change": "what branch B did",
      "resolution": "unresolved",
      "rationale": "explanation of why this is a conflict"
    }}
  ],
  "provenance": {{
    "from_a": ["list of items that came from branch A"],
    "from_b": ["list of items that came from branch B"],
    "from_base": ["list of items unchanged from base"]
  }}
}}

Include conflicting items in context_notes with clear labels like "[CONFLICT A]: ..." and "[CONFLICT B]: ...".
Return ONLY the JSON object.'''


def execute_three_way_merge(
    base_summary: StateSummary,
    diff_a: SemanticDiff,
    diff_b: SemanticDiff,
    api_client: Optional[APIClient] = None,
    provider: str = "anthropic"
) -> MergeResult:
    """
    Execute three-way merge using LLM.
    
    Args:
        base_summary: The LCA state summary.
        diff_a: Semantic diff from base to branch A head.
        diff_b: Semantic diff from base to branch B head.
        api_client: Optional API client.
        provider: LLM provider to use.
        
    Returns:
        MergeResult with merged state and any conflicts.
    """
    if api_client is None:
        api_client = APIClient(provider=provider)
    
    # Format inputs as JSON
    base_json = json.dumps(base_summary.to_dict(), indent=2)
    diff_a_json = json.dumps(diff_a.to_dict(), indent=2)
    diff_b_json = json.dumps(diff_b.to_dict(), indent=2)
    
    prompt = MERGE_EXECUTION_PROMPT.format(
        base_state=base_json,
        diff_a=diff_a_json,
        diff_b=diff_b_json
    )
    
    try:
        response = api_client.get_response(prompt, [])
        
        # Parse JSON from response - use shared utility
        from .merge_utils_shared import extract_json_from_markdown
        json_str = extract_json_from_markdown(response)
        
        data = json.loads(json_str)
        
        # Parse merged state
        merged_state = StateSummary.from_dict(data.get("merged_state", {}))
        
        # Parse conflicts
        conflicts = []
        for c_data in data.get("conflicts", []):
            conflicts.append(MergeConflict(
                topic=c_data.get("topic", ""),
                base=c_data.get("base", ""),
                a_change=c_data.get("a_change", ""),
                b_change=c_data.get("b_change", ""),
                resolution=c_data.get("resolution", "unresolved"),
                rationale=c_data.get("rationale", "")
            ))
        
        # Parse provenance
        prov_data = data.get("provenance", {})
        provenance = MergeProvenance(
            from_a=prov_data.get("from_a", []),
            from_b=prov_data.get("from_b", []),
            from_base=prov_data.get("from_base", [])
        )
        
        return MergeResult(
            merged_state=merged_state,
            conflicts=conflicts,
            provenance=provenance,
            success=True
        )
        
    except json.JSONDecodeError as e:
        print(f"Failed to parse merge result JSON: {e}")
        return MergeResult(
            merged_state=StateSummary(),
            success=False,
            error=f"Failed to parse merge result: {e}"
        )
    except Exception as e:
        print(f"Error executing merge: {e}")
        return MergeResult(
            merged_state=StateSummary(),
            success=False,
            error=str(e)
        )


def execute_simple_merge(
    base_summary: StateSummary,
    diff_a: SemanticDiff,
    diff_b: SemanticDiff
) -> MergeResult:
    """
    Execute simple set-based merge without LLM call.
    
    Detects conflicts when both branches modify the same category.
    Faster but less accurate than LLM-based merge.
    
    Args:
        base_summary: The LCA state summary.
        diff_a: Semantic diff from base to branch A.
        diff_b: Semantic diff from base to branch B.
        
    Returns:
        MergeResult with merged state and detected conflicts.
    """
    merged = StateSummary()
    conflicts = []
    provenance = MergeProvenance()
    
    # Merge facts
    base_facts = set(base_summary.facts)
    merged_facts = base_facts.copy()
    
    # Apply A's changes
    merged_facts -= set(diff_a.removed_facts)
    merged_facts.update(diff_a.added_facts)
    provenance.from_a.extend(diff_a.added_facts)
    
    # Apply B's changes - check for conflicts
    for fact in diff_b.removed_facts:
        if fact in diff_a.added_facts:
            conflicts.append(MergeConflict(
                topic=f"Fact: {fact[:50]}...",
                base="not present",
                a_change="added",
                b_change="would remove",
                rationale="A added a fact that B wants to remove"
            ))
            # Remove from merged_facts (do not keep A's addition)
            merged_facts.discard(fact)
            # Strip provenance
            if fact in provenance.from_a:
                provenance.from_a.remove(fact)
            if fact in provenance.from_b:
                provenance.from_b.remove(fact)
            if fact in provenance.from_base:
                provenance.from_base.remove(fact)
        else:
            merged_facts.discard(fact)
    
    for fact in diff_b.added_facts:
        if fact not in diff_b.removed_facts and fact not in diff_a.added_facts: # Avoid re-adding if it was a conflict
             merged_facts.add(fact)
             if fact not in diff_a.added_facts:
                 provenance.from_b.append(fact)
    
    merged.facts = list(merged_facts)
    provenance.from_base.extend([f for f in base_facts if f in merged_facts and f not in diff_a.added_facts and f not in diff_b.added_facts])
    
    # Merge decisions - similar logic
    base_decisions = set(base_summary.decisions)
    merged_decisions = base_decisions.copy()
    
    merged_decisions -= set(diff_a.reversed_decisions)
    merged_decisions.update(diff_a.new_decisions)
    provenance.from_a.extend(diff_a.new_decisions)
    
    for dec in diff_b.reversed_decisions:
        if dec in diff_a.new_decisions:
            conflicts.append(MergeConflict(
                topic=f"Decision: {dec[:50]}...",
                base="not present",
                a_change="new decision",
                b_change="would reverse",
                rationale="A made a decision that B reverses"
            ))
            # Remove from merged_decisions (do not keep A's new decision)
            merged_decisions.discard(dec)
            # Strip provenance
            if dec in provenance.from_a:
                provenance.from_a.remove(dec)
            if dec in provenance.from_b:
                provenance.from_b.remove(dec)
            if dec in provenance.from_base:
                provenance.from_base.remove(dec)
        else:
            merged_decisions.discard(dec)
    
    for dec in diff_b.new_decisions:
        if dec not in diff_b.reversed_decisions and dec not in diff_a.new_decisions: # Avoid re-adding if it was a conflict
            merged_decisions.add(dec)
            if dec not in diff_a.new_decisions:
                provenance.from_b.append(dec)
    
    merged.decisions = list(merged_decisions)
    
    # Merge assumptions
    base_assumptions = set(base_summary.assumptions)
    merged_assumptions = base_assumptions.copy()
    merged_assumptions -= set(diff_a.removed_assumptions)
    merged_assumptions.update(diff_a.new_assumptions)
    merged_assumptions -= set(diff_b.removed_assumptions)
    merged_assumptions.update(diff_b.new_assumptions)
    merged.assumptions = list(merged_assumptions)
    
    # Merge constraints
    base_constraints = set(base_summary.constraints)
    merged_constraints = base_constraints.copy()
    merged_constraints -= set(diff_a.removed_constraints)
    merged_constraints.update(diff_a.new_constraints)
    merged_constraints -= set(diff_b.removed_constraints)
    merged_constraints.update(diff_b.new_constraints)
    merged.constraints = list(merged_constraints)
    
    # Merge open questions
    base_questions = set(base_summary.open_questions)
    merged_questions = base_questions.copy()
    merged_questions -= set(diff_a.questions_answered)
    merged_questions.update(diff_a.new_open_questions)
    merged_questions -= set(diff_b.questions_answered)
    merged_questions.update(diff_b.new_open_questions)
    merged.open_questions = list(merged_questions)
    
    # Merge definitions
    merged.definitions = base_summary.definitions.copy()
    
    # 1. Apply removals
    for term in diff_a.removed_definitions:
        if term in merged.definitions:
            del merged.definitions[term]
    for term in diff_b.removed_definitions:
        if term in merged.definitions:
            del merged.definitions[term]
            
    # 2. Apply additions
    merged.definitions.update(diff_a.new_definitions)
    merged.definitions.update(diff_b.new_definitions)
    
    # Check for Add/Add conflicts
    for term, val_a in diff_a.new_definitions.items():
        if term in diff_b.new_definitions and val_a != diff_b.new_definitions[term]:
            conflicts.append(MergeConflict(
                topic=f"Definition: {term}",
                base="not present",
                a_change=val_a,
                b_change=diff_b.new_definitions[term],
                rationale="Both branches added this definition differently"
            ))
            # Conflict: remove it
            if term in merged.definitions:
                del merged.definitions[term]
    
    # 3. Check for update conflicts (updates vs updates, updates vs removals)
    processed_updates = set()
    
    # Updates from Diff A
    for term, change in diff_a.definition_changes.items():
        processed_updates.add(term)
        if term in diff_b.definition_changes:
            # Both update
            change_b = diff_b.definition_changes[term]
            if change["to"] != change_b["to"]:
                conflicts.append(MergeConflict(
                    topic=f"Definition: {term}",
                    base=change["from"],
                    a_change=change["to"],
                    b_change=change_b["to"],
                    rationale="Both branches redefined this term differently"
                ))
                # Restore base or remove
                if term in base_summary.definitions:
                    merged.definitions[term] = base_summary.definitions[term]
                else:
                    if term in merged.definitions:
                        del merged.definitions[term]
            else:
                merged.definitions[term] = change["to"]
        elif term in diff_b.removed_definitions:
            # A updates, B removes
            conflicts.append(MergeConflict(
                topic=f"Definition: {term}",
                base=change["from"],
                a_change=change["to"],
                b_change="removed",
                rationale="A updated a definition that B removed"
            ))
            # Restore base
            if term in base_summary.definitions:
                merged.definitions[term] = base_summary.definitions[term]
        else:
            # Only A updates
            merged.definitions[term] = change["to"]
            
    # Updates from Diff B (that weren't in A)
    for term, change in diff_b.definition_changes.items():
        if term in processed_updates:
            continue
            
        if term in diff_a.removed_definitions:
            # B updates, A removes
            conflicts.append(MergeConflict(
                topic=f"Definition: {term}",
                base=change["from"],
                a_change="removed",
                b_change=change["to"],
                rationale="B updated a definition that A removed"
            ))
            # Restore base
            if term in base_summary.definitions:
                merged.definitions[term] = base_summary.definitions[term]
        else:
            merged.definitions[term] = change["to"]
            
    # Cleanup provenance for all terms NOT in merged.definitions
    # This applies to removals from either side and unresolved conflicts.
    all_known_definition_terms = set(base_summary.definitions.keys()) | \
                                 set(diff_a.new_definitions.keys()) | \
                                 set(diff_b.new_definitions.keys())
    
    for term in all_known_definition_terms:
        if term not in merged.definitions:
            for p_list in [provenance.from_a, provenance.from_b, provenance.from_base]:
                to_remove = [item for item in p_list if f"Definition: {term}" in item or term == item]
                for item in to_remove:
                    if item in p_list:
                        p_list.remove(item)
    
    # Add conflict notes
    if conflicts:
        for c in conflicts:
            merged.context_notes.append(f"[CONFLICT]: {c.topic} - {c.rationale}")
    
    return MergeResult(
        merged_state=merged,
        conflicts=conflicts,
        provenance=provenance,
        success=True
    )


def format_merged_state_for_context(merge_result: MergeResult) -> str:
    """
    Format merge result as context for LLM continuation.
    
    Args:
        merge_result: The result of a merge operation.
        
    Returns:
        Formatted string for use in system/developer prompt.
    """
    state = merge_result.merged_state
    lines = ["## Merged Conversation State\n"]
    
    if state.facts:
        lines.append("### Facts")
        for fact in state.facts:
            lines.append(f"- {fact}")
        lines.append("")
    
    if state.decisions:
        lines.append("### Decisions")
        for dec in state.decisions:
            lines.append(f"- {dec}")
        lines.append("")
    
    if state.assumptions:
        lines.append("### Assumptions")
        for asm in state.assumptions:
            lines.append(f"- {asm}")
        lines.append("")
    
    if state.constraints:
        lines.append("### Constraints")
        for con in state.constraints:
            lines.append(f"- {con}")
        lines.append("")
    
    if state.open_questions:
        lines.append("### Open Questions")
        for q in state.open_questions:
            lines.append(f"- {q}")
        lines.append("")
    
    if state.definitions:
        lines.append("### Definitions")
        for term, defn in state.definitions.items():
            lines.append(f"- **{term}**: {defn}")
        lines.append("")
    
    if merge_result.has_conflicts():
        lines.append("### ⚠️ Unresolved Conflicts")
        for conflict in merge_result.conflicts:
            if conflict.resolution == "unresolved":
                lines.append(f"- **{conflict.topic}**")
                lines.append(f"  - Branch A: {conflict.a_change}")
                lines.append(f"  - Branch B: {conflict.b_change}")
        lines.append("")
        lines.append("*Please acknowledge these conflicts and clarify if needed.*")
    
    return "\n".join(lines)
