import { useState, useEffect, useCallback, useRef } from 'react'
import axios from 'axios'
import './App.css'
import FlowGraph from './components/FlowGraph'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import DOMPurify from 'dompurify'


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
  const [selectedModel, setSelectedModel] = useState('')
  const [availableModels, setAvailableModels] = useState([])
  const [sidebarWidth, setSidebarWidth] = useState(450)
  const [isResizing, setIsResizing] = useState(false)

  // Selection state
  const [selectedNodeIds, setSelectedNodeIds] = useState([])
  const [mergeEligibility, setMergeEligibility] = useState(null) // {eligible, rejection_reason, lca_id}

  // Search state
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState([])
  const [isSearching, setIsSearching] = useState(false)

  // Attachment state
  const [pendingAttachments, setPendingAttachments] = useState([])
  const [uploadingFiles, setUploadingFiles] = useState(false)
  const fileInputRef = useRef(null)

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

  // Search functionality
  const handleSearch = async (query) => {
    setSearchQuery(query)
    if (!query.trim()) {
      setSearchResults([])
      return
    }
    setIsSearching(true)
    try {
      const res = await axios.get(`${API_URL}/search?q=${encodeURIComponent(query)}`)
      setSearchResults(res.data.results || [])
    } catch (err) {
      console.error("Search failed", err)
      setSearchResults([])
    } finally {
      setIsSearching(false)
    }
  }

  const handleSearchResultClick = async (result) => {
    // Load the conversation if different
    if (result.conversation_id !== currentConversationId) {
      await handleSelectConversation(result.conversation_id)
    }
    // Checkout to the node
    try {
      await axios.post(`${API_URL}/checkout`, {
        identifier: result.node_id,
        conversation_id: result.conversation_id
      })
      refresh()
    } catch (err) {
      console.error("Checkout failed", err)
    }
    // Clear search
    setSearchQuery('')
    setSearchResults([])
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

  // Fetch available models
  const fetchAvailableModels = useCallback(async () => {
    try {
      const res = await axios.get(`${API_URL}/available_models`)
      const models = res.data.models || []
      setAvailableModels(models)
      if (models.length > 0 && !selectedModel) {
        setSelectedModel(models[0].id)
      }
    } catch (err) {
      console.error("Failed to fetch available models", err)
    }
  }, [selectedModel])

  // Initial load
  useEffect(() => {
    fetchConversations()
    fetchAvailableModels()
    refresh()
  }, [fetchConversations, fetchAvailableModels, refresh])

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

  // File upload handler
  const handleFileSelect = async (e) => {
    const files = Array.from(e.target.files)
    if (!files.length || !currentConversationId) return

    setUploadingFiles(true)

    for (const file of files) {
      try {
        const formData = new FormData()
        formData.append('file', file)
        formData.append('conversation_id', currentConversationId)

        const res = await axios.post(`${API_URL}/upload`, formData)

        setPendingAttachments(prev => [...prev, res.data])
      } catch (err) {
        console.error('Failed to upload file:', err)
        const errorMsg = err.response?.data?.detail || err.message
        alert(`Failed to upload ${file.name}: ${errorMsg}`)
      }
    }

    setUploadingFiles(false)
    // Reset file input
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  // Remove pending attachment
  const removeAttachment = async (attachmentId) => {
    try {
      await axios.delete(`${API_URL}/attachment/${attachmentId}`)
      setPendingAttachments(prev => prev.filter(a => a.attachment_id !== attachmentId))
    } catch (err) {
      console.error('Failed to remove attachment:', err)
      // Still remove from UI even if server delete fails
      setPendingAttachments(prev => prev.filter(a => a.attachment_id !== attachmentId))
    }
  }

  const sendMessage = async (e) => {
    e.preventDefault()
    if (!input.trim()) return
    if (uploadingFiles) {
      alert('Please wait for file uploads to complete before sending.')
      return
    }

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
    const currentInput = input
    const currentAttachments = pendingAttachments.map(a => a.attachment_id)
    setInput('')
    setPendingAttachments([]) // Clear attachments
    setLoading(true)

    try {
      const response = await fetch(`${API_URL}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: currentInput,
          conversation_id: currentConversationId,
          model: selectedModel,
          attachment_ids: currentAttachments.length > 0 ? currentAttachments : undefined
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

        {/* Search Input */}
        <div className="search-container">
          <input
            type="text"
            className="search-input"
            placeholder="🔍 Search all chats..."
            value={searchQuery}
            onChange={(e) => handleSearch(e.target.value)}
          />
          {searchQuery && (
            <span
              className="search-clear"
              onClick={() => { setSearchQuery(''); setSearchResults([]); }}
            >
              ✕
            </span>
          )}
        </div>

        {/* Search Results */}
        {searchQuery && (
          <div className="search-results">
            {isSearching ? (
              <div className="search-loading">Searching...</div>
            ) : searchResults.length > 0 ? (
              searchResults.map((result, idx) => (
                <div
                  key={`${result.node_id}-${idx}`}
                  className="search-result-item"
                  onClick={() => handleSearchResultClick(result)}
                >
                  <div className="search-result-meta">
                    <span className="search-result-conv">{result.conversation_name}</span>
                    <span className={`search-result-role ${result.role}`}>{result.role}</span>
                  </div>
                  <div
                    className="search-result-snippet"
                    dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(result.snippet) }}
                  />
                </div>
              ))
            ) : (
              <div className="search-no-results">No results found</div>
            )}
          </div>
        )}

        <ul className="nav-list">
          {conversations.map(conv => (
            <li
              key={conv.id}
              className={`nav-item ${conv.id === currentConversationId ? 'active' : ''}`}
              onClick={() => handleSelectConversation(conv.id)}
            >
              <span className="nav-item-name" title={conv.name}>{conv.name.length > 18 ? conv.name.substring(0, 18) + '...' : conv.name}</span>
              <span className="nav-item-actions">
                <button
                  type="button"
                  onClick={(e) => handleRenameConversation(e, conv.id, conv.name)}
                  style={{ opacity: 0.5, fontSize: '0.8rem', marginRight: '6px' }}
                  title="Rename"
                  aria-label={`Rename conversation: ${conv.name}`}
                >
                  ✏️
                </button>
                <button
                  type="button"
                  onClick={(e) => handleDeleteConversation(e, conv.id)}
                  style={{ opacity: 0.5, fontSize: '0.8rem' }}
                  title="Delete"
                  aria-label={`Delete conversation: ${conv.name}`}
                >
                  ✕
                </button>
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
              // Handle both old string format and new object format
              const isOldFormat = typeof msg === 'string'
              const isUser = isOldFormat
                ? (msg.startsWith("User:") || msg.startsWith("user:"))
                : msg.role === "user"
              const content = isOldFormat
                ? msg.replace(/^(User:|System:|Assistant:|user:|system:|assistant:)\s*/, "")
                : msg.content
              const attachments = isOldFormat ? [] : (msg.attachments || [])

              return (
                <div key={isOldFormat ? i : msg.id} className={`message ${isUser ? 'user' : 'system'}`}>
                  {/* Attachments for user messages */}
                  {isUser && attachments.length > 0 && (
                    <div className="message-attachments">
                      {attachments.map(att => (
                        <div key={att.id} className="message-attachment">
                          {att.type === 'image' ? (
                            <img
                              src={`${API_URL}${att.url}`}
                              alt={att.original_name}
                              onClick={() => window.open(`${API_URL}${att.url}`, '_blank')}
                            />
                          ) : (
                            <a
                              href={`${API_URL}${att.url}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="document-attachment"
                            >
                              <span className="doc-icon">📄</span>
                              <span className="doc-name">{att.original_name}</span>
                            </a>
                          )}
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Message content */}
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

        {/* Attachments Preview */}
        {pendingAttachments.length > 0 && (
          <div className="attachments-preview">
            {pendingAttachments.map(att => (
              <div key={att.attachment_id} className="attachment-chip">
                {att.type === 'image' ? (
                  <img src={`${API_URL}${att.url}`} alt={att.original_name} />
                ) : (
                  <span className="attachment-icon">📄</span>
                )}
                <span className="attachment-name" title={att.original_name}>
                  {att.original_name.length > 12 ? att.original_name.substring(0, 12) + '...' : att.original_name}
                </span>
                <button
                  type="button"
                  onClick={() => removeAttachment(att.attachment_id)}
                  className="attachment-remove"
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        )}

        <form onSubmit={sendMessage} className="input-area">
          {/* Hidden file input */}
          <input
            type="file"
            ref={fileInputRef}
            style={{ display: 'none' }}
            multiple
            accept="image/*,.pdf,.txt,.md,.json,.csv,.py,.js,.ts,.jsx,.tsx,.html,.css,.sql,.java,.cpp,.c,.go,.rs,.rb,.php"
            onChange={handleFileSelect}
          />

          {/* Attach button */}
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={loading || !currentConversationId || uploadingFiles}
            className="attach-button"
            title="Attach files"
          >
            {uploadingFiles ? '⏳' : '📎'}
          </button>

          <select
            value={selectedModel}
            onChange={(e) => setSelectedModel(e.target.value)}
            disabled={loading || !currentConversationId || availableModels.length === 0}
            style={{ marginRight: '10px', padding: '8px', borderRadius: '4px', border: '1px solid #ccc' }}
          >
            {availableModels.length === 0 ? (
              <option value="">No models available</option>
            ) : (
              availableModels.map(model => (
                <option key={model.id} value={model.id}>{model.name}</option>
              ))
            )}
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
                : pendingAttachments.length > 0
                  ? `${pendingAttachments.length} file(s) attached. Type a message...`
                  : "Type a message..."
            }
            style={{
              borderColor: selectedNodeIds.length === 2 ? '#8b5cf6' : (pendingAttachments.length > 0 ? '#22c55e' : '#ccc'),
              borderWidth: selectedNodeIds.length === 2 || pendingAttachments.length > 0 ? '2px' : '1px'
            }}
            autoFocus
          />
          <button
            type="submit"
            disabled={loading || uploadingFiles || !currentConversationId || (selectedNodeIds.length === 2 && !mergeEligibility?.eligible)}
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
