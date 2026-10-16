import { create } from 'zustand'

interface Message {
  role: 'user' | 'assistant'
  content: string
  model?: string
}

interface ChatState {
  messages: Message[]
  isLoading: boolean
  error: string | null
  addMessage: (message: Message) => void
  updateLastMessage: (content: string) => void
  setLoading: (loading: boolean) => void
  setError: (error: string | null) => void
  clearMessages: () => void
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  isLoading: false,
  error: null,
  
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
  clearMessages: () => set({ messages: [] }),
}))
