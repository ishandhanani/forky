from core.conversation_tree import ConversationTree

def handle_chat(args):
    tree = ConversationTree()
    print("Enter your message (type 'quit' to exit, '/status' for conversation state, '/fork' to create a fork, '/merge' to merge a fork, '/visualize' to see the conversation tree, '/history' to view full conversation history):")
    
    while True:
        user_input = input("You: ")
        
        if user_input.lower() == 'quit':
            break
        elif user_input.lower() == '/status':
            show_status(tree)
        elif user_input.lower() == '/fork':
            tree.fork()
            print("Created a new fork. You are now in the forked conversation.")
        elif user_input.lower() == '/merge':
            try:
                merge_prompt = input("Enter a prompt for the merge summary (optional): ").strip()
                tree.merge(merge_prompt)
                print("Merged the fork back into the main conversation. You are now in the main conversation.")
            except ValueError as e:
                print(f"Error: {e}")
        elif user_input.lower() == '/visualize':
            visualize_tree(tree)
        elif user_input.lower() == '/history':
            show_full_history(tree)
        else:
            response = tree.chat_with_claude(user_input)
            print(f"Claude: {response}")

def show_full_history(tree):
    history = tree.get_conversation_history()
    print("\nFull Conversation History:")
    for message in history:
        content = message['content']
        if len(content) > 50:
            content = content[:47] + "..."
        print(f"{message['role'].capitalize()}: {content}")

def visualize_tree(tree):
    ascii_tree = tree.generate_ascii_tree()
    print("\nConversation Tree Visualization:")
    print(ascii_tree)

def show_status(tree):
    print("\nCurrent conversation state:")
    messages = tree.get_flat_conversation()
    for message in messages:
        print(message)
    
    if tree.is_in_fork():
        print("\nYou are currently in a forked conversation.")
    else:
        print("\nYou are in the main conversation.")
    print()  # Add an extra newline for better readability