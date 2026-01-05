from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid

@dataclass
class ConversationNode:
    """
    Represents a single node in the conversation tree (or DAG).
    
    Each node contains a message, its metadata, and references to related nodes.
    Now supports multiple parents for DAG-based merging.
    """
    content: str
    role: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    branch_name: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    children: List['ConversationNode'] = field(default_factory=list)
    parents: List['ConversationNode'] = field(default_factory=list)
    
    # Three-way merge support
    node_type: str = "message"  # "message" | "merge"
    merge_metadata: Optional[Dict[str, Any]] = None  # For merge nodes: {base_id, merged_state, conflicts, provenance}
    state_summary_cache: Optional[Dict[str, Any]] = None  # Cached StateSummary for this node

    @property
    def parent(self) -> Optional['ConversationNode']:
        """
        Backward compatibility property. Returns the first parent or None.
        """
        return self.parents[0] if self.parents else None

    @parent.setter
    def parent(self, value: Optional['ConversationNode']):
        """
        Backward compatibility setter. Sets the primary parent.
        """
        if value is None:
            self.parents = []
        else:
            if not self.parents:
                self.parents = [value]
            else:
                self.parents[0] = value

    def add_child(self, child: 'ConversationNode') -> None:
        """
        Adds a child node to this node.
        """
        self.children.append(child)
        if self not in child.parents:
            child.parents.append(self)

    def remove_child(self, child: 'ConversationNode') -> None:
        """
        Removes a child node from this node.
        """
        if child in self.children:
            self.children.remove(child)
            if self in child.parents:
                child.parents.remove(self)

    def is_leaf(self) -> bool:
        """
        Returns True if the node has no children.
        """
        return len(self.children) == 0

    def is_root(self) -> bool:
        """
        Returns True if the node has no parents.
        """
        return len(self.parents) == 0

    def depth(self) -> int:
        """
        Calculates the max depth of the node in the tree/DAG.
        """
        if self.is_root():
            return 0
        return 1 + max((p.depth() for p in self.parents), default=0)

    def to_dict(self) -> dict:
        """
        Serializes the node options to a dictionary (flat structure).
        """
        return {
            "id": self.id,
            "content": self.content,
            "role": self.role,
            "branch_name": self.branch_name,
            "timestamp": self.timestamp.isoformat(),
            "children_ids": [child.id for child in self.children],
            "parent_ids": [p.id for p in self.parents],
            "node_type": self.node_type,
            "merge_metadata": self.merge_metadata,
            "state_summary_cache": self.state_summary_cache
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'ConversationNode':
        """
        Deserializes a dictionary to a ConversationNode.
        """
        return cls(
            id=data.get("id", uuid.uuid4().hex[:8]),
            content=data["content"],
            role=data["role"],
            branch_name=data.get("branch_name"),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            node_type=data.get("node_type", "message"),
            merge_metadata=data.get("merge_metadata"),
            state_summary_cache=data.get("state_summary_cache")
        )
    
    def is_merge_node(self) -> bool:
        """
        Returns True if this is a merge node.
        """
        return self.node_type == "merge" or len(self.parents) > 1

    def __str__(self) -> str:
        """
        Returns a string representation of the node for debugging/logging.
        """
        content_preview = self.content[:50] + '...' if len(self.content) > 50 else self.content
        prefix = f"[{self.branch_name}] " if self.branch_name else ""
        return f"{prefix}{self.role}: {content_preview}"