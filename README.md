# Forky: Git-style Conversation Structure for LLMs 

Forky is a command-line interface (CLI) tool that implements a git-style conversation structure for interactions with the Claude API. It allows users to create, manage, and navigate through branching conversations, providing a unique way to explore different conversation paths with an AI assistant.

## Features

- **Conversation Tree Structure**: Manage conversations in a tree-like structure, allowing for branching and merging of dialogue paths.
- **Forking**: Create new branches in the conversation to explore alternative dialogue paths.
- **Merging**: Combine forked conversations back into the main thread with automatic summarization.
- **CLI Interface**: Easy-to-use command-line interface for interacting with the conversation tree.
- **Visualization**: ASCII-based tree visualization of the conversation structure.
- **History Tracking**: View and manage the full conversation history.

## Installation

1. Clone the repository:
   ```
   git clone https://github.com/ishandhanani/forky.git
   cd forky
   ```

2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Set up your Anthropic API key:
   - Create a `.env` file in the project root.
   - Add your API key: `ANTHROPIC_API_KEY=your_api_key_here`

## Usage

Run the CLI application:

```
python -m cli.main chat
```

Available commands:
- Type your message to chat with Claude
- `/fork`: Create a new branch in the conversation
- `/merge`: Merge the current branch back into the main conversation
- `/status`: View the current conversation state
- `/visualize`: See an ASCII representation of the conversation tree
- `/history`: View the full conversation history
- `quit`: Exit the application

## Project Structure

- `api_client.py`: Handles communication with the Claude API
- `cli.py`: Implements the command-line interface
- `conversation_node.py`: Defines the ConversationNode class for tree structure
- `conversation_tree.py`: Manages the overall conversation tree and operations

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. Here are some things I'd like to add:

- [ ] Branching: Implement named branches for easier navigation and management.
- [ ] Checkout: Add ability to switch between different branches or specific conversation points.
- [ ] Rebase: Allow reorganizing and combining conversation branches.
- [ ] Cherry-pick: Implement selecting and applying specific messages from other branches.
- [ ] Stash: Add functionality to temporarily save and reapply uncommitted changes.
- [ ] Tags: Allow marking significant points in the conversation history.
- [ ] Diff: Create a tool to compare differences between branches or commits.
- [ ] Reset: Implement the ability to move the conversation back to a previous state.
- [ ] LLMs: Support other LLM models besides Claude

## Open questions 

- [ ] Should each node should be a user/assistant exchnage, not just a single message

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.