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

    # 레이트리밋 (HIVE-92). 인메모리 슬라이딩 윈도우, 단일 프로세스 기준.
    upload_rate_per_minute: int = 3       # 업로드 /분/유저
    upload_rate_per_day: int = 10         # 업로드 /일/유저 (LLM 비용 가드레일)
    recommend_rate_per_minute: int = 20   # 추천 /분/유저
    synthesis_rate_per_minute: int = 10   # synthesis 조회 /분/유저

    # 업로드 요청 크기 제한 (HIVE-92)
    upload_max_title_chars: int = 500
    upload_max_body_chars: int = 20_000   # ~4000 토큰 상당


settings = Settings()
