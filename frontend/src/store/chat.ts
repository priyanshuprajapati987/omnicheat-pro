import { create } from 'zustand'

interface Message {
  role: 'user' | 'assistant'
  content: string
  model?: string
  tool_calls?: string[]
}

interface ChatState {
  messages: Message[]
  isLoading: boolean
  error: string | null
  sessionId: string | null
  agentType: string
  addMessage: (message: Message) => void
  updateLastMessage: (content: string) => void
  setLoading: (loading: boolean) => void
  setError: (error: string | null) => void
  setSessionId: (id: string) => void
  setAgentType: (type: string) => void
  clearMessages: () => void
  newSession: () => void
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  isLoading: false,
  error: null,
  sessionId: null,
  agentType: 'general',
  
  addMessage: (message) =>
    set((state) => ({ messages: [...state.messages, message] })),
  
  updateLastMessage: (content) =>
    set((state) => {
      const messages = [...state.messages]
      const lastIndex = messages.length - 1
      if (lastIndex >= 0 && messages[lastIndex].role === 'assistant') {
        messages[lastIndex] = { ...messages[lastIndex], content }
      }
      return { messages }
    }),
  
  setLoading: (loading) => set({ isLoading: loading }),
  setError: (error) => set({ error }),
  setSessionId: (id) => set({ sessionId: id }),
  setAgentType: (type) => set({ agentType: type }),
  
  clearMessages: () => set({ messages: [] }),
  
  newSession: () => set({
    messages: [],
    sessionId: null,
    error: null,
  }),
}))
