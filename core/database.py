"""
SQLite database layer for Forky conversation storage.

Provides schema management, connection handling, and migration utilities
for transitioning from JSON file storage to SQLite.
"""

import sqlite3
import os
import json
from datetime import datetime
from typing import Optional, List, Dict, Tuple
from contextlib import contextmanager

# Database file location (same directory as JSON files were stored)
DATA_DIR = ".forky_conversations"
DB_FILE = os.path.join(DATA_DIR, "forky.db")


def get_db_path() -> str:
    """Returns the full path to the SQLite database file."""
    return DB_FILE


@contextmanager
def get_connection():
    """
    Context manager for database connections.
    
    Yields:
        sqlite3.Connection: Database connection with row factory set.
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """
    Initializes the database schema.
    
    Creates tables if they don't exist: conversations, nodes, edges.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Conversations table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                name TEXT,
                current_node_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Nodes table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS nodes (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                content TEXT,
                role TEXT NOT NULL,
                branch_name TEXT,
                timestamp TIMESTAMP,
                node_type TEXT DEFAULT 'message',
                merge_metadata TEXT,
                state_summary_cache TEXT,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            )
        """)
        
        # Migration: add new columns if they don't exist
        try:
            cursor.execute("ALTER TABLE nodes ADD COLUMN node_type TEXT DEFAULT 'message'")
        except Exception:
            pass  # Column already exists
        try:
            cursor.execute("ALTER TABLE nodes ADD COLUMN merge_metadata TEXT")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE nodes ADD COLUMN state_summary_cache TEXT")
        except Exception:
            pass
        
        # Edges table (parent-child relationships for DAG)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS edges (
                parent_id TEXT NOT NULL,
                child_id TEXT NOT NULL,
                PRIMARY KEY (parent_id, child_id),
                FOREIGN KEY (parent_id) REFERENCES nodes(id) ON DELETE CASCADE,
                FOREIGN KEY (child_id) REFERENCES nodes(id) ON DELETE CASCADE
            )
        """)
        
        # Create indexes for common queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_nodes_conversation 
            ON nodes(conversation_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_edges_parent 
            ON edges(parent_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_edges_child 
            ON edges(child_id)
        """)
        
        # FTS5 virtual table for full-text search (standalone, no external content binding)
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
                node_id UNINDEXED,
                conversation_id UNINDEXED,
                content,
                role UNINDEXED
            )
        """)
        
        # Triggers to keep FTS index in sync with nodes table
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS nodes_fts_ai AFTER INSERT ON nodes BEGIN
                INSERT INTO nodes_fts(node_id, conversation_id, content, role)
                VALUES (NEW.id, NEW.conversation_id, NEW.content, NEW.role);
            END
        """)
        
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS nodes_fts_ad AFTER DELETE ON nodes BEGIN
                DELETE FROM nodes_fts WHERE node_id = OLD.id;
            END
        """)
        
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS nodes_fts_au AFTER UPDATE ON nodes BEGIN
                UPDATE nodes_fts SET content = NEW.content, role = NEW.role
                WHERE node_id = OLD.id;
            END
        """)
        
        # Populate FTS from existing data if empty
        cursor.execute("SELECT COUNT(*) FROM nodes_fts")
        fts_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM nodes")
        nodes_count = cursor.fetchone()[0]
        
        if fts_count == 0 and nodes_count > 0:
            print("Populating FTS index from existing nodes...")
            cursor.execute("""
                INSERT INTO nodes_fts(node_id, conversation_id, content, role)
                SELECT id, conversation_id, content, role FROM nodes
            """)
        
        # Attachments table for file uploads
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS attachments (
                id TEXT PRIMARY KEY,
                node_id TEXT,
                conversation_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                original_name TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                size_bytes INTEGER,
                attachment_type TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (node_id) REFERENCES nodes(id) ON DELETE CASCADE,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_attachments_node 
            ON attachments(node_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_attachments_conversation 
            ON attachments(conversation_id)
        """)
        
    print("Database initialized successfully.")


