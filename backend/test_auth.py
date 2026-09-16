import pytest
import asyncio
from httpx import AsyncClient, ASGITransport
from .main import app
from .database import init_db

@pytest.fixture(autouse=True)
async def setup_db():
    await init_db()

@pytest.mark.asyncio
async def test_auth_flow():
    # Make sure to initialize the DB so the users table is created and seeded.
    await init_db()
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. Login as Admin
        response = await ac.post("/api/auth/token", data={
            "username": "admin",
            "password": "admin"
        })
        assert response.status_code == 200
        token = response.json()["access_token"]
        
        # 2. Access protected route with token
        headers = {"Authorization": f"Bearer {token}"}
        response = await ac.post("/api/simulation/pause", headers=headers)
        assert response.status_code == 200
        
        # 3. Access protected route without token (should fail)
        response = await ac.post("/api/simulation/pause")
        assert response.status_code == 401

        # 4. Login as Occupant
        response = await ac.post("/api/auth/token", data={
            "username": "occupantA",
            "password": "occupant"
        })
        assert response.status_code == 200
        occ_token = response.json()["access_token"]

        # 5. Occupant tries to access admin route (should fail)
        occ_headers = {"Authorization": f"Bearer {occ_token}"}
        response = await ac.post("/api/simulation/pause", headers=occ_headers)
        assert response.status_code == 403
        
        # 6. Occupant tries to access occupant route (should succeed)
        response = await ac.post("/api/chat/message", json={"message": "it is too cold"}, headers=occ_headers)
        assert response.status_code == 200
