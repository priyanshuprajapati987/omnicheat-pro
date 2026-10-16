// WebSocket hook for streaming chat
import { useEffect, useRef, useCallback } from 'react'
import { useChatStore } from '../store/chat'

export function useChatStream() {
  const wsRef = useRef<WebSocket | null>(null)
  const { addMessage, updateLastMessage, setLoading, setError } = useChatStore()

  useEffect(() => {
    // Connect to WebSocket
    const ws = new WebSocket(`ws://${window.location.hostname}:8000/api/chat/ws`)
    
    ws.onopen = () => {
      console.log('WebSocket connected')
    }
    
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      
      switch (data.type) {
        case 'start':
          // Assistant message started
          addMessage({ role: 'assistant', content: '', model: data.model })
          break
          
        case 'token':
          // Append token to last message
          const messages = useChatStore.getState().messages
          const lastMessage = messages[messages.length - 1]
          if (lastMessage && lastMessage.role === 'assistant') {
            updateLastMessage(lastMessage.content + data.content)
          }
          break
          
        case 'end':
          // Message complete
          setLoading(false)
          break
          
        case 'error':
          setError(data.content)
          setLoading(false)
          break
      }
    }
    
    ws.onclose = () => {
      console.log('WebSocket disconnected')
    }
    
    ws.onerror = (error) => {
      console.error('WebSocket error:', error)
      setError('Connection error')
      setLoading(false)
    }
    
    wsRef.current = ws
    
    return () => {
      ws.close()
    }
  }, [])

  const sendMessage = useCallback((
    message: string,
    model: string,
    history: Array<{ role: string; content: string }>
  ) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      setError('Not connected')
      return
    }
    
    addMessage({ role: 'user', content: message })
    setLoading(true)
    
    wsRef.current.send(JSON.stringify({
      role: 'user',
      content: message,
      model,
      history,
    }))
  }, [])

  return { sendMessage }
}