def migrate_json_to_sqlite() -> int:
    """
    Migrates existing JSON conversation files to SQLite database.
    
    Returns:
        int: Number of conversations migrated.
    """
    migrated_count = 0
    
    if not os.path.exists(DATA_DIR):
        return 0
    
    json_files = [f for f in os.listdir(DATA_DIR) if f.endswith(".json")]
    
    if not json_files:
        return 0
    
    print(f"Found {len(json_files)} JSON files to migrate...")
    
    for filename in json_files:
        filepath = os.path.join(DATA_DIR, filename)
        conversation_id = filename.replace(".json", "")
        
        try:
            # Check if already migrated
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id FROM conversations WHERE id = ?", 
                    (conversation_id,)
                )
                if cursor.fetchone():
                    print(f"  Skipping {conversation_id} (already exists)")
                    continue
            
            # Load JSON data
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            if "nodes" not in data:
                print(f"  Skipping {conversation_id} (legacy format)")
                continue
            
            # Migrate to SQLite
            _migrate_single_conversation(
                conversation_id=conversation_id,
                data=data
            )
            migrated_count += 1
            print(f"  Migrated: {conversation_id}")
            
        except Exception as e:
            print(f"  Error migrating {conversation_id}: {e}")
            continue
    
    print(f"Migration complete. {migrated_count} conversations migrated.")
    return migrated_count


def _migrate_single_conversation(conversation_id: str, data: Dict) -> None:
    """
    Migrates a single conversation from JSON data to SQLite.
    
    Args:
        conversation_id: The conversation identifier.
        data: Parsed JSON data containing nodes and metadata.
    """
    nodes_map = data.get("nodes", {})
    root_id = data.get("root_id")
    current_node_id = data.get("current_node_id", root_id)
    
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Insert conversation
        cursor.execute("""
            INSERT INTO conversations (id, name, current_node_id, updated_at)
            VALUES (?, ?, ?, ?)
        """, (conversation_id, conversation_id, current_node_id, datetime.now()))
        
        # Insert all nodes
        for node_id, node_data in nodes_map.items():
            timestamp = node_data.get("timestamp", datetime.now().isoformat())
            cursor.execute("""
                INSERT INTO nodes (id, conversation_id, content, role, branch_name, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                node_id,
                conversation_id,
                node_data.get("content", ""),
                node_data.get("role", "user"),
                node_data.get("branch_name"),
                timestamp
            ))
        
        # Insert edges (parent-child relationships)
        for node_id, node_data in nodes_map.items():
            for child_id in node_data.get("children_ids", []):
                cursor.execute("""
                    INSERT OR IGNORE INTO edges (parent_id, child_id)
                    VALUES (?, ?)
                """, (node_id, child_id))


# --- CRUD Operations for Conversations ---

def list_conversations() -> List[Dict]:
    """
    Lists all conversations in the database.
    
    Returns:
        List of conversation dictionaries with id, name, updated_at.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, updated_at 
            FROM conversations 
            ORDER BY updated_at DESC
        """)
        return [dict(row) for row in cursor.fetchall()]


def create_conversation(conversation_id: str, name: Optional[str] = None) -> None:
    """
    Creates a new conversation in the database.
    
    Args:
        conversation_id: Unique identifier for the conversation.
        name: Optional display name (defaults to conversation_id).
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO conversations (id, name, created_at, updated_at)
            VALUES (?, ?, ?, ?)
        """, (conversation_id, name or conversation_id, datetime.now(), datetime.now()))


def delete_conversation(conversation_id: str) -> bool:
    """
    Deletes a conversation and all its nodes/edges (CASCADE).
    
    Args:
        conversation_id: The conversation to delete.
        
    Returns:
        True if deleted, False if not found.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        return cursor.rowcount > 0


def conversation_exists(conversation_id: str) -> bool:
    """
    Checks if a conversation exists in the database.
    
    Args:
        conversation_id: The conversation ID to check.
        
    Returns:
        True if exists, False otherwise.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM conversations WHERE id = ?", (conversation_id,))
        return cursor.fetchone() is not None


def update_conversation_timestamp(conversation_id: str) -> None:
    """Updates the updated_at timestamp for a conversation."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE conversations SET updated_at = ? WHERE id = ?
        """, (datetime.now(), conversation_id))


def rename_conversation(conversation_id: str, new_name: str) -> bool:
    """
    Renames a conversation.
    
    Args:
        conversation_id: The conversation to rename.
        new_name: The new display name.
        
    Returns:
        True if renamed, False if not found.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE conversations SET name = ?, updated_at = ? WHERE id = ?
        """, (new_name, datetime.now(), conversation_id))
        return cursor.rowcount > 0


def get_conversation_current_node(conversation_id: str) -> Optional[str]:
    """Gets the current node ID for a conversation."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT current_node_id FROM conversations WHERE id = ?",
            (conversation_id,)
        )
        row = cursor.fetchone()
        return row["current_node_id"] if row else None


def set_conversation_current_node(conversation_id: str, node_id: str) -> None:
    """Sets the current node ID for a conversation."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE conversations 
            SET current_node_id = ?, updated_at = ?
            WHERE id = ?
        """, (node_id, datetime.now(), conversation_id))


# --- Node Operations ---

