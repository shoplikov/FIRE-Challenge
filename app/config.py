from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://tickets:tickets@db:5432/tickets_db"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "attachments"
    minio_secure: bool = False
    geocoder_user_agent: str = "ticket-distribution-service"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
