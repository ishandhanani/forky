import { useState, useEffect, useCallback, useRef } from 'react'
import Tree from 'react-d3-tree'
import axios from 'axios'
import './App.css'
import CustomNode from './CustomNode'

const API_URL = 'http://localhost:8000'

function App() {
  const [conversations, setConversations] = useState([])
  const [currentConversationId, setCurrentConversationId] = useState(null)
  const [treeData, setTreeData] = useState(null)
  const [history, setHistory] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [sidebarWidth, setSidebarWidth] = useState(450)
  const [isResizing, setIsResizing] = useState(false)
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
    } catch (err) {
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
          setTreeData(null)
          setHistory([])
          setCurrentConversationId(null)
        }
      }
    } catch (err) {
      console.error("Delete failed", err)
      alert('Failed to delete conversation')
    }
  }

  const fetchTree = useCallback(async () => {
    try {
      const url = currentConversationId ? `${API_URL}/tree?conversation_id=${currentConversationId}` : `${API_URL}/tree`
      const res = await axios.get(url)

      const transform = (node) => {
        // Linear merge: User -> one Assistant child
        if (node.role === 'user' && node.children && node.children.length === 1 && node.children[0].role === 'assistant') {
          const assistantNode = node.children[0];
          return {
            name: 'TURN',
            role: 'turn',
            userContent: node.content,
            assistantContent: assistantNode.content,
            attributes: {
              id: assistantNode.id,
              isCurrent: assistantNode.is_current || node.is_current,
              fullUserContent: node.content,
              fullAssistantContent: assistantNode.content
            },
            children: assistantNode.children.map(transform)
          }
        }

        return {
          name: node.role === 'system' && node.content === 'Root' ? 'ROOT' :
            node.role === 'system' && node.content === '<FORK>' ? `<FORK: ${node.branch_name}>` :
              `${node.role}`,
          role: node.role,
          content: node.content,
          attributes: {
            id: node.id,
            fullContent: node.content,
            branch: node.branch_name,
            isCurrent: node.is_current
          },
          children: node.children ? node.children.map(transform) : []
        }
      }

      if (res.data.root) {
        setTreeData([transform(res.data.root)])
      }
      if (res.data.conversation_id && !currentConversationId) {
        setCurrentConversationId(res.data.conversation_id)
      }
    } catch (err) {
      console.error("Failed to fetch tree", err)
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
    fetchTree()
    fetchHistory()
  }, [fetchTree, fetchHistory])

  // Initial load
  useEffect(() => {
    fetchConversations()
    refresh()
  }, [fetchConversations, refresh])

  const sendMessage = async (e) => {
    e.preventDefault()
    if (!input.trim()) return

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
          conversation_id: currentConversationId
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

  const handleNodeClick = async (nodeDatum) => {
    const attributes = nodeDatum.attributes || (nodeDatum.data && nodeDatum.data.attributes);
    if (attributes && attributes.id) {
      // Auto-checkout on click
      try {
        await axios.post(`${API_URL}/checkout`, {
          identifier: attributes.id,
          conversation_id: currentConversationId
        })
        refresh()
      } catch (err) {
        console.error("Checkout failed", err)
      }
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
              <span>{conv.name.substring(0, 15)}</span>
              <span
                onClick={(e) => handleDeleteConversation(e, conv.id)}
                style={{ opacity: 0.5, fontSize: '0.8rem' }}
              >
                ✕
              </span>
            </li>
          ))}
        </ul>
        <div className="nav-actions">
          <button onClick={handleCreateConversation}>+ New Chat</button>
        </div>
      </div>

      {/* Tree Visualization Sidebar */}
      <div className="sidebar" style={{ width: sidebarWidth }}>
        <div className="resizer" onMouseDown={startResizing} />
        <h2>Conversation Tree</h2>
        <div className="tree-container">
          {treeData && (
            <Tree
              data={treeData}
              orientation="vertical"
              onNodeClick={handleNodeClick}
              pathFunc="step"
              translate={{ x: sidebarWidth / 2, y: 50 }}
              collapsible={false}
              zoomable={true}
              scaleExtent={{ min: 0.1, max: 2 }}
              nodeSize={{ x: 300, y: 150 }}
              renderCustomNodeElement={(rd3tProps) => (
                <CustomNode {...rd3tProps} onNodeClick={handleNodeClick} />
              )}
            />
          )}
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
                  {content}
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
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={loading || !currentConversationId}
            placeholder={currentConversationId ? "Type a message..." : "Create a chat to start"}
            autoFocus
          />
          <button type="submit" disabled={loading || !currentConversationId}>
            {loading ? '...' : 'Send'}
          </button>
        </form>
      </div>
    </div>
  )
}

export default App
