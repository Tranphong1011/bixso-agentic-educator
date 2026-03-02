import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    DATABASE_URL: str
    ENV: str = "dev"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL is required. Set it in your environment or .env file.")

    env = os.getenv("ENV", "dev")
    return Settings(DATABASE_URL=database_url, ENV=env)


settings = get_settings()
