from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict
import os
from core.conversation_tree import ConversationTree

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

# State management
DATA_DIR = ".forky_conversations"
os.makedirs(DATA_DIR, exist_ok=True)
PROVIDER = "openai" 

# Stateless approach: file ID is passed in requests

def get_file_path(file_id):
    """Returns the full file path for a given conversation ID."""
    return os.path.join(DATA_DIR, f"{file_id}.json")

def load_tree(file_id=None):
    """
    Loads a conversation tree from disk.
    
    If file_id is provided, loads that specific conversation.
    Otherwise, defaults to the most recently modified conversation.
    Does NOT maintain global state.
    """
    target_id = file_id
    
    if not target_id:
        # If no explicit file_id, try to find the most recent one or create default
        files = [f for f in os.listdir(DATA_DIR) if f.endswith(".json")]
        if files:
            # Sort by mtime descending
            files.sort(key=lambda x: os.path.getmtime(os.path.join(DATA_DIR, x)), reverse=True)
            target_id = files[0].replace(".json", "")
        else:
            target_id = "default"
    
    path = get_file_path(target_id)
    # If path doesn't exist and it's 'default', load_from_file handles it by returning new tree
    # If path doesn't exist and it's specific ID, load_from_file also handles it (returns empty tree currently)
    # But ideally we might want to 404 if specific ID missing? 
    # Current behavior of load_from_file: "if not os.path.exists... return cls(provider)". 
    # This might hide 404s. But for now, we invoke it.
    
    return ConversationTree.load_from_file(path, provider=PROVIDER)

def save_tree(tree, file_id):
    """Saves the given conversation tree to the specified file ID."""
    path = get_file_path(file_id)
    tree.save_to_file(path)

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

class CreateConversationRequest(BaseModel):
    """Request model for creating a new conversation."""
    name: Optional[str] = None

# Endpoints

@app.get("/conversations")
def list_conversations():
    """Lists all available conversations, sorted by last update time."""
    conversations = []
    if not os.path.exists(DATA_DIR):
        return {"conversations": []}
        
    for filename in os.listdir(DATA_DIR):
        if filename.endswith(".json"):
            file_id = filename.replace(".json", "")
            path = os.path.join(DATA_DIR, filename)
            try:
                # We could load the tree to get the root content as a title, but that's expensive
                # checking mtime for sorting
                mtime = os.path.getmtime(path)
                conversations.append({
                    "id": file_id,
                    "name": file_id, # Could improve naming later
                    "updated_at": mtime,
                    # "is_active": False # Concept of active is client-side now
                })
            except Exception:
                continue
                
    # Sort by updated_at desc
    conversations.sort(key=lambda x: x["updated_at"], reverse=True)
    return {"conversations": conversations}

@app.post("/conversations")
def create_conversation(request: CreateConversationRequest):
    """Creates a new empty conversation with an optional name."""
    import uuid
    file_id = request.name or f"conv-{uuid.uuid4().hex[:8]}"
    # sanitize filename
    file_id = "".join(c for c in file_id if c.isalnum() or c in ('-', '_'))

    if not file_id:
        file_id = f"conv-{uuid.uuid4().hex[:8]}"
    
    path = get_file_path(file_id)
    if os.path.exists(path):
         raise HTTPException(status_code=400, detail="Conversation already exists")
         
    # Create new empty tree
    tree = ConversationTree(provider=PROVIDER)
    tree.save_to_file(path)
    
    return {"id": file_id, "message": "Conversation created"}

@app.post("/conversations/{file_id}/load") # Kept for compat, but essentially a verify endpoint
def load_conversation(file_id: str):
    """Verifies that the conversation exists."""
    path = get_file_path(file_id)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    return {"id": file_id, "message": "Conversation loaded"}

@app.delete("/conversations/{file_id}")
def delete_conversation(file_id: str):
    """Deletes a conversation by its ID."""
    path = get_file_path(file_id)
    if os.path.exists(path):
        os.remove(path)
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
            path = get_file_path(request.conversation_id)
            tree.save_to_file(path)
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
    
    path = get_file_path(request.conversation_id)
    tree.save_to_file(path)
    return {"message": msg, "current_node_id": tree.current_node.id}

@app.post("/fork")
def fork(request: ForkRequest):
    """Creates a new branch from the current node."""
    tree = load_tree(request.conversation_id)
    try:
        branch_name = tree.fork(request.branch_name)
        path = get_file_path(request.conversation_id)
        tree.save_to_file(path)
        return {"branch_name": branch_name}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))



@app.post("/merge_branches")
def merge_branches(request: MergeBranchesRequest):
    """
    Merges a target branch into the current branch (DAG merge).
    """
    tree = load_tree(request.conversation_id)
    try:
        tree.merge_branches(request.target_node_id, request.merge_prompt)
        path = get_file_path(request.conversation_id)
        tree.save_to_file(path)
        return {"message": "Branches merged successfully", "new_node_id": tree.current_node.id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server.app:app", host="0.0.0.0", port=8000, reload=True)
