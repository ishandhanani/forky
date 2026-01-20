"""
Merge utilities for three-way semantic merge.

Provides LCA computation, ancestor checking, and merge eligibility validation.
"""

from dataclasses import dataclass
from typing import Optional, Set, List, Tuple
from collections import deque
from enum import Enum

from .conversation_node import ConversationNode


class MergeRejectionReason(Enum):
    """Reasons why a merge may be rejected."""
    SAME_NODE = "cannot_merge_node_with_itself"
    ANCESTOR_DESCENDANT = "cannot_merge_ancestor_with_descendant"
    NO_COMMON_ANCESTOR = "no_common_ancestor_found"


@dataclass
class MergeEligibility:
    """Result of merge eligibility check."""
    eligible: bool
    rejection_reason: Optional[MergeRejectionReason] = None
    lca: Optional[ConversationNode] = None
    lca_id: Optional[str] = None
    distance_a: int = 0
    distance_b: int = 0

    def to_dict(self) -> dict:
        """Serialize to dictionary for API responses."""
        return {
            "eligible": self.eligible,
            "rejection_reason": self.rejection_reason.value if self.rejection_reason else None,
            "lca_id": self.lca_id,
            "distance_a": self.distance_a,
            "distance_b": self.distance_b
        }


def get_ancestors_with_distance(node: ConversationNode) -> dict:
    """
    Returns a dict mapping ancestor node IDs to their distance from the given node.
    
    Args:
        node: Starting node for ancestor traversal.
        
    Returns:
        Dict mapping node_id -> distance (0 for the node itself).
    """
    ancestors = {node.id: 0}
    queue = deque([(node, 0)])
    
    while queue:
        current, dist = queue.popleft()
        for parent in current.parents:
            if parent.id not in ancestors:
                ancestors[parent.id] = dist + 1
                queue.append((parent, dist + 1))
    
    return ancestors


def is_ancestor(potential_ancestor: ConversationNode, node: ConversationNode) -> bool:
    """
    Checks if potential_ancestor is an ancestor of node.
    
    Args:
        potential_ancestor: The node to check as ancestor.
        node: The descendant node.
        
    Returns:
        True if potential_ancestor is an ancestor of node.
    """
    if potential_ancestor.id == node.id:
        return False
    
    ancestors = get_ancestors_with_distance(node)
    return potential_ancestor.id in ancestors


def compute_lca(node_a: ConversationNode, node_b: ConversationNode) -> Tuple[Optional[ConversationNode], int, int]:
    """
    Computes the Lowest Common Ancestor of two nodes.
    
    Uses BFS to find ancestors of both nodes, then finds the common ancestor
    with minimum total distance.
    
    Args:
        node_a: First node.
        node_b: Second node.
        
    Returns:
        Tuple of (LCA node or None, distance from A, distance from B).
    """
    # Get all ancestors with distances
    ancestors_a = get_ancestors_with_distance(node_a)
    ancestors_b = get_ancestors_with_distance(node_b)
    
    # Find common ancestors
    common_ids = set(ancestors_a.keys()) & set(ancestors_b.keys())
    
    if not common_ids:
        return None, 0, 0
    
    # Find the one with minimum total distance
    best_lca_id = None
    best_total_dist = float('inf')
    best_dist_a = 0
    best_dist_b = 0
    
    for cid in common_ids:
        dist_a = ancestors_a[cid]
        dist_b = ancestors_b[cid]
        total = dist_a + dist_b
        
        if total < best_total_dist:
            best_total_dist = total
            best_lca_id = cid
            best_dist_a = dist_a
            best_dist_b = dist_b
    
    # Get the actual node - we need to traverse to find it
    lca_node = _find_node_by_id_from(node_a, best_lca_id) or _find_node_by_id_from(node_b, best_lca_id)
    
    return lca_node, best_dist_a, best_dist_b


def _find_node_by_id_from(start_node: ConversationNode, target_id: str) -> Optional[ConversationNode]:
    """
    Finds a node by ID by traversing ancestors from start_node.
    """
    visited = set()
    queue = deque([start_node])
    
    while queue:
        current = queue.popleft()
        if current.id == target_id:
            return current
        if current.id in visited:
            continue
        visited.add(current.id)
        queue.extend(current.parents)
    
    return None


def check_merge_eligibility(node_a: ConversationNode, node_b: ConversationNode) -> MergeEligibility:
    """
    Checks whether two nodes can be merged.
    
    Rules:
    1. Nodes must be distinct
    2. Neither can be an ancestor of the other
    3. Must have a common ancestor (LCA)
    
    Args:
        node_a: First node to merge.
        node_b: Second node to merge.
        
    Returns:
        MergeEligibility with eligibility status and LCA if valid.
    """
    # Rule 1: Distinctness
    if node_a.id == node_b.id:
        return MergeEligibility(
            eligible=False,
            rejection_reason=MergeRejectionReason.SAME_NODE
        )
    
    # Rule 2: No ancestor/descendant
    if is_ancestor(node_a, node_b):
        return MergeEligibility(
            eligible=False,
            rejection_reason=MergeRejectionReason.ANCESTOR_DESCENDANT
        )
    
    if is_ancestor(node_b, node_a):
        return MergeEligibility(
            eligible=False,
            rejection_reason=MergeRejectionReason.ANCESTOR_DESCENDANT
        )
    
    # Rule 3: Must have common ancestor
    lca, dist_a, dist_b = compute_lca(node_a, node_b)
    
    if lca is None:
        return MergeEligibility(
            eligible=False,
            rejection_reason=MergeRejectionReason.NO_COMMON_ANCESTOR
        )
    
    return MergeEligibility(
        eligible=True,
        lca=lca,
        lca_id=lca.id,
        distance_a=dist_a,
        distance_b=dist_b
    )


def get_path_to_ancestor(node: ConversationNode, ancestor: ConversationNode) -> List[ConversationNode]:
    """
    Gets the path from node to ancestor (inclusive on both ends).
    
    Uses BFS to find shortest path.
    
    Args:
        node: Starting node.
        ancestor: Target ancestor node.
        
    Returns:
        List of nodes from node to ancestor, or empty if not reachable.
    """
    if node.id == ancestor.id:
        return [node]
    
    # BFS with parent tracking
    visited = {node.id: None}
    queue = deque([node])
    
    while queue:
        current = queue.popleft()
        
        for parent in current.parents:
            if parent.id not in visited:
                visited[parent.id] = current
                queue.append(parent)
                
                if parent.id == ancestor.id:
                    # Reconstruct path
                    path = [ancestor]
                    curr = ancestor
                    while visited.get(curr.id):
                        curr = visited[curr.id]
                        path.append(curr)
                    return list(reversed(path))
    
    return []


def get_conversation_segment(from_node: ConversationNode, to_node: ConversationNode) -> List[dict]:
    """
    Gets conversation messages between two nodes (from ancestor to descendant).
    
    Args:
        from_node: Ancestor node (start).
        to_node: Descendant node (end).
        
    Returns:
        List of message dicts with role and content.
    """
    path = get_path_to_ancestor(to_node, from_node)
    
    if not path:
        return []
    
    messages = []
    for node in path:
        if node.role in ("user", "assistant"):
            messages.append({
                "role": node.role,
                "content": node.content
            })
    
    return messages
