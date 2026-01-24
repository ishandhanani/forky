
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.state_summary import StateSummary
from core.semantic_diff import SemanticDiff
from core.merge_executor import execute_simple_merge

def test_merge_logic():
    # Base state
    base = StateSummary(facts=["Fact 1"])
    
    # Diff A adds "Fact 2"
    diff_a = SemanticDiff()
    diff_a.added_facts = ["Fact 2"]
    
    # Diff B adds "Fact 2" but also removes it (erroneous state that should be handled)
    # Actually, the specific case in the code is:
    # if fact not in diff_b.removed_facts and fact not in diff_a.added_facts:
    
    # Case 1: Fact is in both added_facts and removed_facts of B
    diff_b = SemanticDiff()
    diff_b.added_facts = ["Fact 3"]
    diff_b.removed_facts = ["Fact 3"]
    
    result = execute_simple_merge(base, diff_a, diff_b)
    print(f"Case 1 (Fact 3 in B's added and removed): {'Fact 3' in result.merged_state.facts}")
    assert "Fact 3" not in result.merged_state.facts, "Fact 3 should not be in merged facts if it was removed by B"

    # Case 2: Fact is in B's added and A's added
    diff_b2 = SemanticDiff()
    diff_b2.added_facts = ["Fact 2"]
    
    result2 = execute_simple_merge(base, diff_a, diff_b2)
    print(f"Case 2 (Fact 2 in both A and B added): {'Fact 2' in result2.merged_state.facts}")
    # It should be there, but only once (set handles this), 
    # and provenance should be handled correctly.
    # The fix prevents provenance.from_b.append(fact) if it's already in diff_a.added_facts.
    assert "Fact 2" in result2.merged_state.facts
    assert result2.provenance.from_b.count("Fact 2") == 0, "Fact 2 should not be in Provenance B if already in A"

    print("Verification successful!")

if __name__ == "__main__":
    try:
        test_merge_logic()
    except AssertionError as e:
        print(f"Verification FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"An error occurred: {e}")
        sys.exit(1)
