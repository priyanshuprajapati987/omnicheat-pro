import { useState } from 'react'

function App() {
  const [count, setCount] = useState(0)

  return (
    <div className="min-h-screen bg-gray-900 text-white">
      <div className="container mx-auto p-8">
        <h1 className="text-4xl font-bold mb-4">🚀 OmniChat Pro</h1>
        <p className="text-gray-400 mb-8">
          Professional AI Chat - Multi-model, agents, memory, tools
        </p>
        
        <div className="bg-gray-800 rounded-lg p-6">
          <p className="text-gray-300 mb-4">
            Frontend setup complete! Edit <code className="text-cyan-400">frontend/src/App.tsx</code> to start building.
          </p>
          <button
            onClick={() => setCount((count) => count + 1)}
            className="bg-cyan-600 hover:bg-cyan-700 px-4 py-2 rounded-lg transition"
          >
            Count: {count}
          </button>
        </div>
      </div>
    </div>
  )
}

export default App
