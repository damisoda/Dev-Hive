from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM / 임베딩
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # 크롤링
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "script:dev-hive:v1.0"
    github_token: str = ""

    # DB
    database_url: str = "postgresql://devhive:devhive@localhost:5432/devhive"

    # 백엔드
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000

    # 인증 (HIVE-100). jwt_secret은 운영에서 반드시 .env로 주입(빈 값이면 토큰 발급/검증 거부).
    jwt_secret: str = ""
    jwt_expire_hours: int = 336  # 14일


settings = Settings()
