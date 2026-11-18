from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = "Облік впливу погодних умов на вимірювальні модулі"
    API_V1_PREFIX: str = "/api/v1"
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    FIRST_ADMIN_EMAIL: str = "admin@nure.ua"
    FIRST_ADMIN_PASSWORD: str = "AdminPassword123!"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()