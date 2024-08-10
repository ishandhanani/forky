from core.conversation_tree import ConversationTree

def handle_chat(args):
    tree = ConversationTree()
    print("Starting a new chat session. Type '/quit' to exit, '/fork' to create a new branch, '/merge' to merge a branch, '/status' for conversation state, '/visualize' to see the conversation tree.")
    
    while True:
        user_input = input("You: ")
        
        if user_input.lower() == '/quit':
            break
        elif user_input.lower() == '/fork':
            branch_name = input("Enter the name for the new branch: ")
            tree.fork(branch_name)
            print(f"Created a new branch: {branch_name}")
        elif user_input.lower() == '/merge':
            branch_name = input("Enter the name of the branch to merge: ")
            tree.merge(branch_name)
            print(f"Merged branch: {branch_name}")
        elif user_input.lower() == '/status':
            tree.show_status()
        elif user_input.lower() == '/visualize':
            tree.visualize()
        else:
            response = tree.chat_with_claude(user_input)
            print(f"Claude: {response}")