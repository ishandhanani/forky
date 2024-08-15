class Node:
    def __init__(self, question, answer, prev_summary, parent):
        self.question = question
        self.answer = answer
        self.prev_summary = prev_summary
        self.children = []
        self.parent = parent

    def add_child(self, child):
        self.children.append(child)




class ConversationTree:
    def __init__(self):
        self.root = Node("Root", "Root", "Root", None)
        self.current_node = self.root







ConversationTree()
