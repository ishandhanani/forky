from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime
import uuid

@dataclass
class ConversationNode:
    """
    Represents a single node in the conversation tree.
    
    Each node contains a message, its metadata, and references to related nodes.
    """
    content: str
    role: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    branch_name: Optional[str] = None
    branch_name: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    children: List['ConversationNode'] = field(default_factory=list)
    parent: Optional['ConversationNode'] = None

    def add_child(self, child: 'ConversationNode') -> None:
        """
        Adds a child node to this node.
        
        Args:
            child (ConversationNode): The node to be added as a child.
        """
        self.children.append(child)
        child.parent = self

    def remove_child(self, child: 'ConversationNode') -> None:
        """
        Removes a child node from this node.
        
        Args:
            child (ConversationNode): The node to be removed from children.
        """
        if child in self.children:
            self.children.remove(child)
            child.parent = None

    def is_leaf(self) -> bool:
        """
        Checks if the node is a leaf (has no children).
        
        Returns:
            bool: True if the node has no children, False otherwise.
        """
        return len(self.children) == 0

    def is_root(self) -> bool:
        """
        Checks if the node is the root (has no parent).
        
        Returns:
            bool: True if the node has no parent, False otherwise.
        """
        return self.parent is None

    def depth(self) -> int:
        """
        Calculates the depth of the node in the tree.
        
        Returns:
            int: The depth of the node (0 for root, 1 for root's children, etc.)
        """
        if self.is_root():
            return 0
        return 1 + self.parent.depth()

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
            "parent_id": self.parent.id if self.parent else None
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'ConversationNode':
        """
        Deserializes a dictionary to a ConversationNode (flat structure).
        Does NOT handle children/parent linking here - that must be done by the tree loader.
        """
        return cls(
            id=data.get("id", uuid.uuid4().hex[:8]),
            content=data["content"],
            role=data["role"],
            branch_name=data.get("branch_name"),
            timestamp=datetime.fromisoformat(data["timestamp"])
        )

    def __str__(self) -> str:
        """
        Returns a string representation of the node.
        
        Returns:
            str: A string containing the role and a preview of the content.
        """
        content_preview = self.content[:50] + '...' if len(self.content) > 50 else self.content
        prefix = f"[{self.branch_name}] " if self.branch_name else ""
        return f"{prefix}{self.role}: {content_preview}"