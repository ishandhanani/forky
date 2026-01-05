import json
import os
import uuid
from datetime import datetime
from typing import List, Dict, Optional, Any
from .conversation_node import ConversationNode
from .api_client import APIClient
from . import database as db

class ConversationTree:
    """
    Manages a tree-like structure of conversation nodes, supporting operations
    like forking, merging, and interacting with the LLM API.
    """

    def __init__(self, provider: str = "anthropic"):
        self.root = ConversationNode(content="Root", role="system", branch_name="master")
        self.current_node = self.root
        self.api_client = APIClient(provider=provider)

    def get_branches_info(self) -> List[Dict[str, str]]:
        """
        Returns a list of all branches with their details.
        """
        branches = []
        queue = [self.root]
        visited = {self.root.id}
        
        while queue:
            node = queue.pop(0)
            if node.branch_name:
                 branches.append({
                     "name": node.branch_name,
                     "head_id": node.id, 
                 })
            
            for child in node.children:
                if child.id not in visited:
                    visited.add(child.id)
                    queue.append(child)
        return branches

    def _get_all_branch_names(self) -> set:
        """
        Helper method to retrieve a set of all active branch names in the tree.
        """
        return {b['name'] for b in self.get_branches_info()}

    def add_message(self, content: str, role: str) -> None:
        """
        Adds a new message to the conversation.

        Args:
            content (str): The content of the message.
            role (str): The role of the message sender (user, assistant, or system).
        """
        new_node = ConversationNode(content=content, role=role)
        
        # Auto-fork if we are branching off a node that already has children
        # preventing anonymous branches/divergences.
        if self.current_node.children:
            print(f"Auto-forking from non-leaf node {self.current_node.id}...")
            new_branch_name = self.fork() # Auto-generates name
            print(f"Created automatic branch: {new_branch_name}")
            # fork() updates self.current_node to the new fork node
            
        self.current_node.add_child(new_node)
        self.current_node = new_node

    def fork(self, branch_name: Optional[str] = None) -> str:
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

    def merge_branches(self, target_node_id: str, merge_prompt: str) -> dict:
        """
        Merges the target node's branch into the current branch using three-way semantic merge.
        
        Performs LCA computation, state summarization, semantic diffing, and conflict detection.
        
        Args:
            target_node_id (str): The ID of the leaf node from the other branch to merge in.
            merge_prompt (str): The user's question or prompt that synthesizes the two branches.
            
        Returns:
            dict: Merge result containing merged_state, conflicts, and new node info.
            
        Raises:
            ValueError: If merge is not allowed (same node, ancestor/descendant, no LCA).
        """
        from .merge_utils import check_merge_eligibility, get_conversation_segment, MergeRejectionReason
        from .state_summary import generate_state_summary, StateSummary
        from .semantic_diff import compute_semantic_diff
        from .merge_executor import execute_three_way_merge, format_merged_state_for_context
        
        target_node = self.find_node_by_id(target_node_id)
        if not target_node:
            raise ValueError(f"Target node {target_node_id} not found")
        
        # Check merge eligibility
        eligibility = check_merge_eligibility(self.current_node, target_node)
        
        if not eligibility.eligible:
            if eligibility.rejection_reason == MergeRejectionReason.SAME_NODE:
                raise ValueError("Cannot merge a node into itself")
            elif eligibility.rejection_reason == MergeRejectionReason.ANCESTOR_DESCENDANT:
                raise ValueError("Cannot merge ancestor with descendant - one node is an ancestor of the other")
            elif eligibility.rejection_reason == MergeRejectionReason.NO_COMMON_ANCESTOR:
                raise ValueError("Cannot merge - no common ancestor found between nodes")
            else:
                raise ValueError("Merge not allowed")
        
        lca = eligibility.lca
        
        # Get conversation segments
        segment_to_a = get_conversation_segment(lca, self.current_node)
        segment_to_b = get_conversation_segment(lca, target_node)
        segment_to_lca = self._get_history_to_node(lca)
        
        # Generate state summaries
        print("[Merge] Generating state summary for LCA...")
        summary_lca = generate_state_summary(segment_to_lca, self.api_client)
        
        print("[Merge] Generating state summary for branch A (current)...")
        summary_a = generate_state_summary(segment_to_lca + segment_to_a, self.api_client)
        
        print("[Merge] Generating state summary for branch B (target)...")
        summary_b = generate_state_summary(segment_to_lca + segment_to_b, self.api_client)
        
        # Compute semantic diffs
        print("[Merge] Computing semantic diff A...")
        diff_a = compute_semantic_diff(summary_lca, summary_a, self.api_client)
        
        print("[Merge] Computing semantic diff B...")
        diff_b = compute_semantic_diff(summary_lca, summary_b, self.api_client)
        
        # Execute three-way merge
        print("[Merge] Executing three-way merge...")
        merge_result = execute_three_way_merge(summary_lca, diff_a, diff_b, self.api_client)
        
        if not merge_result.success:
            raise ValueError(f"Merge execution failed: {merge_result.error}")
        
        # Create the Merge Node with metadata
        merge_metadata = {
            "base_id": lca.id,
            "merged_state": merge_result.merged_state.to_dict(),
            "conflicts": [c.to_dict() for c in merge_result.conflicts],
            "provenance": merge_result.provenance.to_dict()
        }
        
        merge_node = ConversationNode(
            content=merge_prompt, 
            role="user",
            node_type="merge",
            merge_metadata=merge_metadata
        )
        
        # Parent 1: Current Node (Mainline)
        self.current_node.add_child(merge_node)
        
        # Parent 2: Target Node (Incoming)
        target_node.add_child(merge_node)
        
        # Move current pointer
        self.current_node = merge_node
        
        # Build context for LLM response
        merged_context = format_merged_state_for_context(merge_result)
        
        # Prepare system context for the response
        context_messages = self.get_conversation_history()
        
        # Add merged state as developer context
        merge_system_msg = f"""You are continuing a conversation after a merge of two branches.

{merged_context}

The user's merge prompt is the message that follows. Consider both branches' context when responding.
If there are unresolved conflicts, acknowledge them and ask for clarification if needed."""
        
        context_messages.insert(0, {"role": "system", "content": merge_system_msg})
        
        # Get response
        response = self.api_client.get_response(merge_prompt, context_messages)
        self.add_message(response, "assistant")
        
        return {
            "success": True,
            "new_node_id": self.current_node.id,
            "merge_node_id": merge_node.id,
            "lca_id": lca.id,
            "conflicts": [c.to_dict() for c in merge_result.conflicts],
            "has_conflicts": merge_result.has_conflicts(),
            "merged_state": merge_result.merged_state.to_dict()
        }
    
    def _get_history_to_node(self, target_node: ConversationNode) -> List[Dict[str, str]]:
        """
        Gets conversation history from root to target node.
        
        Args:
            target_node: The node to get history up to.
            
        Returns:
            List of message dicts with role and content.
        """
        messages = []
        
        # Build path from root to target
        path = []
        current = target_node
        while current:
            path.append(current)
            if current.parents:
                current = current.parents[0]
            else:
                break
        path.reverse()
        
        for node in path:
            if node.role in ("user", "assistant"):
                messages.append({"role": node.role, "content": node.content})
        
        return messages



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

    def chat(self, message: str, provider: Optional[str] = None, model: Optional[str] = None) -> str:
        """
        Sends a message to the LLM and gets a response, using the full conversation history.

        Args:
            message (str): The message to send.
            provider (str, optional): The provider to use (openai or anthropic).
            model (str, optional): The specific model to use.

        Returns:
            str: LLM response.
        """
        if (model and model != self.api_client.model) or (provider and provider != self.api_client.provider):
            self.api_client = APIClient(provider=provider or self.api_client.provider, model=model)
            
        conversation_history = self.get_conversation_history()
        self.add_message(message, "user")
        response = self.api_client.get_response(message, conversation_history)
        self.add_message(response, "assistant")
        return response

    def chat_stream(self, message: str, provider: Optional[str] = None, model: Optional[str] = None):
        """
        Sends a message to the LLM and yields the response as chunks, updating the tree in real-time.

        Args:
            message (str): The user message to send.
            provider (Optional[str]): The LLM provider (e.g., "anthropic").
            model (Optional[str]): The specific model version to use.
        
        Yields:
             str: Chunks of the LLM response.
        """
        if (model and model != self.api_client.model) or (provider and provider != self.api_client.provider):
            self.api_client = APIClient(provider=provider or self.api_client.provider, model=model)

        conversation_history = self.get_conversation_history()
        self.add_message(message, "user")
        
        # Create a new empty assistant node
        assistant_node = ConversationNode(content="", role="assistant")
        self.current_node.add_child(assistant_node)
        self.current_node = assistant_node

        # Stream response
        for chunk in self.api_client.get_response_stream(message, conversation_history):
            assistant_node.content += chunk
            yield chunk

    def get_conversation_history(self) -> List[Dict[str, str]]:
        """
        Retrieves the conversation history. Handles DAGs by linearizing secondary parent histories.
        """
        history = []
        current = self.current_node
        
        while current:
            # Add current message
            if current.role in ["user", "assistant"]:
                history.append({"role": current.role, "content": current.content})
            elif current.role == "system" and current.content.startswith("MERGE SUMMARY:"):
                 history.append({"role": "user", "content": current.content})

            # Move to parent
            if len(current.parents) > 1:
                # Merge Node Logic
                main_parent = current.parents[0]
                secondary_parent = current.parents[1]
                
                # Identify common ancestors to avoid duplication
                main_ancestors = self._get_ancestors(main_parent)
                
                # Get unique history from secondary branch
                secondary_history_nodes = self._get_history_nodes_until(secondary_parent, stop_nodes=main_ancestors)
                
                # Format secondary history
                context_text = "Context from merged branch:\n"
                for node in secondary_history_nodes:
                    if node.role in ["user", "assistant"]:
                         context_text += f"{node.role}: {node.content}\n"
                
                # Insert this context as a system message (or user note) effectively *before* the merge node
                # Since 'history' is currently [MergeNode, ...], we append to it (which is 'before' in time)
                history.append({"role": "system", "content": context_text})
                
                current = main_parent
            elif current.parents:
                current = current.parents[0]
            else:
                current = None
            
        return list(reversed(history))

    def _get_ancestors(self, node: ConversationNode) -> set:
        """Returns a set of all ancestor IDs for a given node."""
        ancestors = set()
        queue = [node]
        while queue:
            curr = queue.pop(0)
            ancestors.add(curr.id)
            queue.extend(curr.parents)
        return ancestors

    def _get_history_nodes_until(self, start_node: ConversationNode, stop_nodes: set) -> List[ConversationNode]:
        """
        Traverses backwards from start_node until hitting a node in stop_nodes (or root).
        Returns a list of nodes (chronological/reversed order? -> We want chronological for display, 
        but we traverse backwards. This returns list in Reverse Chronological order (Leaf -> Root)).
        """
        nodes = []
        current = start_node
        while current:
            if current.id in stop_nodes:
                break
            nodes.append(current)
            if current.parents:
                current = current.parents[0]
            else:
                break
        return list(reversed(nodes)) # Return chronological: Root-ish -> Leaf

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
        """
        Checks if the current node is within a forked branch (descendant of a <FORK> node).

        Returns:
            bool: True if inside a fork, False otherwise.
        """
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

    def get_all_nodes(self) -> List[dict]:
        """
        Returns a flat list of all nodes in the tree/graph.
        Useful for visualization.
        """
        nodes = []
        queue = [self.root]
        visited = {self.root.id}
        
        while queue:
            node = queue.pop(0)
            nodes.append(node.to_dict())
            
            for child in node.children:
                if child.id not in visited:
                    visited.add(child.id)
                    queue.append(child)
        
        # Sort by timestamp to help visualization libraries replay history
        # (Assuming nodes have generic ISO timestamps, sort should work)
        nodes.sort(key=lambda x: x.get('timestamp', ''))
        return nodes

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
        Used for serialization.

        Returns:
            Dict[str, dict]: A map of all nodes in the tree.
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
            
        elif "root" in data:
            # Legacy format detected but no longer supported
            print("Warning: Detected legacy nested storage format. Backward compatibility has been removed.")
            print("Please reset your conversation history or manually migrate data.")
            # We return a fresh tree instead of crashing or trying to load
            return cls(provider=provider)
        else:
             # Unknown format or corrupted
            return cls(provider=provider)
            
        return tree

    def _get_node_path(self, target_node: ConversationNode) -> List[int]:
        """
        Returns a list of indices representing the path from root to target_node.
        Legacy helper for tree navigation.

        Args:
             target_node (ConversationNode): The destination node.

        Returns:
            List[int]: List of child indices to follow from root.
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
        Legacy helper.

        Args:
            root (ConversationNode): The starting node.
            path (List[int]): The sequence of child indices.

        Returns:
             ConversationNode: The node at the end of the path.
        """
        current = root
        for index in path:
            if 0 <= index < len(current.children):
                current = current.children[index]
            else:
                # Fallback if path is invalid (shouldn't happen with consistent data)
                break
        return current

    # --- SQLite Database Methods ---

    def save_to_db(self, conversation_id: str) -> None:
        """
        Saves the conversation tree to the SQLite database.

        Args:
            conversation_id: The unique identifier for this conversation.
        """
        # Ensure conversation exists
        if not db.conversation_exists(conversation_id):
            db.create_conversation(conversation_id)

        # Flatten tree and save all nodes
        nodes_map = self._flatten_tree()

        # First pass: save all nodes
        for node_id, node_data in nodes_map.items():
            # Serialize merge_metadata and state_summary_cache to JSON strings
            merge_metadata_json = None
            if node_data.get("merge_metadata"):
                merge_metadata_json = json.dumps(node_data["merge_metadata"])
            
            state_summary_json = None
            if node_data.get("state_summary_cache"):
                state_summary_json = json.dumps(node_data["state_summary_cache"])
            
            db.save_node(
                conversation_id=conversation_id,
                node_id=node_id,
                content=node_data["content"],
                role=node_data["role"],
                branch_name=node_data.get("branch_name"),
                timestamp=node_data.get("timestamp"),
                node_type=node_data.get("node_type", "message"),
                merge_metadata=merge_metadata_json,
                state_summary_cache=state_summary_json
            )
        
        # Second pass: save all edges (after all nodes exist)
        for node_id, node_data in nodes_map.items():
            for child_id in node_data.get("children_ids", []):
                db.add_edge(node_id, child_id)

        # Update current node pointer
        db.set_conversation_current_node(conversation_id, self.current_node.id)

    @classmethod
    def load_from_db(cls, conversation_id: str, provider: str = "anthropic") -> 'ConversationTree':
        """
        Loads the conversation tree from the SQLite database.

        Args:
            conversation_id: The unique identifier for the conversation.
            provider: The LLM provider to use.

        Returns:
            ConversationTree: The loaded conversation tree.
        """
        tree = cls(provider=provider)

        if not db.conversation_exists(conversation_id):
            return tree

        # Load all nodes
        nodes_data = db.get_all_nodes(conversation_id)

        if not nodes_data:
            return tree

        # Instantiate nodes
        loaded_nodes = {}
        for node_id, node_data in nodes_data.items():
            # Deserialize merge_metadata and state_summary_cache from JSON
            merge_metadata = None
            if node_data.get("merge_metadata"):
                try:
                    merge_metadata = json.loads(node_data["merge_metadata"])
                except (json.JSONDecodeError, TypeError):
                    pass
            
            state_summary_cache = None
            if node_data.get("state_summary_cache"):
                try:
                    state_summary_cache = json.loads(node_data["state_summary_cache"])
                except (json.JSONDecodeError, TypeError):
                    pass
            
            loaded_nodes[node_id] = ConversationNode(
                id=node_id,
                content=node_data["content"],
                role=node_data["role"],
                branch_name=node_data.get("branch_name"),
                timestamp=datetime.fromisoformat(node_data["timestamp"]) if node_data.get("timestamp") else datetime.now(),
                node_type=node_data.get("node_type", "message"),
                merge_metadata=merge_metadata,
                state_summary_cache=state_summary_cache
            )

        # Re-link parent-child relationships
        for node_id, node_data in nodes_data.items():
            node = loaded_nodes[node_id]
            for child_id in node_data.get("children_ids", []):
                if child_id in loaded_nodes:
                    node.add_child(loaded_nodes[child_id])

        # Find root (node with no parents)
        root_id = db.find_root_node_id(conversation_id)
        if root_id and root_id in loaded_nodes:
            tree.root = loaded_nodes[root_id]
        else:
            # Fallback: find node with no parents
            for node_id, node in loaded_nodes.items():
                if not node.parents:
                    tree.root = node
                    break

        # Ensure root has branch name
        if tree.root and not tree.root.branch_name:
            tree.root.branch_name = "master"

        # Set current node
        current_node_id = db.get_conversation_current_node(conversation_id)
        if current_node_id and current_node_id in loaded_nodes:
            tree.current_node = loaded_nodes[current_node_id]
        else:
            tree.current_node = tree.root

        return tree