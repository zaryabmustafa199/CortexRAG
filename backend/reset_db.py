import asyncio

from sqlalchemy import text

# Import all models to ensure metadata is compiled
from app.db.session import AsyncSessionLocal


async def main():
    async with AsyncSessionLocal() as session:
        # Deleting from users table cascades to all other tables due to ON DELETE CASCADE
        print("Cleaning up database...")
        await session.execute(text("TRUNCATE TABLE users CASCADE;"))
        await session.commit()
        print(
            "Database reset successfully! All users, workspaces, documents, and messages have been cleared."
        )


if __name__ == "__main__":
    asyncio.run(main())
