import os
import asyncpg
import logging

logger = logging.getLogger(__name__)

async def get_db_pool(database_url: str):
    """Create a connection pool to the PostgreSQL database."""
    logger.info("Connecting to Neon database...")
    if not database_url:
        raise ValueError("DATABASE_URL is not set!")
    return await asyncpg.create_pool(database_url)

async def init_db(pool):
    """Initialize the database tables and triggers."""
    logger.info("Initializing database schema...")
    async with pool.acquire() as conn:
        # Create function for updated_at trigger
        await conn.execute('''
            CREATE OR REPLACE FUNCTION update_updated_at_column()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.updated_at = NOW();
                RETURN NEW;
            END;
            $$ language 'plpgsql';
        ''')

        # Create users table
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                age INTEGER,
                interests TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
        ''')

        # Create trigger for the users table
        await conn.execute('''
            DROP TRIGGER IF EXISTS update_users_updated_at ON users;
            CREATE TRIGGER update_users_updated_at
            BEFORE UPDATE ON users
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
        ''')
    logger.info("Database schema initialized successfully.")

async def get_user(pool, user_id: int):
    """Get a user by their Telegram ID."""
    async with pool.acquire() as conn:
        return await conn.fetchrow('SELECT * FROM users WHERE user_id = $1', user_id)

async def save_user(pool, user_id: int, name: str, age: int, interests: str):
    """Insert or update a user's profile."""
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO users (user_id, name, age, interests)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (user_id) DO UPDATE
            SET name = EXCLUDED.name,
                age = EXCLUDED.age,
                interests = EXCLUDED.interests;
        ''', user_id, name, age, interests)