def save_node(conversation_id: str, node_id: str, content: str, role: str,
              branch_name: Optional[str] = None, timestamp: Optional[str] = None,
              node_type: str = "message", merge_metadata: Optional[str] = None,
              state_summary_cache: Optional[str] = None) -> None:
    """
    Saves or updates a node in the database.
    
    Args:
        conversation_id: The parent conversation.
        node_id: Unique node identifier.
        content: Message content.
        role: user, assistant, or system.
        branch_name: Optional branch name for fork nodes.
        timestamp: ISO format timestamp.
        node_type: 'message' or 'merge'.
        merge_metadata: JSON string of merge metadata.
        state_summary_cache: JSON string of cached state summary.
    """
    ts = timestamp or datetime.now().isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO nodes 
            (id, conversation_id, content, role, branch_name, timestamp, node_type, merge_metadata, state_summary_cache)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (node_id, conversation_id, content, role, branch_name, ts, node_type, merge_metadata, state_summary_cache))


def get_all_nodes(conversation_id: str) -> Dict[str, Dict]:
    """
    Gets all nodes for a conversation.
    
    Returns:
        Dict mapping node_id to node data.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Get nodes
        cursor.execute("""
            SELECT id, content, role, branch_name, timestamp, node_type, merge_metadata, state_summary_cache
            FROM nodes 
            WHERE conversation_id = ?
        """, (conversation_id,))
        
        nodes = {}
        for row in cursor.fetchall():
            nodes[row["id"]] = {
                "id": row["id"],
                "content": row["content"],
                "role": row["role"],
                "branch_name": row["branch_name"],
                "timestamp": row["timestamp"],
                "node_type": row["node_type"] or "message",
                "merge_metadata": row["merge_metadata"],
                "state_summary_cache": row["state_summary_cache"],
                "children_ids": [],
                "parent_ids": []
            }
        
        # Get edges
        node_ids = list(nodes.keys())
        if node_ids:
            placeholders = ",".join("?" * len(node_ids))
            cursor.execute(f"""
                SELECT parent_id, child_id FROM edges 
                WHERE parent_id IN ({placeholders}) OR child_id IN ({placeholders})
            """, node_ids + node_ids)
            
            for row in cursor.fetchall():
                parent_id, child_id = row["parent_id"], row["child_id"]
                if parent_id in nodes:
                    nodes[parent_id]["children_ids"].append(child_id)
                if child_id in nodes:
                    nodes[child_id]["parent_ids"].append(parent_id)
        
        return nodes


def add_edge(parent_id: str, child_id: str) -> None:
    """Adds a parent-child edge between nodes."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO edges (parent_id, child_id) VALUES (?, ?)
        """, (parent_id, child_id))


def find_root_node_id(conversation_id: str) -> Optional[str]:
    """Finds the root node (node with no parents) for a conversation."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT n.id FROM nodes n
            LEFT JOIN edges e ON n.id = e.child_id
            WHERE n.conversation_id = ? AND e.parent_id IS NULL
        """, (conversation_id,))
        row = cursor.fetchone()
        return row["id"] if row else None


def get_node_parents(node_id: str) -> List[str]:
    """Gets the parent IDs for a node."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT parent_id FROM edges WHERE child_id = ?", (node_id,))
        return [row["parent_id"] for row in cursor.fetchall()]


