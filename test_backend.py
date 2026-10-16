"""Quick test script for OmniChat Pro backend"""

import asyncio
import sys

async def test_health():
    """Test health endpoint"""
    import httpx
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get("http://localhost:8000/health")
            print(f"✅ Health check: {response.json()}")
            return True
        except Exception as e:
            print(f"❌ Health check failed: {e}")
            return False

async def test_models():
    """Test models endpoint"""
    import httpx
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get("http://localhost:8000/api/chat/models")
            models = response.json()
            print(f"✅ Models endpoint: {list(models.keys())}")
            return True
        except Exception as e:
            print(f"❌ Models endpoint failed: {e}")
            return False

async def test_agents():
    """Test agents endpoint"""
    import httpx
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get("http://localhost:8000/api/agents/")
            agents = response.json()
            print(f"✅ Agents endpoint: {len(agents.get('agents', []))} agents")
            return True
        except Exception as e:
            print(f"❌ Agents endpoint failed: {e}")
            return False

async def main():
    print("🧪 Testing OmniChat Pro Backend...\n")
    
    tests = [
        ("Health", test_health),
        ("Models", test_models),
        ("Agents", test_agents),
    ]
    
    passed = 0
    for name, test in tests:
        print(f"Testing {name}...")
        if await test():
            passed += 1
        print()
    
    print(f"📊 Results: {passed}/{len(tests)} tests passed")
    
    if passed == len(tests):
        print("\n✅ Backend is running correctly!")
        print("\n📖 Next steps:")
        print("1. Open http://localhost:8000/docs for API documentation")
        print("2. Open http://localhost:3000 for the frontend (if running)")
        return 0
    else:
        print("\n❌ Some tests failed. Make sure backend is running:")
        print("   cd backend && uvicorn main:app --reload")
        return 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
