import asyncio
from sqlalchemy import text
from app.db.session import AsyncSessionLocal

# Import all models to ensure metadata is compiled
import app.models.user
import app.models.workspace
import app.models.document
import app.models.query

async def main():
    async with AsyncSessionLocal() as session:
        # Deleting from users table cascades to all other tables due to ON DELETE CASCADE
        print("Cleaning up database...")
        await session.execute(text("TRUNCATE TABLE users CASCADE;"))
        await session.commit()
        print("Database reset successfully! All users, workspaces, documents, and messages have been cleared.")

if __name__ == "__main__":
    asyncio.run(main())