def get_node_children(node_id: str) -> List[str]:
    """Gets the child IDs for a node."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT child_id FROM edges WHERE parent_id = ?", (node_id,))
        return [row["child_id"] for row in cursor.fetchall()]


def delete_node(node_id: str) -> Tuple[bool, Optional[str]]:
    """
    Deletes a node (or turn pair) and reconnects ancestors to descendants.
    
    If the node is an assistant with a single user parent (a turn pair),
    both are deleted together. Parents inherit children.
    
    Only works for nodes with exactly one parent (not merge results).
    
    Args:
        node_id: The node to delete (typically the assistant node ID from UI).
        
    Returns:
        Tuple of (success, new_parent_id).
    """
    parents = get_node_parents(node_id)
    
    # Cannot delete nodes with multiple parents (merge results)
    if len(parents) != 1:
        return False, None
    
    parent_id = parents[0]
    children = get_node_children(node_id)
    
    # Check if this is an assistant node with a user parent (turn pair)
    # If so, we should delete both
    nodes_to_delete = [node_id]
    actual_parent_id = parent_id
    
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Check if parent is a user node with single parent
        cursor.execute("SELECT role FROM nodes WHERE id = ?", (parent_id,))
        parent_row = cursor.fetchone()
        
        cursor.execute("SELECT role FROM nodes WHERE id = ?", (node_id,))
        node_row = cursor.fetchone()
        
        if parent_row and node_row:
            parent_role = parent_row["role"]
            node_role = node_row["role"]
            
            # If this is assistant and parent is user -> delete both (turn pair)
            if node_role == "assistant" and parent_role == "user":
                user_parents = get_node_parents(parent_id)
                if len(user_parents) == 1:
                    nodes_to_delete.append(parent_id)
                    actual_parent_id = user_parents[0]
                    # Update children to include any children of the user node that aren't this assistant
                    user_children = get_node_children(parent_id)
                    for uc in user_children:
                        if uc != node_id and uc not in children:
                            children.append(uc)
        
        # Connect actual parent to all children of deleted nodes
        for child_id in children:
            cursor.execute("""
                INSERT OR REPLACE INTO edges (parent_id, child_id) VALUES (?, ?)
            """, (actual_parent_id, child_id))
        
        # Remove all edges involving deleted nodes
        for del_id in nodes_to_delete:
            cursor.execute("DELETE FROM edges WHERE parent_id = ? OR child_id = ?", (del_id, del_id))
        
        # Get all attachments for nodes being deleted (before deleting nodes)
        attachments_to_delete = []
        for del_id in nodes_to_delete:
            cursor.execute("SELECT filename FROM attachments WHERE node_id = ?", (del_id,))
            for row in cursor.fetchall():
                attachments_to_delete.append(row["filename"])
        
        # Delete attachments from database (CASCADE should handle this, but be explicit)
        for del_id in nodes_to_delete:
            cursor.execute("DELETE FROM attachments WHERE node_id = ?", (del_id,))
        
        # Delete the nodes
        for del_id in nodes_to_delete:
            cursor.execute("DELETE FROM nodes WHERE id = ?", (del_id,))
        
        # Delete attachment files from disk (after commit in finally block)
        # We do this outside the transaction to avoid issues
        import os
        UPLOAD_DIR = ".forky_conversations/uploads"
        for filename in attachments_to_delete:
            filepath = os.path.join(UPLOAD_DIR, filename)
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
            except Exception as e:
                print(f"Warning: Failed to delete attachment file {filepath}: {e}")
        
        return True, actual_parent_id


def search_nodes(query: str, limit: int = 50) -> List[Dict]:
    """
    Performs full-text search across all conversation nodes.
    
    Args:
        query: The search query string.
        limit: Maximum number of results to return.
        
    Returns:
        List of matching nodes with conversation context and snippets.
    """
    if not query or not query.strip():
        return []
    
    # Escape special FTS5 characters and add prefix matching
    escaped_query = query.replace('"', '""')
    search_term = f'"{escaped_query}"*'
    
    with get_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                fts.node_id,
                fts.conversation_id,
                c.name as conversation_name,
                fts.role,
                snippet(nodes_fts, 2, '<mark>', '</mark>', '...', 32) as snippet,
                n.timestamp
            FROM nodes_fts fts
            JOIN conversations c ON fts.conversation_id = c.id
            JOIN nodes n ON fts.node_id = n.id
            WHERE nodes_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (search_term, limit))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                "node_id": row["node_id"],
                "conversation_id": row["conversation_id"],
                "conversation_name": row["conversation_name"],
                "role": row["role"],
                "snippet": row["snippet"],
                "timestamp": row["timestamp"]
            })
        
        return results


# --- Attachment Operations ---

def save_attachment(
    attachment_id: str,
    conversation_id: str,
    filename: str,
    original_name: str,
    mime_type: str,
    attachment_type: str,
    size_bytes: int,
    node_id: Optional[str] = None
) -> None:
    """
    Saves attachment metadata to the database.
    
    Args:
        attachment_id: Unique identifier for the attachment.
        conversation_id: The parent conversation.
        filename: Saved filename (e.g., uuid.ext).
        original_name: Original filename from upload.
        mime_type: MIME type of the file.
        attachment_type: 'image' or 'document'.
        size_bytes: File size in bytes.
        node_id: Optional node ID (linked after message is sent).
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO attachments 
            (id, conversation_id, node_id, filename, original_name, mime_type, attachment_type, size_bytes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (attachment_id, conversation_id, node_id, filename, original_name, 
              mime_type, attachment_type, size_bytes))


