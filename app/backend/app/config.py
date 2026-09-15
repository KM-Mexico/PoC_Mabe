from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Business Case Agent API"
    api_prefix: str = "/api/v1"
    database_url: str = "sqlite:////data/business_case.db"
    use_mocks: bool = False
    agent_mode: bool = True
    agent_env: str = "test"
    max_request_body_bytes: int = 55_574_528
    max_json_request_body_bytes: int = 1_048_576
    upload_directory: str = "/data/uploads"
    llm_provider: str = "openai_compatible"
    llm_base_url: str = "https://api.servicesessentials.ibm.com/v1"
    llm_api_style: str = "responses"
    llm_generator_model: str = ""
    llm_critic_model: str = ""
    llm_api_key_file: str = "/run/secrets/llm_api_key"
    llm_ca_bundle: str = ""
    llm_user_agent: str = "business-case-agent/0.1"
    llm_originator: str = ""
    llm_timeout_seconds: int = Field(default=60, ge=1, le=300)
    llm_max_retries: int = Field(default=2, ge=0, le=5)
    llm_max_output_tokens: int = Field(default=4_096, ge=128, le=16_384)
    quality_score_threshold: int = Field(default=80, ge=0, le=100)

    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
