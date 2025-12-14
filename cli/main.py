import argparse
from cli.commands import chat

def main():
    parser = argparse.ArgumentParser(description="Forky: Git-style Conversation Structure for Claude API")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Chat command
    chat_parser = subparsers.add_parser("chat", help="Start a new chat session")
    chat_parser.add_argument("--provider", choices=["anthropic", "openai"], default="anthropic", help="LLM provider to use (default: anthropic)")
    chat_parser.add_argument("--file", help="Path to the conversation state file (default: .forky_state.json)")
    chat_parser.set_defaults(func=chat.handle_chat)

    args = parser.parse_args()
    if hasattr(args, 'func'):
        args.func(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()