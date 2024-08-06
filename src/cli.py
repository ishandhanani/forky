from .conversation_tree import ConversationTree

class ForkyCLI:
    def __init__(self):
        self.tree = ConversationTree()

    def chat(self):
        print("Enter your message (type 'quit' to exit, '/status' for conversation state, '/fork' to create a fork, '/merge' to merge a fork):")
        while True:
            user_input = input("You: ")
            if user_input.lower() == 'quit':
                break
            elif user_input.lower() == '/status':
                self.show_status()
            elif user_input.lower() == '/fork':
                self.tree.fork()
                print("Created a new fork. You are now in the forked conversation.")
            elif user_input.lower() == '/merge':
                try:
                    self.tree.merge()
                    print("Merged the fork back into the main conversation. You are now in the main conversation.")
                except ValueError as e:
                    print(f"Error: {e}")
            else:
                response = self.tree.chat_with_claude(user_input)
                print(f"Claude: {response}")

    def show_status(self):
        print("\nCurrent conversation state:")
        messages = self.tree.get_flat_conversation()
        for message in messages:
            print(message)
        
        if self.tree.is_in_fork():
            print("\nYou are currently in a forked conversation.")
        else:
            print("\nYou are in the main conversation.")
        print()  # Add an extra newline for better readability

def main():
    cli = ForkyCLI()
    cli.chat()

if __name__ == "__main__":
    main()