import { useState, useEffect, useCallback, useRef } from 'react'
import axios from 'axios'
import './App.css'
import FlowGraph from './components/FlowGraph'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'


const API_URL = 'http://localhost:8000'

function App() {
  const [conversations, setConversations] = useState([])
  const [currentConversationId, setCurrentConversationId] = useState(null)
  // node data for graph
  const [graphData, setGraphData] = useState([])
  const [currentNodeId, setCurrentNodeId] = useState(null)

  const [history, setHistory] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [selectedModel, setSelectedModel] = useState('claude-4.5-sonnet')
  const [sidebarWidth, setSidebarWidth] = useState(450)
  const [isResizing, setIsResizing] = useState(false)

  // Selection state
  const [selectedNodeIds, setSelectedNodeIds] = useState([])
  const [mergeEligibility, setMergeEligibility] = useState(null) // {eligible, rejection_reason, lca_id}

  const historyEndRef = useRef(null)

  const scrollToBottom = () => {
    historyEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }

  useEffect(() => {
    scrollToBottom()
  }, [history])

  // Resizing logic
  const startResizing = useCallback((e) => {
    setIsResizing(true)
    e.preventDefault()
  }, [])

  const stopResizing = useCallback(() => {
    setIsResizing(false)
  }, [])

  const resize = useCallback((e) => {
    if (isResizing) {
      const newWidth = Math.max(300, Math.min(800, e.clientX - 250)) // 250 is nav sidebar width
      setSidebarWidth(newWidth)
    }
  }, [isResizing])

  useEffect(() => {
    if (isResizing) {
      window.addEventListener('mousemove', resize)
      window.addEventListener('mouseup', stopResizing)
    } else {
      window.removeEventListener('mousemove', resize)
      window.removeEventListener('mouseup', stopResizing)
    }
    return () => {
      window.removeEventListener('mousemove', resize)
      window.removeEventListener('mouseup', stopResizing)
    }
  }, [isResizing, resize, stopResizing])

  useEffect(() => {
    if (isResizing) {
      document.body.style.cursor = 'col-resize'
      document.body.style.userSelect = 'none'
    } else {
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
  }, [isResizing])

  // Conversations logic
  const fetchConversations = useCallback(async () => {
    try {
      const res = await axios.get(`${API_URL}/conversations`)
      setConversations(res.data.conversations)
      const active = res.data.conversations.find(c => c.is_active)
      if (active) setCurrentConversationId(active.id)
      return res.data.conversations
    } catch (err) {
      console.error("Failed to fetch conversations", err)
      return []
    }
  }, [])

  const handleCreateConversation = async () => {
    try {
      const res = await axios.post(`${API_URL}/conversations`, {})
      await fetchConversations()
      // Load the new conversation
      await handleSelectConversation(res.data.id)
    } catch (_err) {
      alert('Failed to create conversation')
    }
  }

  const handleSelectConversation = async (id) => {
    try {
      await axios.post(`${API_URL}/conversations/${id}/load`)
      setCurrentConversationId(id)
      refresh() // Refresh tree and history
      fetchConversations() // Update active state in list
    } catch (err) {
      console.error("Failed to load conversation", err)
    }
  }

  const handleDeleteConversation = async (e, id) => {
    e.stopPropagation()
    if (!window.confirm("Are you sure you want to delete this conversation?")) return

    try {
      await axios.delete(`${API_URL}/conversations/${id}`)

      const updatedList = await fetchConversations()

      if (currentConversationId === id) {
        // We deleted the active conversation. Switch to another if possible.
        if (updatedList.length > 0) {
          const next = updatedList[0]
          await handleSelectConversation(next.id)
        } else {
          setGraphData([])
          setHistory([])
          setCurrentConversationId(null)
        }
      }
    } catch (err) {
      console.error("Delete failed", err)
      alert('Failed to delete conversation')
    }
  }

  const handleRenameConversation = async (e, id, currentName) => {
    e.stopPropagation()
    const newName = window.prompt("Enter new name:", currentName)
    if (!newName || newName.trim() === '' || newName === currentName) return

    try {
      await axios.patch(`${API_URL}/conversations/${id}`, { name: newName.trim() })
      await fetchConversations()
    } catch (err) {
      console.error("Rename failed", err)
      alert('Failed to rename conversation')
    }
  }

  const fetchGraph = useCallback(async () => {
    if (!currentConversationId) return;
    try {
      const res = await axios.get(`${API_URL}/graph?conversation_id=${currentConversationId}`)
      // Expecting { nodes: [...], current_node_id: ... }
      setGraphData(res.data.nodes || [])
      setCurrentNodeId(res.data.current_node_id)
    } catch (err) {
      console.error("Failed to fetch graph", err)
    }
  }, [currentConversationId])

  const fetchHistory = useCallback(async () => {
    try {
      const url = currentConversationId ? `${API_URL}/history?conversation_id=${currentConversationId}` : `${API_URL}/history`
      const res = await axios.get(url)
      setHistory(res.data.history)
    } catch (err) {
      console.error("Failed to fetch history", err)
      setHistory([])
    }
  }, [currentConversationId])

  const refresh = useCallback(() => {
    fetchGraph()
    fetchHistory()
  }, [fetchGraph, fetchHistory])

  // Initial load
  useEffect(() => {
    fetchConversations()
    refresh()
  }, [fetchConversations, refresh])

  // Check merge eligibility when 2 nodes are selected
  useEffect(() => {
    const checkEligibility = async () => {
      if (selectedNodeIds.length === 2 && currentConversationId) {
        try {
          const res = await axios.post(`${API_URL}/check_merge_eligibility`, {
            node_a_id: selectedNodeIds[0],
            node_b_id: selectedNodeIds[1],
            conversation_id: currentConversationId
          })
          setMergeEligibility(res.data)
        } catch (err) {
          console.error("Failed to check merge eligibility", err)
          setMergeEligibility({ eligible: false, rejection_reason: "check_failed" })
        }
      } else {
        setMergeEligibility(null)
      }
    }
    checkEligibility()
  }, [selectedNodeIds, currentConversationId])

  const sendMessage = async (e) => {
    e.preventDefault()
    if (!input.trim()) return

    // CHECK SELECTION FOR MERGE
    if (selectedNodeIds.length === 2) {
      // Check eligibility first
      if (!mergeEligibility?.eligible) {
        const reason = mergeEligibility?.rejection_reason || "unknown"
        if (reason === "cannot_merge_ancestor_with_descendant") {
          alert("Cannot merge: one node is an ancestor of the other. Select two divergent branches.")
        } else if (reason === "cannot_merge_node_with_itself") {
          alert("Cannot merge a node with itself.")
        } else if (reason === "no_common_ancestor_found") {
          alert("Cannot merge: no common ancestor found between these nodes.")
        } else {
          alert(`Merge not allowed: ${reason}`)
        }
        return
      }

      // MERGE LOGIC
      // We need to determine which is 'current' and which is 'target'.

      // Check if one of them is the current active node
      const isCurrentInSelection = selectedNodeIds.includes(currentNodeId)

      let targetId = null

      if (isCurrentInSelection) {
        // Target is the other one
        targetId = selectedNodeIds.find(id => id !== currentNodeId)
      } else {
        // Neither is current.
        // Heuristic: We must checkout one of them first.
        const baseId = selectedNodeIds[0]
        targetId = selectedNodeIds[1]

        console.log(`Neither sel is current. Auto-checking out ${baseId} then merging ${targetId}`)

        try {
          await axios.post(`${API_URL}/checkout`, {
            identifier: baseId,
            conversation_id: currentConversationId
          })
        } catch (_err) {
          alert("Failed to auto-checkout base node for merge.")
          return;
        }
      }

      console.log(`Merging ${targetId} into current... (LCA: ${mergeEligibility?.lca_id})`)
      setLoading(true)
      try {
        const res = await axios.post(`${API_URL}/merge_branches`, {
          target_node_id: targetId,
          merge_prompt: input,
          conversation_id: currentConversationId
        })

        // Show conflicts if any
        if (res.data.has_conflicts) {
          const conflictCount = res.data.conflicts?.length || 0
          alert(`Merge completed with ${conflictCount} conflict(s). The AI has been informed and may ask for clarification.`)
        }

        setInput('')
        setSelectedNodeIds([]) // Clear selection
        setMergeEligibility(null)
        refresh()
      } catch (err) {
        alert("Merge failed: " + (err.response?.data?.detail || err.message))
      } finally {
        setLoading(false)
      }
      return
    }

    // NORMAL SEND LOGIC
    const userMsg = `user: ${input}`
    const assistantMsgPrefix = `assistant: `

    // Optimistic update
    setHistory(prev => [...prev, userMsg, assistantMsgPrefix])
    setInput('')
    setLoading(true)

    try {
      const response = await fetch(`${API_URL}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: input,
          conversation_id: currentConversationId,
          model: selectedModel
        })
      })

      if (!response.body) return

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let assistantResponse = ""

      while (true) {
        const { value, done } = await reader.read()
        if (done) break

        const chunk = decoder.decode(value, { stream: true })
        assistantResponse += chunk

        // Update the last message in history with the accumulated response
        setHistory(prev => {
          const newHistory = [...prev]
          newHistory[newHistory.length - 1] = assistantMsgPrefix + assistantResponse
          return newHistory
        })
      }

      // Cleanup / Finalize
      refresh()
    } catch (err) {
      console.error(err)
      alert('Error sending message')
    } finally {
      setLoading(false)
    }
  }

  const handleNodeClick = async (e, nodeId) => {
    // If modifier keys are pressed, we interpret this as a selection action, 
    // handled internally by ReactFlow. We DO NOT want to trigger a checkout/refresh
    // because that would reset the graph state and clear the selection.
    if (e.metaKey || e.ctrlKey || e.shiftKey) {
      console.log("Modifier pressed, skipping checkout")
      return
    }
    // But FlowGraph handles selection. 
    // We should only checkout if NOT selecting?
    // Actually, let's decouple checkout from click if we are in "selection mode" (e.g. holding ctrl/cmd done by library)
    // BUT: ReactFlow's onNodeClick event usually fires.

    // Simplify: Single click = Checkout.
    // Shift/Ctrl + Click = Selection (handled by ReactFlow internals, we get onSelectionChange).

    // However, user wants to "highlight two nodes".
    // If we click one, it checkouts.
    // If we want to multi-select, usage of defaults usually requires Shift-click.

    // Let's implement checkout on single click ONLY if selection count <= 1?
    // Or separate "checkout" action?

    // Default behavior: Click = Checkout.
    // Getting current selection from state.

    // We'll let the user explicitly checkout via click. Selection is visual.
    // If you select 2 nodes, clicking one might trigger checkout but selection remains.

    try {
      await axios.post(`${API_URL}/checkout`, {
        identifier: nodeId,
        conversation_id: currentConversationId
      })
      refresh()
    } catch (err) {
      console.error("Checkout failed", err)
    }
  }

  const handleDeleteNode = async (nodeId) => {
    if (!window.confirm("Delete this node? Children will be inherited by parent.")) return

    try {
      await axios.post(`${API_URL}/delete_node`, {
        node_id: nodeId,
        conversation_id: currentConversationId
      })
      setSelectedNodeIds([])
      refresh()
    } catch (err) {
      const msg = err.response?.data?.detail || err.message
      alert(`Cannot delete node: ${msg}`)
    }
  }

  return (
    <div className="container">
      {/* Navigation Sidebar */}
      <div className="nav-sidebar">
        <h2>Chats</h2>
        <ul className="nav-list">
          {conversations.map(conv => (
            <li
              key={conv.id}
              className={`nav-item ${conv.id === currentConversationId ? 'active' : ''}`}
              onClick={() => handleSelectConversation(conv.id)}
            >
              <span className="nav-item-name" title={conv.name}>{conv.name.length > 18 ? conv.name.substring(0, 18) + '...' : conv.name}</span>
              <span className="nav-item-actions">
                <span
                  onClick={(e) => handleRenameConversation(e, conv.id, conv.name)}
                  style={{ opacity: 0.5, fontSize: '0.8rem', marginRight: '6px', cursor: 'pointer' }}
                  title="Rename"
                >
                  ✏️
                </span>
                <span
                  onClick={(e) => handleDeleteConversation(e, conv.id)}
                  style={{ opacity: 0.5, fontSize: '0.8rem', cursor: 'pointer' }}
                  title="Delete"
                >
                  ✕
                </span>
              </span>
            </li>
          ))}
        </ul>
        <div className="nav-actions">
          <button onClick={handleCreateConversation}>+ New Chat</button>
        </div>
      </div>

      {/* Graph Sidebar */}
      <div className="sidebar" style={{ width: sidebarWidth }}>
        <div className="resizer" onMouseDown={startResizing} />
        <div className="tree-header" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid var(--border-color)', height: '40px', padding: '0 10px' }}>
          <h3 style={{ margin: 0 }}>
            Graph {selectedNodeIds.length > 0 && <span style={{ fontSize: '0.8em', color: '#3b82f6' }}>({selectedNodeIds.length} selected)</span>}
          </h3>
          {selectedNodeIds.length === 1 && (
            <button
              onClick={() => handleDeleteNode(selectedNodeIds[0])}
              style={{
                background: '#ef4444',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                padding: '4px 10px',
                fontSize: '0.8rem',
                cursor: 'pointer'
              }}
              title="Delete selected node"
            >
              🗑️ Delete Node
            </button>
          )}
        </div>

        <div className="tree-container" style={{ height: 'calc(100% - 40px)', background: '#fff' }}>
          {/* ReactFlow Component */}
          <FlowGraph
            data={graphData}
            currentId={currentNodeId}
            onNodeClick={handleNodeClick}
            onSelectionChange={setSelectedNodeIds}
          />
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="main">
        <h2>Chat History</h2>
        <div className="history">
          {history.length > 0 ? (
            history.map((msg, i) => {
              const isUser = msg.startsWith("User:") || msg.startsWith("user:")
              const content = msg.replace(/^(User:|System:|Assistant:|user:|system:|assistant:)\s*/, "")
              return (
                <div key={i} className={`message ${isUser ? 'user' : 'system'}`}>
                  {isUser ? (
                    content
                  ) : (
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {content}
                    </ReactMarkdown>
                  )}
                </div>
              )
            })
          ) : (
            <div style={{ padding: '20px', color: '#64748b', textAlign: 'center' }}>
              Select a conversation or start a new one.
            </div>
          )}
          <div ref={historyEndRef} />
        </div>
        <form onSubmit={sendMessage} className="input-area">
          <select
            value={selectedModel}
            onChange={(e) => setSelectedModel(e.target.value)}
            disabled={loading || !currentConversationId}
            style={{ marginRight: '10px', padding: '8px', borderRadius: '4px', border: '1px solid #ccc' }}
          >
            <option value="claude-4.5-sonnet">Claude Sonnet 4.5</option>
            <option value="claude-4.5-haiku">Claude Haiku 4.5</option>
            <option value="claude-4.5-opus">Claude Opus 4.5</option>
            <option value="gpt-5.2-2025-12-11">gpt-5.2-2025-12-11</option>
            <option value="gpt-5-mini-2025-08-07">gpt-5-mini-2025-08-07</option>
            <option value="gpt-5-nano-2025-08-07">gpt-5-nano-2025-08-07</option>
          </select>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={loading || !currentConversationId}
            placeholder={
              selectedNodeIds.length === 2
                ? (mergeEligibility?.eligible
                  ? "Enter merge prompt to merge selected nodes..."
                  : `⚠️ Merge not allowed: ${mergeEligibility?.rejection_reason || 'checking...'}`)
                : "Type a message..."
            }
            style={{
              borderColor: selectedNodeIds.length === 2 ? '#8b5cf6' : '#ccc',
              borderWidth: selectedNodeIds.length === 2 ? '2px' : '1px'
            }}
            autoFocus
          />
          <button
            type="submit"
            disabled={loading || !currentConversationId || (selectedNodeIds.length === 2 && !mergeEligibility?.eligible)}
            style={{
              backgroundColor: selectedNodeIds.length === 2
                ? (mergeEligibility?.eligible ? '#8b5cf6' : '#9ca3af')
                : '#2563eb'
            }}
          >
            {loading ? '...' : (selectedNodeIds.length === 2 ? 'Merge & Send' : 'Send')}
          </button>
        </form>
      </div>
    </div>
  )
}

export default App
