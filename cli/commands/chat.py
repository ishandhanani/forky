from core.conversation_tree import ConversationTree
import os

DEFAULT_STATE_FILE = ".forky_state.json"

def handle_chat(args):
    state_file = args.file if hasattr(args, 'file') and args.file else DEFAULT_STATE_FILE
    
    if os.path.exists(state_file):
        print(f"Loading conversation from {state_file}...")
        tree = ConversationTree.load_from_file(state_file, provider=args.provider)
    else:
        tree = ConversationTree(provider=args.provider)
        
    print(f"Starting chat with {args.provider}. Enter your message (type 'quit' to exit, '/status' for conversation state, '/fork [name]' to create a fork, '/merge' to merge a fork, '/checkout [name_or_id]' to switch branches/nodes, '/visualize' to see the conversation tree, '/history' to view full conversation history):")
    
    while True:
        try:
            user_input = input("You: ")
            
            if user_input.lower() == 'quit':
                break
            elif user_input.lower() == '/status':
                show_status(tree)
            elif user_input.lower().startswith('/fork'):
                parts = user_input.split(maxsplit=1)
                branch_name = parts[1] if len(parts) > 1 else None
                try:
                    branch_name = tree.fork(branch_name)
                    print(f"Created a new named {branch_name}. You are now in the forked conversation.")
                    tree.save_to_file(state_file)
                except ValueError as e:
                    print(f"Error: {e}")
            elif user_input.lower().startswith('/checkout'):
                args_str = user_input[9:].strip()
                if not args_str:
                    print("Usage: /checkout [branch_name_or_node_id] [-b new_branch_name]")
                else:
                    new_branch_name = None
                    identifier = args_str
                    
                    # Check for -b flag for forking
                    if " -b " in args_str:
                        parts = args_str.split(" -b ", 1)
                        identifier = parts[0].strip()
                        new_branch_name = parts[1].strip()
                    
                    if tree.checkout(identifier):
                        print(f"Checked out to '{identifier}'.")
                        if new_branch_name:
                            try:
                                tree.fork(new_branch_name)
                                print(f"Created and switched to new branch '{new_branch_name}'.")
                            except ValueError as e:
                                print(f"Error creating branch: {e}")
                        
                        tree.save_to_file(state_file)
                    else:
                        print(f"Could not find branch or node with identifier '{identifier}'.")
            elif user_input.lower() == '/merge':
                try:
                    merge_prompt = input("Enter a prompt for the merge summary (optional): ").strip()
                    tree.merge(merge_prompt)
                    print("Merged the fork back into the main conversation. You are now in the main conversation.")
                    tree.save_to_file(state_file)
                except ValueError as e:
                    print(f"Error: {e}")
            elif user_input.lower() == '/visualize':
                visualize_tree(tree)
            elif user_input.lower() == '/history':
                show_full_history(tree)
            elif user_input.startswith('/'):
                print("Unknown command. Valid commands are: /status, /fork, /merge, /checkout, /visualize, /history, quit")
            else:
                response = tree.chat(user_input)
                print(f"Assistant: {response}")
                tree.save_to_file(state_file)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"An error occurred: {e}")
            # Try to save state even if error occurs
            tree.save_to_file(state_file)

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