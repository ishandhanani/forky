class Node:
    def __init__(self, question, answer, prev_summary):
        self.question = question
        self.answer = answer
        self.prev_summary = prev_summary
        self.children = []

    def add_child(self, child):
        self.children.append(child)

    def printNode(self):
        print(self.question, self.answer, self.prev_summary)


class Tree:
    def __init__(self):
        self.root = Node("Root", "Root", "Root")
        self.current_node = self.root
        #blank question, blank answer, blank summary

    def add_child(self, question, answer, prev_summary):
        """Add a new child to the current node."""
        new_node = Node(question, answer, prev_summary)
        self.current_node.add_child(new_node)
        self.current_node = new_node

 


tree = Tree()
node1 = tree.add_child("Question 1", "Answer 1", "Summary 1")
node2 = tree.add_child("Question 2", "Answer 2", "Summary 2")

