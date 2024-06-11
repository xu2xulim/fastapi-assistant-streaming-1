from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "OpenAI Assistant FastAPI micro"
    OPENAI_API_KEY: str
    OPENAI_ASSISTANT_ID: str
    PROJECT_VERSION: str = "1.0.0"
    EMAIL_SUBSTRING_START: str
    EMAIL_SUBSTRING_END: str

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
