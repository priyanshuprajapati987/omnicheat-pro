"""Test chat with Ollama"""
import httpx
import asyncio

async def test_chat():
    async with httpx.AsyncClient() as client:
        print("Testing chat with Ollama...\n")
        
        # Test 1: Simple chat
        print("Test 1: Simple message")
        response = await client.post(
            "http://localhost:8000/api/chat/send",
            json={
                "message": "Hello! What is 2+2?",
                "model": "llama3.2",
                "agent_type": "general",
            },
            timeout=30.0,
        )
        data = response.json()
        print(f"Response: {data['content'][:200]}")
        print(f"Session: {data.get('session_id', 'N/A')}\n")
        
        # Test 2: Code agent
        print("Test 2: Coder agent")
        response = await client.post(
            "http://localhost:8000/api/chat/send",
            json={
                "message": "Write a Python function to calculate fibonacci",
                "model": "llama3.2",
                "agent_type": "coder",
            },
            timeout=30.0,
        )
        data = response.json()
        print(f"Response: {data['content'][:200]}")
        print(f"Tools used: {data.get('tool_calls', [])}\n")
        
        print("All tests passed!")

asyncio.run(test_chat())
