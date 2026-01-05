from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict
import os
from core.conversation_tree import ConversationTree
from core import database as db

app = FastAPI(
    title="Forky API",
    description="API for the Forky conversation management tool.",
    version="0.1.0"
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development convenience
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Provider configuration
PROVIDER = "openai" 


@app.on_event("startup")
def startup_event():
    """Initialize database and run migrations on server startup."""
    db.init_db()
    migrated = db.migrate_json_to_sqlite()
    if migrated > 0:
        print(f"Migrated {migrated} conversations from JSON to SQLite")


def load_tree(conversation_id: str = None) -> ConversationTree:
    """
    Loads a conversation tree from the database.
    
    If conversation_id is provided, loads that specific conversation.
    Otherwise, defaults to the most recently modified conversation.
    """
    if not conversation_id:
        # Get most recent conversation
        conversations = db.list_conversations()
        if conversations:
            conversation_id = conversations[0]["id"]
        else:
            conversation_id = "default"
            db.create_conversation(conversation_id)
    
    return ConversationTree.load_from_db(conversation_id, provider=PROVIDER)


def save_tree(tree: ConversationTree, conversation_id: str) -> None:
    """Saves the given conversation tree to the database."""
    tree.save_to_db(conversation_id)

# Data models
class MessageRequest(BaseModel):
    """Request model for sending a message to the chat."""
    message: str
    conversation_id: str
    provider: Optional[str] = None
    model: Optional[str] = None

class CheckoutRequest(BaseModel):
    """Request model for checking out a specific node or branch."""
    identifier: str
    conversation_id: str
    branch_name: Optional[str] = None

class ForkRequest(BaseModel):
    """Request model for creating a new fork."""
    branch_name: Optional[str] = None
    conversation_id: str

class MergeRequest(BaseModel):
    """Request model for merging the current branch."""
    merge_prompt: Optional[str] = ""
    conversation_id: str

class MergeBranchesRequest(BaseModel):
    """Request model for DAG merge of two branches."""
    target_node_id: str
    merge_prompt: str
    conversation_id: str

class MergeEligibilityRequest(BaseModel):
    """Request model for checking merge eligibility."""
    node_a_id: str
    node_b_id: str
    conversation_id: str

class CreateConversationRequest(BaseModel):
    """Request model for creating a new conversation."""
    name: Optional[str] = None

# Endpoints

@app.get("/conversations")
def list_conversations():
    """Lists all available conversations, sorted by last update time."""
    conversations = db.list_conversations()
    return {"conversations": conversations}

@app.post("/conversations")
def create_conversation(request: CreateConversationRequest):
    """Creates a new empty conversation with an optional name."""
    import uuid
    conversation_id = request.name or f"conv-{uuid.uuid4().hex[:8]}"
    # sanitize
    conversation_id = "".join(c for c in conversation_id if c.isalnum() or c in ('-', '_'))

    if not conversation_id:
        conversation_id = f"conv-{uuid.uuid4().hex[:8]}"
    
    if db.conversation_exists(conversation_id):
        raise HTTPException(status_code=400, detail="Conversation already exists")
    
    # Create new empty tree and save to database
    tree = ConversationTree(provider=PROVIDER)
    tree.save_to_db(conversation_id)
    
    return {"id": conversation_id, "message": "Conversation created"}

@app.post("/conversations/{conversation_id}/load")
def load_conversation(conversation_id: str):
    """Verifies that the conversation exists."""
    if not db.conversation_exists(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    return {"id": conversation_id, "message": "Conversation loaded"}


class RenameConversationRequest(BaseModel):
    """Request model for renaming a conversation."""
    name: str


@app.patch("/conversations/{conversation_id}")
def rename_conversation(conversation_id: str, request: RenameConversationRequest):
    """Renames a conversation."""
    if not request.name or not request.name.strip():
        raise HTTPException(status_code=400, detail="Name cannot be empty")
    
    if db.rename_conversation(conversation_id, request.name.strip()):
        return {"id": conversation_id, "name": request.name.strip(), "message": "Conversation renamed"}
    raise HTTPException(status_code=404, detail="Conversation not found")


@app.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str):
    """Deletes a conversation by its ID."""
    if db.delete_conversation(conversation_id):
        return {"message": "Conversation deleted"}
    raise HTTPException(status_code=404, detail="Conversation not found")

@app.get("/tree")
def get_tree(conversation_id: Optional[str] = None):
    """
    Returns the full tree structure of the conversation.
    
    Includes all nodes, edges, and the current active node.
    """
    tree = load_tree(conversation_id)
    # Helper to serialize recursively
    def serialize_node(node):
        return {
            "id": node.id,
            "role": node.role,
            "content": node.content,
            "branch_name": node.branch_name,
            "children": [serialize_node(c) for c in node.children],
            "is_current": node == tree.current_node
        }
    
    return {
        "root": serialize_node(tree.root),
        "current_node_id": tree.current_node.id,
        "conversation_id": conversation_id
    }

@app.get("/graph")
def get_graph(conversation_id: Optional[str] = None):
    """
    Returns a flat list of all nodes for graph visualization.
    """
    tree = load_tree(conversation_id)
    nodes = tree.get_all_nodes()
    return {
        "nodes": nodes,
        "current_node_id": tree.current_node.id,
        "root_id": tree.root.id
    }

@app.get("/history")
def get_history(conversation_id: Optional[str] = None):
    """Returns the linear conversation history from the root to the current node."""
    tree = load_tree(conversation_id)
    history = tree.get_flat_conversation()
    return {"history": history}

@app.post("/chat")
def chat(request: MessageRequest):
    """
    Sends a message to the LLM and gets a response.
    
    Updates the conversation tree with the new user message and assistant response.
    """
    tree = load_tree(request.conversation_id)
    
    async def generate():
        try:
            for chunk in tree.chat_stream(request.message, provider=request.provider, model=request.model):
                yield chunk
            
            # Save after completion
            tree.save_to_db(request.conversation_id)
        except Exception as e:
            # In a stream, we can't easily raise HTTP exception once started, 
            # but we can log or yield an error message if caught early.
            print(f"Streaming error: {e}")
            yield f"[Error: {str(e)}]"

    return StreamingResponse(generate(), media_type="text/plain")

@app.post("/checkout")
def checkout(request: CheckoutRequest):
    """Checks out to a valid node ID or branch name."""
    tree = load_tree(request.conversation_id)
    success = tree.checkout(request.identifier)
    if not success:
         raise HTTPException(status_code=404, detail="Node or branch not found")
    
    msg = f"Checked out to {request.identifier}"

    if request.branch_name:
        try:
            tree.fork(request.branch_name)
            msg += f" and created branch {request.branch_name}"
        except ValueError as e:
             raise HTTPException(status_code=400, detail=str(e))
    
    tree.save_to_db(request.conversation_id)
    return {"message": msg, "current_node_id": tree.current_node.id}

@app.post("/fork")
def fork(request: ForkRequest):
    """Creates a new branch from the current node."""
    tree = load_tree(request.conversation_id)
    try:
        branch_name = tree.fork(request.branch_name)
        tree.save_to_db(request.conversation_id)
        return {"branch_name": branch_name}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))



