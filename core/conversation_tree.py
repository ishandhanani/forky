from typing import List, Dict, Optional
from .conversation_node import ConversationNode
from .api_client import ClaudeClient
import json

class ConversationTree:
    """
    Manages a tree-like structure of conversation nodes, supporting operations
    like forking, merging, and interacting with the Claude API.
    """

    def __init__(self):
        self.root = ConversationNode(content="Root", role="system")
        self.current_node = self.root
        self.claude_client = ClaudeClient()

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

    def fork(self) -> None:
        """
        Creates a new branch in the conversation.

        Args:
            branch_name (str): The name of the new branch.
        """
        fork_node = ConversationNode(content="<FORK>", role="system")
        self.current_node.add_child(fork_node)
        self.current_node = fork_node

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
        merge_assistant_message = f"Here's a summary of another conversation branch: {summary}"
        
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
            summary = self.claude_client.summarize(messages, merge_prompt)
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

    def chat_with_claude(self, message: str) -> str:
        """
        Sends a message to Claude and gets a response, using the full conversation history.

        Args:
            message (str): The message to send to Claude.

        Returns:
            str: Claude's response.
        """
        conversation_history = self.get_conversation_history()
        self.add_message(message, "user")
        response = self.claude_client.get_response(message, conversation_history)
        self.add_message(response, "assistant")
        return response

    def get_conversation_history(self) -> List[Dict[str, str]]:
        """
        Retrieves the conversation history, excluding system messages.

        Returns:
            List[Dict[str, str]]: A list of dictionaries representing the conversation history.
        """
        history = []
        
        def traverse_tree(node):
            if node.role in ["user", "assistant"]:
                history.append({"role": node.role, "content": node.content})
            elif node.role == "system" and node.content.startswith("MERGE SUMMARY:"):
                # Include merge summaries as user messages
                history.append({"role": "user", "content": node.content})
            for child in node.children:
                traverse_tree(child)

        traverse_tree(self.root)
        return history

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
        messages = []
        current = self.root
        while current:
            messages.append(f"{current.role}: {current.content}")
            if current.children:
                current = current.children[0]
            else:
                break
        return messages

    def is_in_fork(self) -> bool:
        current = self.current_node
        while current.parent:
            if current.content == "<FORK>":
                return True
            current = current.parent
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
            lines.append(f"{prefix}{'└── ' if is_last else '├── '}[{node.role}] {content}")
            
            prefix += "    " if is_last else "│   "
            child_count = len(node.children)
            
            for i, child in enumerate(node.children):
                lines.extend(tree_lines(child, prefix, i == child_count - 1))
            
            return lines

        return "\n".join(tree_lines(self.root))
    
    def gen_text_tree(self) -> str:
        """
        Generates a text representation of the conversation tree.

        Returns:
            str: Text tree representing the conversation structure.
        """
        def tree_lines(node, level=0):
            lines = []
            lines.append(f"{'  ' * level}[{node.role}] {node.content}")
            for child in node.children:
                lines.extend(tree_lines(child, level + 1))
            return lines

        return "\n".join(tree_lines(self.root))
    


    def reset_tree(self) -> None:
        """
        Resets the conversation tree to its initial state.
        """
        
        self.root = ConversationNode(content="Root", role="system")
        self.current_node = self.root


    def export_file(self, filename: str) -> bool:
        """
        Exports the conversation tree to a JSON file
        input argument: Name of file to save to.

        """

        try:
            # content, role, children
            def getNodes(node):
                return {
                    "content": node.content,
                    "role": node.role,
                    "children": [getNodes(child) for child in node.children]
                }

            with open(filename, 'w') as f:
                json.dump(getNodes(self.root), f, indent=4)

            return True
            
        except:
            return False
    

    def load_file(self, filename: str) -> bool:
        """
        Loads a conversation tree from a JSON file
        input argument: Name of file to load from.

        """

        self.reset_tree()



        return True
