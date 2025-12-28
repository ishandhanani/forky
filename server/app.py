from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict
import os
from core.conversation_tree import ConversationTree

app = FastAPI()

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

# Global state to track current active file
current_file_id = None

def get_file_path(file_id):
    return os.path.join(DATA_DIR, f"{file_id}.json")

def load_tree(file_id=None):
    global current_file_id
    target_id = file_id or current_file_id
    
    if not target_id:
        # If no active file, try to find the most recent one or create default
        files = [f for f in os.listdir(DATA_DIR) if f.endswith(".json")]
        if files:
            # Sort by mtime descending
            files.sort(key=lambda x: os.path.getmtime(os.path.join(DATA_DIR, x)), reverse=True)
            target_id = files[0].replace(".json", "")
        else:
            target_id = "default"
    
    current_file_id = target_id
    path = get_file_path(target_id)
    return ConversationTree.load_from_file(path, provider=PROVIDER)

def save_tree(tree):
    path = get_file_path(current_file_id)
    tree.save_to_file(path)

# Data models
class MessageRequest(BaseModel):
    message: str
    conversation_id: str

class CheckoutRequest(BaseModel):
    identifier: str
    conversation_id: str
    branch_name: Optional[str] = None

class ForkRequest(BaseModel):
    branch_name: Optional[str] = None
    conversation_id: str

class MergeRequest(BaseModel):
    merge_prompt: Optional[str] = ""
    conversation_id: str

class CreateConversationRequest(BaseModel):
    name: Optional[str] = None

# Endpoints

@app.get("/conversations")
def list_conversations():
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
                    "is_active": file_id == current_file_id
                })
            except Exception:
                continue
                
    # Sort by updated_at desc
    conversations.sort(key=lambda x: x["updated_at"], reverse=True)
    return {"conversations": conversations}

@app.post("/conversations")
def create_conversation(request: CreateConversationRequest):
    global current_file_id
    import uuid
    file_id = request.name or f"conv-{uuid.uuid4().hex[:8]}"
    # sanitize filename
    file_id = "".join(c for c in file_id if c.isalnum() or c in ('-', '_'))
    
    path = get_file_path(file_id)
    if os.path.exists(path):
         raise HTTPException(status_code=400, detail="Conversation already exists")
         
    # Create new empty tree
    tree = ConversationTree(provider=PROVIDER)
    tree.save_to_file(path)
    
    current_file_id = file_id
    return {"id": file_id, "message": "Conversation created"}

@app.post("/conversations/{file_id}/load")
def load_conversation(file_id: str):
    global current_file_id
    path = get_file_path(file_id)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    current_file_id = file_id
    return {"id": file_id, "message": "Conversation loaded"}

@app.delete("/conversations/{file_id}")
def delete_conversation(file_id: str):
    global current_file_id
    path = get_file_path(file_id)
    if os.path.exists(path):
        os.remove(path)
        if current_file_id == file_id:
            current_file_id = None
        return {"message": "Conversation deleted"}
    raise HTTPException(status_code=404, detail="Conversation not found")

@app.get("/tree")
def get_tree(conversation_id: Optional[str] = None):
    # If explicit ID provided, use it. Otherwise fall back to global state (backward compat/default)
    target_id = conversation_id or current_file_id
    tree = load_tree(target_id)
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
        "conversation_id": target_id
    }

@app.get("/history")
def get_history(conversation_id: Optional[str] = None):
    target_id = conversation_id or current_file_id
    tree = load_tree(target_id)
    history = tree.get_flat_conversation()
    return {"history": history}

@app.post("/chat")
def chat(request: MessageRequest):
    tree = load_tree(request.conversation_id)
    try:
        response = tree.chat(request.message)
        save_tree(tree) # Note: save_tree relies on global current_file_id which might be wrong!
        # Fix save_tree to take path or ID too?
        # Let's fix save_tree uses.
        path = get_file_path(request.conversation_id)
        tree.save_to_file(path)
        
        return {"response": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/checkout")
def checkout(request: CheckoutRequest):
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
    tree = load_tree(request.conversation_id)
    try:
        branch_name = tree.fork(request.branch_name)
        path = get_file_path(request.conversation_id)
        tree.save_to_file(path)
        return {"branch_name": branch_name}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/merge")
def merge(request: MergeRequest):
    tree = load_tree(request.conversation_id)
    try:
        tree.merge(request.merge_prompt or "")
        path = get_file_path(request.conversation_id)
        tree.save_to_file(path)
        return {"message": "Merged successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server.app:app", host="0.0.0.0", port=8000, reload=True)
