from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5433/db_catering"
    app_env: str = "development"
    log_level: str = "INFO"

    # Service Discovery (Consul). Vacío = no se registra (desarrollo local y tests).
    servicio_nombre: str = "ms-catering"
    servicio_puerto: int = 8000
    consul_url: str = ""

    # Broker (RabbitMQ). Vacío = no arrancan ni el relay del outbox ni el consumidor.
    rabbitmq_url: str = ""
    rabbitmq_exchange: str = "nurtricenter.events"
    rabbitmq_cola: str = "ms-catering.eventos"
    outbox_intervalo_segundos: float = 2.0

    # Seguridad: el token lo emite el api-gateway; aquí se valida con el mismo secreto e issuer.
    auth_habilitada: bool = False
    jwt_secret: str = "nurtricenter-secreto-compartido-2026"
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "nurtricenter-gateway"


settings = Settings()
