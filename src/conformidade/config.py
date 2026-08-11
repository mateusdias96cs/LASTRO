"""Configuração da aplicação.

Toda configuração vem de variáveis de ambiente (12-factor). Isso mantém a
paridade entre o container local e o Azure, onde os valores chegam como
env vars injetadas por Container Apps / AKS, App Configuration ou secrets do
Key Vault montados via CSI driver.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CONFORMIDADE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "conformidade"
    environment: Literal["local", "dev", "staging", "prod"] = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    host: str = "0.0.0.0"  # noqa: S104 - obrigatório dentro do container
    # Container Apps e App Service injetam PORT/WEBSITES_PORT; ler do ambiente
    # evita ter que reconstruir a imagem na migração.
    port: int = Field(default=8000, validation_alias="PORT")

    # Onde o corpus indexado vive. Padrão relativo funciona no repositório; na
    # imagem é absoluto, porque o processo não roda a partir da raiz do projeto.
    corpus_dir: str = "corpus"

    # Preenchidos na migração para Azure. Vazios = recursos ainda não conectados.
    azure_client_id: str = ""  # user-assigned managed identity
    key_vault_uri: str = ""
    app_config_endpoint: str = ""
    applicationinsights_connection_string: str = Field(
        default="", validation_alias="APPLICATIONINSIGHTS_CONNECTION_STRING"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
