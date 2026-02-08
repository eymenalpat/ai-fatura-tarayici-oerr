import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env'),
        env_file_encoding='utf-8',
        case_sensitive=False,
        extra='ignore'
    )

    # Application
    APP_NAME: str = Field(default="AI Fatura Tarayıcı")
    APP_VERSION: str = Field(default="1.0.0")
    DEBUG: bool = Field(default=False)
    ENVIRONMENT: str = Field(default="development")
    API_V1_PREFIX: str = Field(default="/api/v1")

    # Server
    HOST: str = Field(default="0.0.0.0")
    PORT: int = Field(default=8000)
    BACKEND_CORS_ORIGINS: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000"]
    )

    # Database
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres_password@localhost:5432/ai_invoice_db"
    )
    DATABASE_POOL_SIZE: int = Field(default=20)
    DATABASE_MAX_OVERFLOW: int = Field(default=10)
    DATABASE_POOL_PRE_PING: bool = Field(default=True)
    DATABASE_ECHO: bool = Field(default=False)

    # Redis
    REDIS_URL: str = Field(default="redis://localhost:6379/0")
    REDIS_PASSWORD: Optional[str] = Field(default=None)
    REDIS_DB: int = Field(default=0)
    REDIS_MAX_CONNECTIONS: int = Field(default=50)
    REDIS_DECODE_RESPONSES: bool = Field(default=True)

    # Celery
    CELERY_BROKER_URL: str = Field(default="redis://localhost:6379/1")
    CELERY_RESULT_BACKEND: str = Field(default="redis://localhost:6379/2")
    CELERY_TASK_SERIALIZER: str = Field(default="json")
    CELERY_RESULT_SERIALIZER: str = Field(default="json")
    CELERY_ACCEPT_CONTENT: list[str] = Field(default=["json"])
    CELERY_TIMEZONE: str = Field(default="Europe/Istanbul")
    CELERY_ENABLE_UTC: bool = Field(default=True)
    CELERY_TASK_TRACK_STARTED: bool = Field(default=True)
    CELERY_TASK_TIME_LIMIT: int = Field(default=30 * 60)
    CELERY_TASK_SOFT_TIME_LIMIT: int = Field(default=25 * 60)

    # JWT Authentication
    JWT_SECRET_KEY: str = Field(
        default="supersecretkey_change_in_production_minimum_32_characters_long"
    )
    JWT_ALGORITHM: str = Field(default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7)

    # Google Cloud Vision OCR
    GOOGLE_VISION_CREDENTIALS_PATH: Optional[str] = Field(default=None)
    GOOGLE_CLOUD_PROJECT_ID: Optional[str] = Field(default=None)
    GOOGLE_VISION_API_KEY: Optional[str] = Field(default=None)

    # OpenAI
    OPENAI_API_KEY: Optional[str] = Field(default=None)
    OPENAI_MODEL: str = Field(default="gpt-4-turbo-preview")
    OPENAI_TEMPERATURE: float = Field(default=0.1)
    OPENAI_MAX_TOKENS: int = Field(default=2000)
    OPENAI_TIMEOUT: int = Field(default=60)

    # AWS S3
    AWS_ACCESS_KEY_ID: Optional[str] = Field(default=None)
    AWS_SECRET_ACCESS_KEY: Optional[str] = Field(default=None)
    AWS_REGION: str = Field(default="eu-central-1")
    AWS_S3_BUCKET: Optional[str] = Field(default="ai-invoice-bucket")
    AWS_S3_USE_SSL: bool = Field(default=True)
    AWS_S3_ENDPOINT_URL: Optional[str] = Field(default=None)

    # Google Cloud Storage (alternative to S3)
    GCS_BUCKET_NAME: Optional[str] = Field(default=None)
    GCS_CREDENTIALS_PATH: Optional[str] = Field(default=None)
    GCS_PROJECT_ID: Optional[str] = Field(default=None)

    # Storage Provider Selection
    STORAGE_PROVIDER: str = Field(default="s3")

    # Paraşüt Integration
    PARASUT_CLIENT_ID: Optional[str] = Field(default=None)
    PARASUT_CLIENT_SECRET: Optional[str] = Field(default=None)
    PARASUT_USERNAME: Optional[str] = Field(default=None)
    PARASUT_PASSWORD: Optional[str] = Field(default=None)
    PARASUT_COMPANY_ID: Optional[str] = Field(default=None)
    PARASUT_REDIRECT_URI: str = Field(default="http://localhost:8000/api/v1/parasut/callback")
    PARASUT_API_BASE_URL: str = Field(default="https://api.parasut.com/v4")

    # File Upload
    MAX_UPLOAD_SIZE: int = Field(default=10 * 1024 * 1024)
    ALLOWED_EXTENSIONS: list[str] = Field(
        default=["pdf", "jpg", "jpeg", "png", "tiff", "tif"]
    )
    UPLOAD_TEMP_DIR: str = Field(default="/tmp/uploads")

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = Field(default=True)
    RATE_LIMIT_PER_MINUTE: int = Field(default=60)
    RATE_LIMIT_PER_HOUR: int = Field(default=1000)

    # Subscription Plans
    FREE_PLAN_MONTHLY_LIMIT: int = Field(default=10)
    BASIC_PLAN_MONTHLY_LIMIT: int = Field(default=100)
    PRO_PLAN_MONTHLY_LIMIT: int = Field(default=1000)
    ENTERPRISE_PLAN_MONTHLY_LIMIT: int = Field(default=-1)

    # Email (optional for notifications)
    SMTP_HOST: Optional[str] = Field(default=None)
    SMTP_PORT: int = Field(default=587)
    SMTP_USER: Optional[str] = Field(default=None)
    SMTP_PASSWORD: Optional[str] = Field(default=None)
    SMTP_FROM_EMAIL: Optional[str] = Field(default=None)
    SMTP_USE_TLS: bool = Field(default=True)

    # Logging
    LOG_LEVEL: str = Field(default="INFO")
    LOG_FORMAT: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Sentry (optional)
    SENTRY_DSN: Optional[str] = Field(default=None)
    SENTRY_ENVIRONMENT: Optional[str] = Field(default=None)
    SENTRY_TRACES_SAMPLE_RATE: float = Field(default=1.0)

    @field_validator('BACKEND_CORS_ORIGINS', mode='before')
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(',') if origin.strip()]
        return v

    @field_validator('ALLOWED_EXTENSIONS', mode='before')
    @classmethod
    def parse_allowed_extensions(cls, v):
        if isinstance(v, str):
            return [ext.strip().lower() for ext in v.split(',') if ext.strip()]
        return v

    @field_validator('CELERY_ACCEPT_CONTENT', mode='before')
    @classmethod
    def parse_celery_accept_content(cls, v):
        if isinstance(v, str):
            return [content.strip() for content in v.split(',') if content.strip()]
        return v

    @field_validator('JWT_SECRET_KEY')
    @classmethod
    def validate_jwt_secret(cls, v):
        if len(v) < 32:
            raise ValueError('JWT_SECRET_KEY must be at least 32 characters long')
        return v

    @field_validator('STORAGE_PROVIDER')
    @classmethod
    def validate_storage_provider(cls, v):
        allowed_providers = ['s3', 'gcs', 'local']
        if v.lower() not in allowed_providers:
            raise ValueError(f'STORAGE_PROVIDER must be one of {allowed_providers}')
        return v.lower()

    @property
    def database_url_sync(self) -> str:
        return self.DATABASE_URL.replace('postgresql+asyncpg://', 'postgresql://')

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == 'production'

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT.lower() == 'development'


settings = Settings()