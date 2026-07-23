import asyncio
import os
import psycopg
from pydantic_settings import BaseSettings, SettingsConfigDict


class InitSettings(BaseSettings):
    # Default to the postgres database to execute CREATE DATABASE
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@db:5432/postgres"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = InitSettings()

async def create_test_db():
    print(f"Connecting to {settings.DATABASE_URL} to create test_docrag...")
    # Need to connect with autocommit to create a database
    conn = await psycopg.AsyncConnection.connect(
        settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://"),
        autocommit=True
    )
    
    try:
        async with conn.cursor() as cur:
            # Check if db exists
            await cur.execute("SELECT 1 FROM pg_database WHERE datname = 'test_docrag'")
            exists = await cur.fetchone()
            
            if exists:
                print("Database test_docrag already exists.")
            else:
                await cur.execute("CREATE DATABASE test_docrag")
                print("Database test_docrag created successfully.")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(create_test_db())
