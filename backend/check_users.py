import asyncio

from sqlalchemy import select

# Import all models to configure registries
from app.db.session import AsyncSessionLocal
from app.models.user import User


async def main():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User))
        users = result.scalars().all()
        print(f"TOTAL USERS IN DB: {len(users)}")
        for u in users:
            print(f"- Email: '{u.email}', Active: {u.is_active}, Password Hash: '{u.hashed_password[:30]}...'")

if __name__ == "__main__":
    asyncio.run(main())
