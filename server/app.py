from fastapi import FastAPI, HTTPException, Body, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional, Dict
import os
import uuid
from core.conversation_tree import ConversationTree
from core import database as db
from core import attachment_utils

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

# Upload directory for attachments
UPLOAD_DIR = ".forky_conversations/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Mount static files for serving uploads
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


@app.on_event("startup")
def startup_event():
    """Initialize database and run migrations on server startup."""
    db.init_db()
    migrated = db.migrate_json_to_sqlite()
    if migrated > 0:
        print(f"Migrated {migrated} conversations from JSON to SQLite")
    
    # Clean up orphan attachments (older than 1 hour)
    db.cleanup_orphan_attachments(max_age_hours=1)


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
    attachment_ids: Optional[List[str]] = None  # NEW: list of attachment IDs

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


# --- Attachment Endpoints ---

@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    conversation_id: str = Form(...)
):
    """
    Uploads a file attachment.
    
    Returns attachment metadata including ID and URL for preview.
    The attachment is not yet linked to any message node.
    """
    # Validate conversation exists
    if not db.conversation_exists(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Get file info
    original_name = file.filename or "unknown"
    content = await file.read()
    size_bytes = len(content)
    
    # Determine MIME type
    mime_type = file.content_type or attachment_utils.get_mime_type(original_name)
    
    # Validate file type
    if not attachment_utils.is_supported_file(mime_type, original_name):
        raise HTTPException(
            status_code=400, 
            detail=f"Unsupported file type: {mime_type}"
        )
    
    # Validate file size
    is_valid, error_msg = attachment_utils.validate_file_size(size_bytes, mime_type)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)
    
    # Generate unique filename
    attachment_id = uuid.uuid4().hex[:12]
    ext = os.path.splitext(original_name)[1].lower()
    saved_filename = f"{attachment_id}{ext}"
    filepath = os.path.join(UPLOAD_DIR, saved_filename)
    
    # Save file to disk
    with open(filepath, "wb") as f:
        f.write(content)
    
    # Determine attachment type
    attachment_type = attachment_utils.get_attachment_type(mime_type, original_name)
    
    # Save metadata to database
    db.save_attachment(
        attachment_id=attachment_id,
        conversation_id=conversation_id,
        filename=saved_filename,
        original_name=original_name,
        mime_type=mime_type,
        attachment_type=attachment_type,
        size_bytes=size_bytes
    )
    
    return {
        "attachment_id": attachment_id,
        "filename": saved_filename,
        "original_name": original_name,
        "mime_type": mime_type,
        "type": attachment_type,
        "size_bytes": size_bytes,
        "url": f"/uploads/{saved_filename}"
    }


@app.delete("/attachment/{attachment_id}")
def delete_attachment(attachment_id: str):
    """Deletes an unlinked attachment."""
    attachment = db.get_attachment(attachment_id)
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
    
    # Only allow deleting unlinked attachments
    if attachment.get("node_id"):
        raise HTTPException(status_code=400, detail="Cannot delete attached file")
    
    # Delete file from disk
    filepath = os.path.join(UPLOAD_DIR, attachment["filename"])
    if os.path.exists(filepath):
        os.remove(filepath)
    
    # Delete from database
    db.delete_attachment(attachment_id)
    
    return {"message": "Attachment deleted"}


@app.get("/node/{node_id}/attachments")
def get_node_attachments(node_id: str):
    """Gets all attachments for a specific message node."""
    attachments = db.get_node_attachments(node_id)
    # Add URL to each attachment
    for att in attachments:
        att["url"] = f"/uploads/{att['filename']}"
    return {"attachments": attachments}


# --- Conversation Endpoints ---

@app.get("/conversations")
def list_conversations():
    """Lists all available conversations, sorted by last update time."""
    conversations = db.list_conversations()
    return {"conversations": conversations}

@app.post("/conversations")
def create_conversation(request: CreateConversationRequest):
    """Creates a new empty conversation with an optional name."""
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


@app.get("/search")
def search(q: str = ""):
    """
    Performs full-text search across all conversation nodes.
    
    Returns matching nodes with conversation context and highlighted snippets.
    """
    if not q or not q.strip():
        return {"results": []}
    
    results = db.search_nodes(q.strip())
    return {"results": results}

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
    """
    Returns the linear conversation history with attachments.
    
    Each message includes: id, role, content, attachments[].
    """
    tree = load_tree(conversation_id)
    messages = tree.get_flat_conversation_with_ids()
    
    # Collect all node IDs to fetch attachments in one query
    node_ids = [msg["id"] for msg in messages]
    
    # Get all attachments for these nodes
    all_attachments = db.get_nodes_attachments(node_ids)
    
    # Group attachments by node_id
    attachments_by_node = {}
    for att in all_attachments:
        node_id = att["node_id"]
        if node_id not in attachments_by_node:
            attachments_by_node[node_id] = []
        attachments_by_node[node_id].append({
            "id": att["id"],
            "filename": att["filename"],
            "original_name": att["original_name"],
            "mime_type": att["mime_type"],
            "type": att["attachment_type"],
            "url": f"/uploads/{att['filename']}"
        })
    
    # Add attachments to messages
    for msg in messages:
        msg["attachments"] = attachments_by_node.get(msg["id"], [])
    
    return {"history": messages}

@app.post("/chat")
def chat(request: MessageRequest):
    """
    Sends a message to the LLM and gets a response.
    
    Updates the conversation tree with the new user message and assistant response.
    Supports attachments (images, documents) that are passed to the LLM.
    """
    tree = load_tree(request.conversation_id)
    
    # Prepare attachments for LLM if any
    prepared_attachments = None
    attachment_ids = request.attachment_ids or []
    
    if attachment_ids:
        attachments_data = db.get_attachments_by_ids(attachment_ids)
        prepared_attachments = []
        
        for att in attachments_data:
            filepath = os.path.join(UPLOAD_DIR, att["filename"])
            prepared = attachment_utils.prepare_attachment_for_llm(
                filepath=filepath,
                original_name=att["original_name"],
                mime_type=att["mime_type"]
            )
            if prepared:
                prepared_attachments.append(prepared)
    
    async def generate():
        try:
            for chunk in tree.chat_stream(
                request.message, 
                provider=request.provider, 
                model=request.model,
                attachments=prepared_attachments
            ):
                yield chunk
            
            # Save after completion
            tree.save_to_db(request.conversation_id)
            
            # Link attachments to the user node
            if attachment_ids and hasattr(tree, '_last_user_node_id'):
                db.link_attachments_to_node(attachment_ids, tree._last_user_node_id)
                
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
