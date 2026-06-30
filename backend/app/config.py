from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Candidate Data Pipeline Backend"
    environment: str = "development"

    # Database
    database_url: str = "postgresql+psycopg2://postgres:taran@localhost:5432/candidates"

    # Alembic
    alembic_schema: str | None = None

    class Config:
        env_prefix = "APP_"
        env_file = ".env"
        extra = "ignore"


settings = Settings()

