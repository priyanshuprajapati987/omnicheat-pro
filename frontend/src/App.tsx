import { useState, useEffect, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { useChatStore } from './store/chat'
import { useChatStream } from './hooks/useChatStream'

function App() {
  const [input, setInput] = useState('')
  const [models, setModels] = useState<Record<string, string[]>>({})
  const [selectedModel, setSelectedModel] = useState('gpt-3.5-turbo')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  
  const { messages, isLoading, error, clearMessages } = useChatStore()
  const { sendMessage } = useChatStream()

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

  const handleSend = () => {
    if (!input.trim() || isLoading) return
    
    const history = messages.slice(-10).map(m => ({
      role: m.role,
      content: m.content,
    }))
    
    sendMessage(input, selectedModel, history)
    setInput('')
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="flex h-screen bg-gray-900 text-white">
      {/* Sidebar */}
      <aside className="w-64 bg-gray-800 border-r border-gray-700 flex flex-col">
        <div className="p-4 border-b border-gray-700">
          <h2 className="text-lg font-semibold">💬 Conversations</h2>
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          <button
            onClick={clearMessages}
            className="w-full text-left px-3 py-2 rounded-lg hover:bg-gray-700 transition text-gray-300"
          >
            + New Chat
          </button>
          {/* Conversation list will go here (Week 2) */}
        </div>
        <div className="p-4 border-t border-gray-700">
          <div className="text-xs text-gray-500">
            OmniChat Pro v0.1.0
          </div>
        </div>
      </aside>

      {/* Main Chat */}
      <main className="flex-1 flex flex-col">
        {/* Header */}
        <header className="bg-gray-800 border-b border-gray-700 p-4">
          <div className="flex justify-between items-center">
            <h1 className="text-xl font-bold">🚀 OmniChat Pro</h1>
            <div className="flex items-center gap-3">
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
          </div>
        </header>

        {/* Error Banner */}
        {error && (
          <div className="bg-red-600 text-white px-4 py-2 text-sm">
            {error}
          </div>
        )}

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4">
          <div className="max-w-4xl mx-auto space-y-4">
            {messages.length === 0 ? (
              <div className="text-center py-20 text-gray-400">
                <h2 className="text-4xl font-bold mb-4">👋 Welcome!</h2>
                <p className="text-lg mb-8">Start a conversation with AI</p>
                <div className="grid grid-cols-2 gap-4 max-w-2xl mx-auto">
                  <button
                    onClick={() => setInput("What's the capital of France?")}
                    className="bg-gray-800 hover:bg-gray-700 p-4 rounded-xl text-left transition"
                  >
                    <div className="text-2xl mb-2">🌍</div>
                    <div className="font-medium">Ask a question</div>
                    <div className="text-sm text-gray-400">General knowledge</div>
                  </button>
                  <button
                    onClick={() => setInput("Write a Python function to sort a list")}
                    className="bg-gray-800 hover:bg-gray-700 p-4 rounded-xl text-left transition"
                  >
                    <div className="text-2xl mb-2">💻</div>
                    <div className="font-medium">Write code</div>
                    <div className="text-sm text-gray-400">Programming help</div>
                  </button>
                  <button
                    onClick={() => setInput("Explain quantum computing in simple terms")}
                    className="bg-gray-800 hover:bg-gray-700 p-4 rounded-xl text-left transition"
                  >
                    <div className="text-2xl mb-2">🧠</div>
                    <div className="font-medium">Learn something</div>
                    <div className="text-sm text-gray-400">Explanations</div>
                  </button>
                  <button
                    onClick={() => setInput("Help me write an email to my boss")}
                    className="bg-gray-800 hover:bg-gray-700 p-4 rounded-xl text-left transition"
                  >
                    <div className="text-2xl mb-2">✍️</div>
                    <div className="font-medium">Write content</div>
                    <div className="text-sm text-gray-400">Emails, essays, etc.</div>
                  </button>
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
                    {msg.model && (
                      <div className="text-xs opacity-60 mt-2">
                        {msg.model}
                      </div>
                    )}
                  </div>
                </div>
              ))
            )}
            
            {isLoading && (
              <div className="flex justify-start">
                <div className="bg-gray-800 rounded-2xl p-4">
                  <div className="flex space-x-2">
                    <div className="w-2 h-2 bg-cyan-400 rounded-full animate-bounce"></div>
                    <div className="w-2 h-2 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                    <div className="w-2 h-2 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: '0.4s' }}></div>
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
                placeholder="Type your message..."
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
              Enter to send • Shift+Enter for new line
            </p>
          </div>
        </div>
      </main>
    </div>
  )
}

export default App
