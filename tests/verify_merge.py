
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

    # Case 3: Definitions Merge
    base_def = StateSummary(definitions={"Term 1": "Def 1", "Term 2": "Def 2"})
    
    # Diff A removes Term 1, updates Term 2
    diff_da = SemanticDiff()
    diff_da.removed_definitions = ["Term 1"]
    diff_da.definition_changes = {"Term 2": {"from": "Def 2", "to": "Updated Def 2"}}
    
    # Diff B removes Term 2 (Conflict with A's update), adds Term 3
    diff_db = SemanticDiff()
    diff_db.removed_definitions = ["Term 2"]
    diff_db.new_definitions = {"Term 3": "Def 3"}
    
    result3 = execute_simple_merge(base_def, diff_da, diff_db)
    print(f"Case 3 (Term 1 removed by A): {'Term 1' in result3.merged_state.definitions}")
    print(f"Case 3 (Term 2 conflict - restored?): {result3.merged_state.definitions.get('Term 2')}")
    print(f"Case 3 (Term 3 added by B): {result3.merged_state.definitions.get('Term 3')}")
    
    assert "Term 1" not in result3.merged_state.definitions
    assert result3.merged_state.definitions.get("Term 2") == "Def 2", "Term 2 should be restored to base Def 2 due to update/remove conflict"
    assert result3.merged_state.definitions.get("Term 3") == "Def 3"
    
    # Case 4: Both remove
    diff_db4 = SemanticDiff()
    diff_db4.removed_definitions = ["Term 1"]
    result4 = execute_simple_merge(base_def, diff_da, diff_db4)
    print(f"Case 4 (Both remove Term 1): {'Term 1' in result4.merged_state.definitions}")
    assert "Term 1" not in result4.merged_state.definitions

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