@app.post("/check_merge_eligibility")
def check_merge_eligibility(request: MergeEligibilityRequest):
    """
    Checks if two nodes can be merged (neither is ancestor of the other, have common LCA).
    """
    from core.merge_utils import check_merge_eligibility as check_eligibility
    
    tree = load_tree(request.conversation_id)
    
    node_a = tree.find_node_by_id(request.node_a_id)
    node_b = tree.find_node_by_id(request.node_b_id)
    
    if not node_a:
        raise HTTPException(status_code=404, detail=f"Node A ({request.node_a_id}) not found")
    if not node_b:
        raise HTTPException(status_code=404, detail=f"Node B ({request.node_b_id}) not found")
    
    eligibility = check_eligibility(node_a, node_b)
    return eligibility.to_dict()


@app.post("/merge_branches")
def merge_branches(request: MergeBranchesRequest):
    """
    Merges a target branch into the current branch using three-way semantic merge.
    
    Returns merged state, conflicts, and provenance information.
    """
    tree = load_tree(request.conversation_id)
    try:
        result = tree.merge_branches(request.target_node_id, request.merge_prompt)
        tree.save_to_db(request.conversation_id)
        return {
            "message": "Branches merged successfully",
            "new_node_id": result["new_node_id"],
            "merge_node_id": result["merge_node_id"],
            "lca_id": result["lca_id"],
            "conflicts": result["conflicts"],
            "has_conflicts": result["has_conflicts"],
            "merged_state": result["merged_state"]
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class DeleteNodeRequest(BaseModel):
    """Request model for deleting a node."""
    node_id: str
    conversation_id: str


@app.post("/delete_node")
def delete_node(request: DeleteNodeRequest):
    """
    Deletes a node (or turn pair) from the conversation tree.
    
    If deleting an assistant node with a user parent, both are deleted.
    Only works for nodes with exactly one parent (not merge results).
    Children are inherited by the ancestor.
    """
    # Check if node has single parent
    parents = db.get_node_parents(request.node_id)
    
    if len(parents) == 0:
        raise HTTPException(status_code=400, detail="Cannot delete root node")
    
    if len(parents) > 1:
        raise HTTPException(status_code=400, detail="Cannot delete merge node (has multiple parents)")
    
    # For turn pairs: also check if the user parent (which we'll delete too) has multiple parents
    # This is a merged node in the UI sense
    parent_id = parents[0]
    parent_parents = db.get_node_parents(parent_id)
    if len(parent_parents) > 1:
        raise HTTPException(status_code=400, detail="Cannot delete turn that resulted from a merge (user node has multiple parents)")
    
    # Check if this is the current node or its user parent - if so, we'll need to update
    tree = load_tree(request.conversation_id)
    current_id = tree.current_node.id
    
    success, actual_parent_id = db.delete_node(request.node_id)
    
    if success:
        # If current node was deleted (either the target node or its user parent), move to actual parent
        # Check if current node still exists
        if current_id == request.node_id or current_id == parents[0]:
            db.set_conversation_current_node(request.conversation_id, actual_parent_id)
        
        return {"message": "Node deleted", "parent_id": actual_parent_id}
    
    raise HTTPException(status_code=404, detail="Node not found")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server.app:app", host="0.0.0.0", port=8000, reload=True)
