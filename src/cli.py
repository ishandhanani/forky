import argparse
import sys
from .conversation_tree import ConversationTree

class ForkyCLI:
    def __init__(self):
        self.tree = ConversationTree()
        self.parser = self.create_parser()

    def create_parser(self):
        parser = argparse.ArgumentParser(description="Forky: Git-style conversation management with Claude")
        subparsers = parser.add_subparsers(dest="command", help="Available commands")

        # chat command
        chat_parser = subparsers.add_parser("chat", help="Start or continue a conversation")
        chat_parser.add_argument("message", nargs="?", help="Message to send to Claude")

        # branch command (equivalent to Git's branch)
        subparsers.add_parser("branch", help="List all branches")

        # checkout command (equivalent to Git's checkout for creating new branches)
        checkout_parser = subparsers.add_parser("checkout", help="Create a new branch or switch to an existing one")
        checkout_parser.add_argument("-b", dest="new_branch", action="store_true", help="Create a new branch")
        checkout_parser.add_argument("branch_name", help="Name of the branch to create or switch to")

        # merge command
        merge_parser = subparsers.add_parser("merge", help="Merge the current branch into the main conversation")

        # log command (equivalent to Git's log)
        subparsers.add_parser("log", help="Show conversation history")

        # status command (equivalent to Git's status)
        subparsers.add_parser("status", help="Show the current state of the conversation")

        return parser

    def run(self):
        args = self.parser.parse_args()

        if args.command == "chat":
            self.chat(args.message)
        elif args.command == "branch":
            self.list_branches()
        elif args.command == "checkout":
            self.checkout(args.branch_name, args.new_branch)
        elif args.command == "merge":
            self.merge()
        elif args.command == "log":
            self.show_history()
        elif args.command == "status":
            self.show_status()
        else:
            self.parser.print_help()

    def chat(self, message=None):
        if message:
            response = self.tree.chat_with_claude(message)
            print(f"Claude: {response}")
        else:
            print("Enter your message (type 'quit' to exit):")
            while True:
                user_input = input("You: ")
                if user_input.lower() == 'quit':
                    break
                response = self.tree.chat_with_claude(user_input)
                print(f"Claude: {response}")

    def list_branches(self):
        # This is a placeholder. In a full implementation, we would track branches.
        print("Branches:")
        print("* main")

    def checkout(self, branch_name, new_branch):
        if new_branch:
            print(f"Creating and switching to new branch: {branch_name}")
            self.tree.fork()
        else:
            print(f"Switching to branch: {branch_name}")
        # In a full implementation, we would track and switch between branches here.

    def merge(self):
        try:
            self.tree.merge()
            print("Branch merged successfully.")
        except ValueError as e:
            print(f"Error: {e}")

    def show_history(self):
        history = self.tree.get_conversation_history()
        for message in history:
            print(f"{message['role'].capitalize()}: {message['content']}")

    def show_status(self):
        print("Current conversation state:")
        self.tree.print_tree()

def main():
    cli = ForkyCLI()
    cli.run()

if __name__ == "__main__":
    main()