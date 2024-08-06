# Forky

Forky is a Python library for managing complex conversations with AI models in a Git-style tree structure. It allows for non-linear conversations, including branching, merging, and easy history traversal.

## Features

- Git-style conversation management
- Branching (forking) conversations
- Merging conversation branches
- Easy history traversal
- Integration with Claude API

## Installation

```bash
git clone https://github.com/ishandhanani/forky.git
cd conversation-tree
pip install -r requirements.txt
```

## Usage

Here's a basic example of how to use Forky

```python
from src.conversation_tree import ConversationTree

tree = ConversationTree()

# Start a conversation
tree.add_message("Hello, Claude!", "user")
response = tree.chat_with_claude("Hello, Claude!")
print(f"Claude: {response}")

# Fork the conversation
tree.fork()

# Continue in the forked branch
tree.add_message("What's the weather like?", "user")
response = tree.chat_with_claude("What's the weather like?")
print(f"Claude: {response}")

# Merge the fork back to main conversation
tree.merge()

# Continue in the main conversation
tree.add_message("Tell me a joke", "user")
response = tree.chat_with_claude("Tell me a joke")
print(f"Claude: {response}")
```

## Architecture

The Conversation Tree is built around two main classes:

1. `ConversationNode`: Represents a single message in the conversation.
2. `ConversationTree`: Manages the overall structure of the conversation.

### Conversation Structure

<antArtifact identifier="readme-basic-conversation-diagram" type="application/vnd.ant.mermaid" title="Basic Conversation Structure">
graph TD
    A[Root] --> B[User: Hello]
    B --> C[Assistant: Hi there!]
    C --> D[User: How are you?]
    D --> E[Assistant: I'm doing well, thank you!]