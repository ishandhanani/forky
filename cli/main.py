import argparse
from cli.commands import chat, fork, merge, history, status, visualize

def main():
    parser = argparse.ArgumentParser(description="Forky: Git-style Conversation Structure for Claude API")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Chat command
    chat_parser = subparsers.add_parser("chat", help="Start a new chat session")
    chat_parser.set_defaults(func=chat.handle_chat)

    # Fork command
    fork_parser = subparsers.add_parser("fork", help="Create a new conversation branch")
    fork_parser.add_argument("branch_name", help="Name of the new branch")
    fork_parser.set_defaults(func=fork.handle_fork)

    # Merge command
    merge_parser = subparsers.add_parser("merge", help="Merge a branch into the current conversation")
    merge_parser.add_argument("branch_name", help="Name of the branch to merge")
    merge_parser.set_defaults(func=merge.handle_merge)

    # History command
    history_parser = subparsers.add_parser("history", help="Show conversation history")
    history_parser.set_defaults(func=history.handle_history)

    # Status command
    status_parser = subparsers.add_parser("status", help="Show current conversation state")
    status_parser.set_defaults(func=status.handle_status)

    # Visualize command
    visualize_parser = subparsers.add_parser("visualize", help="Display the conversation tree")
    visualize_parser.set_defaults(func=visualize.handle_visualize)

    args = parser.parse_args()
    if hasattr(args, 'func'):
        args.func(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()