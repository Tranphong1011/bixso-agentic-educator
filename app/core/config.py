import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    DATABASE_URL: str
    ENV: str = "dev"
    OPENAI_API_KEY: str = ""
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    QDRANT_URL: str = ""
    QDRANT_API_KEY: str = ""
    QDRANT_COLLECTION: str = "education-collection"
    CHUNK_SIZE: int = 800
    CHUNK_OVERLAP: int = 120


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL is required. Set it in your environment or .env file.")

    env = os.getenv("ENV", "dev")
    return Settings(
        DATABASE_URL=database_url,
        ENV=env,
        OPENAI_API_KEY=os.getenv("OPENAI_API_KEY", ""),
        EMBEDDING_MODEL=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
        QDRANT_URL=os.getenv("QDRANT_URL", ""),
        QDRANT_API_KEY=os.getenv("QDRANT_API_KEY", ""),
        QDRANT_COLLECTION=os.getenv("QDRANT_COLLECTION", "education-collection"),
        CHUNK_SIZE=int(os.getenv("CHUNK_SIZE", "800")),
        CHUNK_OVERLAP=int(os.getenv("CHUNK_OVERLAP", "120")),
    )


settings = get_settings()
