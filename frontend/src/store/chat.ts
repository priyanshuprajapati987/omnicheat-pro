import { create } from 'zustand'

interface Message {
  role: 'user' | 'assistant'
  content: string
  model?: string
  tool_calls?: string[]
}

interface SessionMeta {
  id: string
  title: string
  agentType: string
  updatedAt: number
  messages: Message[]
}

interface ChatState {
  messages: Message[]
  isLoading: boolean
  error: string | null
  sessionId: string | null
  agentType: string
  sessions: SessionMeta[]
  addMessage: (message: Message) => void
  updateLastMessage: (content: string) => void
  setLoading: (loading: boolean) => void
  setError: (error: string | null) => void
  setSessionId: (id: string) => void
  setAgentType: (type: string) => void
  clearMessages: () => void
  newSession: () => void
  loadSession: (id: string) => void
  deleteSession: (id: string) => void
  saveCurrentSession: () => void
}

function loadSessions(): SessionMeta[] {
  try {
    const raw = localStorage.getItem('omnicheat-sessions')
    return raw ? JSON.parse(raw) : []
  } catch { return [] }
}

function persistSessions(sessions: SessionMeta[]) {
  // Keep last 50 sessions
  const capped = sessions.slice(0, 50)
  localStorage.setItem('omnicheat-sessions', JSON.stringify(capped))
}

function makeTitle(messages: Message[]): string {
  const firstUser = messages.find(m => m.role === 'user')
  if (!firstUser) return 'New Chat'
  const t = firstUser.content.slice(0, 40)
  return t.length < firstUser.content.length ? t + '...' : t
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  isLoading: false,
  error: null,
  sessionId: null,
  agentType: 'general',
  sessions: loadSessions(),

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

  newSession: () => {
    // Save current session before creating new one
    get().saveCurrentSession()
    set({
      messages: [],
      sessionId: null,
      error: null,
    })
  },

  saveCurrentSession: () => {
    const { sessionId, messages, agentType, sessions } = get()
    if (!sessionId || messages.length === 0) return

    const meta: SessionMeta = {
      id: sessionId,
      title: makeTitle(messages),
      agentType,
      updatedAt: Date.now(),
      messages,
    }

    const existing = sessions.findIndex(s => s.id === sessionId)
    let next: SessionMeta[]
    if (existing >= 0) {
      next = [...sessions]
      next[existing] = meta
    } else {
      next = [meta, ...sessions]
    }
    persistSessions(next)
    set({ sessions: next })
  },

  loadSession: (id) => {
    const { sessions } = get()
    const session = sessions.find(s => s.id === id)
    if (!session) return
    set({
      messages: session.messages,
      sessionId: session.id,
      agentType: session.agentType,
      error: null,
    })
  },

  deleteSession: (id) => {
    const { sessions, sessionId } = get()
    const next = sessions.filter(s => s.id !== id)
    persistSessions(next)
    // If deleting active session, reset chat
    if (sessionId === id) {
      set({ sessions: next, messages: [], sessionId: null, error: null })
    } else {
      set({ sessions: next })
    }
  },
}))
