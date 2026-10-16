import { useState, useEffect, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { useChatStore } from './store/chat'

function App() {
  const [input, setInput] = useState('')
  const [models, setModels] = useState<Record<string, string[]>>({})
  const [selectedModel, setSelectedModel] = useState('gpt-3.5-turbo')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  
  const { 
    messages, 
    isLoading, 
    error, 
    sessionId,
    agentType,
    clearMessages,
    newSession,
    setAgentType,
    setSessionId,
    addMessage,
    setLoading,
    setError,
  } = useChatStore()

  // Fetch available models
  useEffect(() => {
    fetch('/api/chat/models')
      .then(res => res.json())
      .then(data => {
        setModels(data)
        const firstProvider = Object.keys(data)[0]
        if (firstProvider && data[firstProvider].length > 0) {
          setSelectedModel(data[firstProvider][0])
        }
      })
      .catch(err => console.error('Failed to fetch models:', err))
  }, [])

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = async () => {
    if (!input.trim() || isLoading) return
    
    const userMessage = input
    addMessage({ role: 'user', content: userMessage })
    setLoading(true)
    setInput('')
    
    try {
      const response = await fetch('/api/chat/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: userMessage,
          model: selectedModel,
          session_id: sessionId,
          agent_type: agentType,
        }),
      })
      
      if (!response.ok) throw new Error('Failed to get response')
      
      const data = await response.json()
      
      // Save session ID
      if (data.session_id && !sessionId) {
        setSessionId(data.session_id)
      }
      
      // Add assistant response
      addMessage({
        role: 'assistant',
        content: data.content,
        model: data.model,
        tool_calls: data.tool_calls,
      })
    } catch (err) {
      console.error('Error:', err)
      setError(err instanceof Error ? err.message : 'Failed to get response')
    } finally {
      setLoading(false)
    }
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const agents = [
    { id: 'general', name: 'General', icon: '💬', desc: 'General assistant' },
    { id: 'coder', name: 'Coder', icon: '💻', desc: 'Programming help' },
    { id: 'researcher', name: 'Researcher', icon: '🔍', desc: 'Research topics' },
    { id: 'writer', name: 'Writer', icon: '✍️', desc: 'Content creation' },
  ]

  return (
    <div className="flex h-screen bg-gray-900 text-white">
      {/* Sidebar */}
      <aside className="w-64 bg-gray-800 border-r border-gray-700 flex flex-col">
        <div className="p-4 border-b border-gray-700">
          <h2 className="text-lg font-semibold">🚀 OmniChat Pro</h2>
        </div>
        
        {/* Agent Selector */}
        <div className="p-4 border-b border-gray-700">
          <div className="text-xs text-gray-400 mb-2">SELECT AGENT</div>
          <div className="space-y-2">
            {agents.map((agent) => (
              <button
                key={agent.id}
                onClick={() => setAgentType(agent.id)}
                className={`w-full text-left px-3 py-2 rounded-lg transition ${
                  agentType === agent.id
                    ? 'bg-cyan-600 text-white'
                    : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                }`}
              >
                <div className="flex items-center gap-2">
                  <span>{agent.icon}</span>
                  <span className="font-medium">{agent.name}</span>
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Conversations */}
        <div className="p-4 border-b border-gray-700">
          <button
            onClick={newSession}
            className="w-full text-left px-3 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-700 transition font-medium"
          >
            + New Chat
          </button>
          {sessionId && (
            <div className="mt-2 text-xs text-gray-500">
              Session: {sessionId.slice(0, 8)}...
            </div>
          )}
        </div>

        <div className="flex-1"></div>
        
        <div className="p-4 border-t border-gray-700">
          <div className="text-xs text-gray-500">
            v0.1.0 • Week 2
          </div>
        </div>
      </aside>

      {/* Main Chat */}
      <main className="flex-1 flex flex-col">
        {/* Header */}
        <header className="bg-gray-800 border-b border-gray-700 p-4">
          <div className="flex justify-between items-center">
            <div className="flex items-center gap-3">
              <h1 className="text-xl font-bold">
                {agents.find(a => a.id === agentType)?.icon}{' '}
                {agents.find(a => a.id === agentType)?.name}
              </h1>
              <span className="text-sm text-gray-400">
                {agents.find(a => a.id === agentType)?.desc}
              </span>
            </div>
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              className="bg-gray-700 text-white px-3 py-2 rounded-lg border border-gray-600 focus:outline-none focus:border-cyan-500 text-sm"
            >
              {Object.entries(models).map(([provider, modelList]) =>
                modelList.map(model => (
                  <option key={model} value={model}>
                    {model}
                  </option>
                ))
              )}
            </select>
          </div>
        </header>

        {/* Error Banner */}
        {error && (
          <div className="bg-red-600 text-white px-4 py-2 text-sm flex justify-between items-center">
            <span>{error}</span>
            <button onClick={() => setError(null)} className="ml-4">✕</button>
          </div>
        )}

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4">
          <div className="max-w-4xl mx-auto space-y-4">
            {messages.length === 0 ? (
              <div className="text-center py-20 text-gray-400">
                <h2 className="text-4xl font-bold mb-4">👋 Welcome!</h2>
                <p className="text-lg mb-8">Select an agent and start chatting</p>
                <div className="grid grid-cols-2 gap-4 max-w-2xl mx-auto">
                  {agents.map((agent) => (
                    <button
                      key={agent.id}
                      onClick={() => setAgentType(agent.id)}
                      className="bg-gray-800 hover:bg-gray-700 p-4 rounded-xl text-left transition"
                    >
                      <div className="text-2xl mb-2">{agent.icon}</div>
                      <div className="font-medium">{agent.name}</div>
                      <div className="text-sm text-gray-400">{agent.desc}</div>
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((msg, index) => (
                <div
                  key={index}
                  className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-[80%] rounded-2xl p-4 ${
                      msg.role === 'user'
                        ? 'bg-cyan-600'
                        : 'bg-gray-800'
                    }`}
                  >
                    {msg.role === 'assistant' ? (
                      <div className="prose prose-invert max-w-none">
                        <ReactMarkdown
                          components={{
                            code({ className, children, ...props }) {
                              const match = /language-(\w+)/.exec(className || '')
                              return match ? (
                                <SyntaxHighlighter
                                  style={oneDark}
                                  language={match[1]}
                                  PreTag="div"
                                  className="rounded-lg my-2"
                                  {...props}
                                >
                                  {String(children).replace(/\n$/, '')}
                                </SyntaxHighlighter>
                              ) : (
                                <code className="bg-gray-700 px-2 py-1 rounded" {...props}>
                                  {children}
                                </code>
                              )
                            },
                          }}
                        >
                          {msg.content}
                        </ReactMarkdown>
                      </div>
                    ) : (
                      <p className="whitespace-pre-wrap">{msg.content}</p>
                    )}
                    {msg.tool_calls && msg.tool_calls.length > 0 && (
                      <div className="mt-2 flex gap-2">
                        {msg.tool_calls.map((tool, i) => (
                          <span key={i} className="text-xs bg-gray-700 px-2 py-1 rounded">
                            🔧 {tool}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))
            )}
            
            {isLoading && (
              <div className="flex justify-start">
                <div className="bg-gray-800 rounded-2xl p-4">
                  <div className="flex items-center gap-3">
                    <div className="flex space-x-2">
                      <div className="w-2 h-2 bg-cyan-400 rounded-full animate-bounce"></div>
                      <div className="w-2 h-2 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                      <div className="w-2 h-2 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: '0.4s' }}></div>
                    </div>
                    <span className="text-gray-400 text-sm">Thinking...</span>
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Input */}
        <div className="border-t border-gray-700 p-4 bg-gray-800">
          <div className="max-w-4xl mx-auto">
            <div className="flex gap-3">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder={`Message ${agents.find(a => a.id === agentType)?.name}...`}
                rows={1}
                className="flex-1 bg-gray-700 text-white px-4 py-3 rounded-xl border border-gray-600 focus:outline-none focus:border-cyan-500 resize-none"
                disabled={isLoading}
              />
              <button
                onClick={handleSend}
                disabled={isLoading || !input.trim()}
                className="bg-cyan-600 hover:bg-cyan-700 disabled:bg-gray-600 disabled:cursor-not-allowed px-6 py-3 rounded-xl font-semibold transition"
              >
                {isLoading ? (
                  <span className="animate-pulse">...</span>
                ) : (
                  'Send'
                )}
              </button>
            </div>
            <p className="text-xs text-gray-500 mt-2 text-center">
              Enter to send • Shift+Enter for new line • Tools auto-detected
            </p>
          </div>
        </div>
      </main>
    </div>
  )
}

export default App
