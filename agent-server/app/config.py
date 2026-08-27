from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AGENT_",
        env_file=".env",
        extra="ignore",
    )

    app_env: Literal["dev", "test", "prod"] = "dev"
    app_name: str = "enterprise-agent-platform"
    api_prefix: str = "/api/v1"

    storage_mode: Literal["memory", "postgres"] = "memory"
    database_url: str = "postgresql+asyncpg://agent:agent@localhost:5432/agent_platform"
    db_pool_size: int = 5

    iam_mode: Literal["mock", "ruoyi"] = "mock"
    ruoyi_auth_mode: Literal["ticket", "password"] = "password"
    ruoyi_base_url: str = "http://localhost:8080"
    ruoyi_ticket_path: str = "/client/ticketLogin"
    ruoyi_login_path: str = "/login"
    ruoyi_captcha_path: str = "/captchaImage"
    ruoyi_current_user_path: str = "/agent-iam/me"
    ruoyi_dept_path: str = "/agent-iam/departments"
    ruoyi_sub_dept_path: str = "/agent-iam/departments"
    ruoyi_user_search_path: str = "/agent-iam/users"
    ruoyi_role_search_path: str = "/system/role/list"
    ruoyi_default_org_id: str = "ruoyi-default"
    ruoyi_timeout_seconds: float = 5.0
    ruoyi_verify_tls: bool = True

    # JSON object: {"external_org_id": "platform-tenant-id"}
    tenant_map: dict[str, str] = Field(default_factory=lambda: {"org-demo": "tenant-demo"})

    session_storage_mode: Literal["memory", "redis"] = "memory"
    redis_url: str = "redis://localhost:6379/0"
    redis_session_key_prefix: str = "agent-platform:session:"

    session_idle_minutes: int = 30
    session_absolute_hours: int = 8
    session_encryption_key: str | None = None
    secret_encryption_key: str | None = None
    session_cookie_name: str = "__Host-ap_session"
    session_cookie_secure: bool = True
    allow_direct_bearer: bool = False

    # RuoYi roles/users mapped to platform control-plane responsibilities.
    # Platform admins operate governance/infrastructure. Resource developers
    # create tenant AI assets but receive no implicit VIEW/USE/RUN grants.
    platform_admin_role_codes: list[str] = Field(default_factory=lambda: ["agent_admin"])
    platform_admin_user_ids: list[str] = Field(default_factory=list)
    resource_developer_role_codes: list[str] = Field(default_factory=lambda: ["agent_developer"])
    resource_developer_user_ids: list[str] = Field(default_factory=list)

    runtime_execution_mode: Literal["disabled", "in_process", "worker"] = "in_process"
    worker_poll_interval_seconds: float = 0.5
    worker_id: str = "agent-worker-1"
    runtime_harness: Literal["mock", "langgraph_baseline"] = "mock"
    model_request_timeout_seconds: float = 180.0
    minio_endpoint: str = "http://localhost:9000"
    minio_bucket: str = "agent-platform"
    minio_access_key: str | None = None
    minio_secret_key: str | None = None
    knowledge_upload_max_bytes: int = 20 * 1024 * 1024
    trusted_origins: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_production_safety(self) -> "Settings":
        if self.app_env == "prod" and self.iam_mode == "mock":
            raise ValueError("AGENT_IAM_MODE=mock is not allowed in prod")
        if self.app_env == "prod" and self.storage_mode != "postgres":
            raise ValueError("AGENT_STORAGE_MODE=postgres is required in prod")
        if self.app_env == "prod" and self.session_storage_mode != "redis":
            raise ValueError("AGENT_SESSION_STORAGE_MODE=redis is required in prod")
        if self.app_env == "prod" and self.runtime_execution_mode not in {"disabled", "worker"}:
            raise ValueError("AGENT_RUNTIME_EXECUTION_MODE=worker is required in prod")
        if self.app_env == "prod" and not self.session_cookie_secure:
            raise ValueError("AGENT_SESSION_COOKIE_SECURE must be enabled in prod")
        if self.app_env == "prod" and self.allow_direct_bearer:
            raise ValueError("AGENT_ALLOW_DIRECT_BEARER is not allowed in prod")
        if self.app_env == "prod" and not self.secret_encryption_key:
            raise ValueError("AGENT_SECRET_ENCRYPTION_KEY is required in prod")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
