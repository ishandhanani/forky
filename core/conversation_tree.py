import json
import os
import uuid
from datetime import datetime
from typing import List, Dict, Optional
from .conversation_node import ConversationNode
from .api_client import APIClient

class ConversationTree:
    """
    Manages a tree-like structure of conversation nodes, supporting operations
    like forking, merging, and interacting with the LLM API.
    """

    def __init__(self, provider: str = "anthropic"):
        self.root = ConversationNode(content="Root", role="system", branch_name="master")
        self.current_node = self.root
        self.api_client = APIClient(provider=provider)

    def _get_all_branch_names(self) -> set:
        names = set()
        queue = [self.root]
        while queue:
            node = queue.pop(0)
            if node.branch_name:
                names.add(node.branch_name)
            queue.extend(node.children)
        return names

    def add_message(self, content: str, role: str) -> None:
        """
        Adds a new message to the conversation.

        Args:
            content (str): The content of the message.
            role (str): The role of the message sender (user, assistant, or system).
        """
        new_node = ConversationNode(content=content, role=role)
        self.current_node.add_child(new_node)
        self.current_node = new_node

    def fork(self, branch_name: Optional[str] = None) -> None:
        """
        Creates a new branch in the conversation.

        Args:
            branch_name (str): The name of the new branch.
        
        Raises:
            ValueError: If the branch name already exists.
        """
        if branch_name:
            if branch_name in self._get_all_branch_names():
                raise ValueError(f"Branch name '{branch_name}' already exists.")
        else:
            # Auto-generate unique name
            while True:
                candidate = f"fork-{uuid.uuid4().hex[:8]}"
                if candidate not in self._get_all_branch_names():
                    branch_name = candidate
                    break
                
        fork_node = ConversationNode(content="<FORK>", role="system", branch_name=branch_name)
        self.current_node.add_child(fork_node)
        self.current_node = fork_node
        return branch_name

    def merge(self, merge_prompt: str) -> None:
        """
        Merges the current branch back into the main conversation and removes the fork.
        """
        # Find the fork node
        fork_node = self.current_node
        while fork_node.content != "<FORK>" and fork_node.parent:
            fork_node = fork_node.parent
        if fork_node.content != "<FORK>":
            raise ValueError("No fork found to merge")
        
        # Summarize the forked conversation
        if merge_prompt == "":
            merge_prompt = "Create a 1-2 sentence summary of the following conversation so that it is easy to understand:"
        summary = self._summarize_fork(fork_node, merge_prompt)
        
        # Move back to the main conversation
        parent_of_fork = fork_node.parent
        self.current_node = parent_of_fork

        # Add the summary as a user message and an assistant response
        merge_user_message = merge_prompt
        merge_assistant_message = f"Here's a summary of another conversation branch ({fork_node.branch_name or 'unnamed'}): {summary}"
        
        self.add_message(merge_user_message, "user")
        self.add_message(merge_assistant_message, "assistant")

        # Remove the fork and its entire subtree
        parent_of_fork.remove_child(fork_node)

    def _summarize_fork(self, fork_node: ConversationNode, merge_prompt: str) -> str:
        """
        Summarizes the conversation in a forked branch.

        Args:
            fork_node (ConversationNode): The node representing the fork.

        Returns:
            str: A summary of the forked conversation.
        """
        messages = self._collect_messages(fork_node)
        if not messages:
            return "The forked conversation was empty."

        try:
            summary = self.api_client.summarize(messages, merge_prompt)
            print("SUMMARY: ", summary)
            return summary
        except Exception as e:
            print(f"Error while summarizing fork: {e}")
            return "Unable to summarize the forked conversation due to an error."

    def _collect_messages(self, node: ConversationNode) -> List[str]:
        """
        Collects all messages in a branch.

        Args:
            node (ConversationNode): The node to start collecting from.

        Returns:
            List[str]: A list of message strings.
        """
        messages = []
        current = node
        while current and current.children:
            child = current.children[0]
            if child.role != "system":
                messages.append(f"{child.role}: {child.content}")
            current = child
        return messages

    def chat(self, message: str) -> str:
        """
        Sends a message to the LLM and gets a response, using the full conversation history.

        Args:
            message (str): The message to send.

        Returns:
            str: LLM response.
        """
        conversation_history = self.get_conversation_history()
        self.add_message(message, "user")
        response = self.api_client.get_response(message, conversation_history)
        self.add_message(response, "assistant")
        return response

    def get_conversation_history(self) -> List[Dict[str, str]]:
        """
        Retrieves the conversation history for the current branch, excluding system messages.

        Returns:
            List[Dict[str, str]]: A list of dictionaries representing the conversation history.
        """
        history = []
        current = self.current_node
        
        while current:
            if current.role in ["user", "assistant"]:
                history.append({"role": current.role, "content": current.content})
            elif current.role == "system" and current.content.startswith("MERGE SUMMARY:"):
                # Include merge summaries as user messages
                history.append({"role": "user", "content": current.content})
            current = current.parent
            
        return list(reversed(history))

    def print_tree(self, node: Optional[ConversationNode] = None, level: int = 0) -> None:
        """
        Prints the entire conversation tree.

        Args:
            node (Optional[ConversationNode]): The node to start printing from. Defaults to root.
            level (int): The current indentation level.
        """
        if node is None:
            node = self.root

        print("  " * level + str(node))
        for child in node.children:
            self.print_tree(child, level + 1)

    def get_flat_conversation(self) -> List[str]:
        """
        Returns a flat list of messages for the *current branch* context.
        """
        messages = []
        current = self.current_node
        while current:
            if current.role != "system" or current.content.startswith("MERGE SUMMARY:"):
                 messages.append(f"{current.role}: {current.content}")
            current = current.parent
        return list(reversed(messages))

    def is_in_fork(self) -> bool:
        current = self.current_node
        while current.parent:
            if current.content == "<FORK>":
                return True
            current = current.parent
        return False
    
    def find_node_by_id(self, identifier: str) -> Optional[ConversationNode]:
        """
        Finds a node by its ID (exact match or prefix).
        """
        def traverse(node):
            if node.id.startswith(identifier):
                return node
            for child in node.children:
                result = traverse(child)
                if result:
                    return result
            return None
        return traverse(self.root)

    def find_branch_head(self, branch_name: str) -> Optional[ConversationNode]:
        """
        Finds the head (tip) of a branch by name.
        Logic: Find the fork node with branch_name, then traverse down to the latest message.
        """
        # First, find the fork node with the given branch_name
        def find_fork(node):
            if node.branch_name == branch_name and node.content == "<FORK>":
                return node
            for child in node.children:
                res = find_fork(child)
                if res:
                    return res
            return None
            
        fork_node = find_fork(self.root)
        if not fork_node:
            # Special case: check if "master" (or "main") refers to the root's lineage
            if branch_name in ["master", "main"] and (self.root.branch_name == branch_name or branch_name in ["master", "main"]):
                 fork_node = self.root
            else:
                return None
        
        # Now find the deepst descendant
        current = fork_node
        while current.children:
            # We want to follow the "main" line of this branch.
            # If a child has a branch_name, it starts a NEW branch, so we should not follow it 
            # (unless it's the fork node we started with, but we are traversing children).
            
            # Prefer children that do NOT have a branch_name (belong to current branch)
            candidates = [c for c in current.children if c.branch_name is None]
            
            if candidates:
                # If there are messages in this branch, follow the latest one
                current = candidates[-1]
            else:
                # If all children are new branches (forks), then 'current' is the tip of THIS branch.
                break
            
        return current

    def checkout(self, identifier: str) -> bool:
        """
        Switches the current conversation state to the specified branch or node ID.
        
        Args:
            identifier (str): Branch name or Node ID.
            
        Returns:
            bool: True if successful, False otherwise.
        """
        # Try to find by branch name
        target_node = self.find_branch_head(identifier)
        
        # If not found, try to find by ID
        if not target_node:
            target_node = self.find_node_by_id(identifier)
            
        if target_node:
            self.current_node = target_node
            return True
        return False

    def generate_ascii_tree(self) -> str:
        """
        Generates an ASCII representation of the conversation tree.

        Returns:
            str: ASCII tree representing the conversation structure.
        """
        def tree_lines(node, prefix="", is_last=True):
            lines = []
            content = (node.content[:30] + '...') if len(node.content) > 30 else node.content
            
            node_str = f"[{node.role}] {content} (id: {node.id})"
            if node.branch_name:
                node_str = f"{{ {node.branch_name} }} " + node_str
            
            if node == self.current_node:
                 node_str += " <--- CURRENT"
                
            lines.append(f"{prefix}{'└── ' if is_last else '├── '}{node_str}")
            
            prefix += "    " if is_last else "│   "
            child_count = len(node.children)
            
            for i, child in enumerate(node.children):
                lines.extend(tree_lines(child, prefix, i == child_count - 1))
            
            return lines

        return "\n".join(tree_lines(self.root))

    def save_to_file(self, filepath: str) -> None:
        """
        Saves the conversation tree to a JSON file atomically (using flat structure).
        Writes to a temporary file first, then renames it to the target filepath.
        """
        # Flatten the tree
        nodes_map = self._flatten_tree()
        
        data = {
            "root_id": self.root.id,
            "current_node_id": self.current_node.id,
            "nodes": nodes_map
        }
        
        # atomic write: save to temp file, then rename
        temp_filepath = filepath + ".tmp"
        try:
            with open(temp_filepath, 'w') as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_filepath, filepath)
        except Exception as e:
            if os.path.exists(temp_filepath):
                try:
                    os.remove(temp_filepath)
                except OSError:
                    pass
            raise e

    def _flatten_tree(self) -> Dict[str, dict]:
        """
        Traverses the tree and returns a dictionary of node_id -> node_dict.
        """
        nodes_map = {}
        queue = [self.root]
        while queue:
            node = queue.pop(0)
            nodes_map[node.id] = node.to_dict()
            queue.extend(node.children)
        return nodes_map

    @classmethod
    def load_from_file(cls, filepath: str, provider: str = "anthropic") -> 'ConversationTree':
        """
        Loads the conversation tree from a JSON file (handling both flat and legacy nested formats).
        """
        if not os.path.exists(filepath):
            return cls(provider=provider)
            
        with open(filepath, 'r') as f:
            data = json.load(f)
            
        tree = cls(provider=provider)
        
        # Check if new flat format
        if "nodes" in data:
            nodes_map = data["nodes"]
            root_id = data["root_id"]
            current_node_id = data["current_node_id"]
            
            # 1. Instantiate all nodes
            loaded_nodes = {}
            for node_id, node_data in nodes_map.items():
                loaded_nodes[node_id] = ConversationNode.from_dict(node_data)
                
            # 2. Re-link children and parents
            for node_id, node_data in nodes_map.items():
                node = loaded_nodes[node_id]
                for child_id in node_data.get("children_ids", []):
                    if child_id in loaded_nodes:
                        node.add_child(loaded_nodes[child_id])
            
            tree.root = loaded_nodes[root_id]
            # Ensure root is named master
            if not tree.root.branch_name:
                tree.root.branch_name = "master"
            
            tree.current_node = loaded_nodes.get(current_node_id, tree.root)
            
        else:
            # Fallback to legacy nested format
            # NOTE: ConversationNode.from_dict expects flat data now, so we need to handle legacy recursively manually here
            # OR we update ConversationNode.from_dict to be smart?
            # It's cleaner to handle legacy recursion here since we are deprecating it.
             
            def legacy_from_dict(data):
                # Only need enough to bootstrap
                node = ConversationNode(
                    content=data["content"],
                    role=data["role"],
                    id=data.get("id"), # Might need to generate if missing (as before)
                    branch_name=data.get("branch_name"),
                    timestamp=datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else datetime.now() # Safety
                )
                if not node.id: node.id = uuid.uuid4().hex[:8] 
                
                for child_data in data.get("children", []):
                     child = legacy_from_dict(child_data)
                     node.add_child(child)
                return node

            tree.root = legacy_from_dict(data["root"])
            # Ensure root is named master
            if not tree.root.branch_name:
                tree.root.branch_name = "master"

            # Legacy path was list of indices
            tree.current_node = tree._navigate_path(tree.root, data["current_node_path"])
            
        return tree

    def _get_node_path(self, target_node: ConversationNode) -> List[int]:
        """
        Returns a list of indices representing the path from root to target_node.
        """
        path = []
        current = target_node
        while current.parent:
            parent = current.parent
            path.append(parent.children.index(current))
            current = parent
        return list(reversed(path))

    def _navigate_path(self, root: ConversationNode, path: List[int]) -> ConversationNode:
        """
        Navigates from root using the provided path indices.
        """
        current = root
        for index in path:
            if 0 <= index < len(current.children):
                current = current.children[index]
            else:
                # Fallback if path is invalid (shouldn't happen with consistent data)
                break
        return current