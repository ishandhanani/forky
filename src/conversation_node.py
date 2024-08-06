from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime

@dataclass
class ConversationNode:
    """
    Represents a single node in the conversation tree.
    
    Each node contains a message, its metadata, and references to related nodes.
    """
    content: str
    role: str
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

    def __str__(self) -> str:
        """
        Returns a string representation of the node.
        
        Returns:
            str: A string containing the role and a preview of the content.
        """
        content_preview = self.content[:50] + '...' if len(self.content) > 50 else self.content
        return f"{self.role}: {content_preview}"