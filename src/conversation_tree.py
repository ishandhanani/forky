from typing import List, Dict, Optional
from .conversation_node import ConversationNode
from .api_client import ClaudeClient

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

    def fork(self, branch_name: str) -> None:
        """
        Creates a new branch in the conversation.

        Args:
            branch_name (str): The name of the new branch.
        """
        fork_node = ConversationNode(content="<FORK>", role="system")
        self.current_node.add_child(fork_node)
        self.current_node = fork_node

    def merge(self) -> None:
        """
        Merges the current branch back into the main conversation.
        """
        # Find the fork node
        fork_node = self.current_node
        while fork_node.content != "<FORK>" and fork_node.parent:
            fork_node = fork_node.parent

        if fork_node.content != "<FORK>":
            raise ValueError("No fork found to merge")

        # Summarize the forked conversation
        summary = self._summarize_fork(fork_node)

        # Move back to the main conversation
        self.current_node = fork_node.parent
        
        # Add the summary as a system message
        self.add_message(f"MERGE SUMMARY: {summary}", "system")

    def _summarize_fork(self, fork_node: ConversationNode) -> str:
        """
        Summarizes the conversation in a forked branch.

        Args:
            fork_node (ConversationNode): The node representing the fork.

        Returns:
            str: A summary of the forked conversation.
        """
        messages = self._collect_messages(fork_node)
        summary_prompt = "Please summarize the key points of the following conversation:\n\n" + "\n".join(messages)
        return self.claude_client.get_response(summary_prompt)

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
        while current:
            if current.role != "system":
                messages.append(f"{current.role}: {current.content}")
            if current.children:
                current = current.children[0]  # Assuming linear conversation in a fork
            else:
                break
        return messages

    def chat_with_claude(self, message: str) -> str:
        """
        Sends a message to Claude and gets a response.

        Args:
            message (str): The message to send to Claude.

        Returns:
            str: Claude's response.
        """
        conversation_history = self.get_conversation_history()
        
        # Add the new user message to the tree before sending to Claude
        self.add_message(message, "user")
        
        response = self.claude_client.get_response(message, conversation_history)
        self.add_message(response, "assistant")
        return response

    def get_conversation_history(self) -> List[Dict[str, str]]:
        """
        Retrieves the current conversation history.

        Returns:
            List[Dict[str, str]]: A list of dictionaries representing the conversation history.
        """
        history = []
        current = self.current_node
        while current.parent:
            if current.role in ["user", "assistant"]:
                history.insert(0, {"role": current.role, "content": current.content})
            current = current.parent
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