def get_attachment(attachment_id: str) -> Optional[Dict]:
    """
    Gets a single attachment by ID.
    
    Args:
        attachment_id: The attachment ID.
        
    Returns:
        Attachment dict or None if not found.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, conversation_id, node_id, filename, original_name, 
                   mime_type, attachment_type, size_bytes, created_at
            FROM attachments WHERE id = ?
        """, (attachment_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None


def get_attachments_by_ids(attachment_ids: List[str]) -> List[Dict]:
    """
    Gets multiple attachments by their IDs.
    
    Args:
        attachment_ids: List of attachment IDs.
        
    Returns:
        List of attachment dicts.
    """
    if not attachment_ids:
        return []
    
    with get_connection() as conn:
        cursor = conn.cursor()
        placeholders = ",".join("?" * len(attachment_ids))
        cursor.execute(f"""
            SELECT id, conversation_id, node_id, filename, original_name, 
                   mime_type, attachment_type, size_bytes, created_at
            FROM attachments WHERE id IN ({placeholders})
        """, attachment_ids)
        return [dict(row) for row in cursor.fetchall()]


def get_node_attachments(node_id: str) -> List[Dict]:
    """
    Gets all attachments for a specific node.
    
    Args:
        node_id: The node ID.
        
    Returns:
        List of attachment dicts.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, conversation_id, node_id, filename, original_name, 
                   mime_type, attachment_type, size_bytes, created_at
            FROM attachments WHERE node_id = ?
        """, (node_id,))
        return [dict(row) for row in cursor.fetchall()]


def link_attachments_to_node(attachment_ids: List[str], node_id: str) -> int:
    """
    Links pending attachments to a node after message creation.
    
    Args:
        attachment_ids: List of attachment IDs to link.
        node_id: The node ID to link them to.
        
    Returns:
        Number of attachments linked.
    """
    if not attachment_ids:
        return 0
    
    with get_connection() as conn:
        cursor = conn.cursor()
        placeholders = ",".join("?" * len(attachment_ids))
        cursor.execute(f"""
            UPDATE attachments SET node_id = ?
            WHERE id IN ({placeholders}) AND node_id IS NULL
        """, [node_id] + attachment_ids)
        return cursor.rowcount


def delete_attachment(attachment_id: str) -> bool:
    """
    Deletes an attachment from the database.
    
    Args:
        attachment_id: The attachment ID to delete.
        
    Returns:
        True if deleted, False if not found.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM attachments WHERE id = ?", (attachment_id,))
        return cursor.rowcount > 0


def get_orphan_attachments(max_age_hours: int = 24) -> List[Dict]:
    """
    Gets attachments that are not linked to any node and older than max_age_hours.
    These can be safely deleted as cleanup.
    
    Args:
        max_age_hours: Maximum age in hours for orphan attachments.
        
    Returns:
        List of orphan attachment dicts.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, conversation_id, filename, original_name, mime_type, 
                   attachment_type, size_bytes, created_at
            FROM attachments 
            WHERE node_id IS NULL 
            AND created_at < datetime('now', ? || ' hours')
        """, (f"-{max_age_hours}",))
        return [dict(row) for row in cursor.fetchall()]


def get_nodes_attachments(node_ids: List[str]) -> List[Dict]:
    """
    Gets all attachments for a list of node IDs.
    
    Useful for collecting all attachments from a branch for merge.
    
    Args:
        node_ids: List of node IDs to get attachments for.
        
    Returns:
        List of attachment dicts with node_id included.
    """
    if not node_ids:
        return []
    
    with get_connection() as conn:
        cursor = conn.cursor()
        placeholders = ",".join("?" * len(node_ids))
        cursor.execute(f"""
            SELECT id, conversation_id, node_id, filename, original_name, 
                   mime_type, attachment_type, size_bytes, created_at
            FROM attachments WHERE node_id IN ({placeholders})
            ORDER BY created_at
        """, node_ids)
        return [dict(row) for row in cursor.fetchall()]


def cleanup_orphan_attachments(max_age_hours: int = 24) -> int:
    """
    Cleans up orphan attachments older than max_age_hours.
    
    Removes both database records and files from disk.
    Should be called periodically or at server startup.
    
    Args:
        max_age_hours: Maximum age in hours for orphan attachments.
        
    Returns:
        Number of attachments cleaned up.
    """
    orphans = get_orphan_attachments(max_age_hours)
    
    if not orphans:
        return 0
    
    UPLOAD_DIR = ".forky_conversations/uploads"
    cleaned = 0
    
    for att in orphans:
        # Delete file from disk
        filepath = os.path.join(UPLOAD_DIR, att["filename"])
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception as e:
            print(f"Warning: Failed to delete orphan file {filepath}: {e}")
        
        # Delete from database
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM attachments WHERE id = ?", (att["id"],))
        
        cleaned += 1
    
    if cleaned > 0:
        print(f"Cleaned up {cleaned} orphan attachment(s)")
    
    return cleaned
