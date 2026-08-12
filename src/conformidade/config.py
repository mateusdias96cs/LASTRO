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

    # Azure OpenAI (camada 3). O Bicep injeta os dois no Container App; sem
    # chave, porque a autenticação é por identidade gerenciada.
    azure_openai_endpoint: str = Field(default="", validation_alias="AZURE_OPENAI_ENDPOINT")
    azure_openai_deployment: str = Field(default="", validation_alias="AZURE_OPENAI_DEPLOYMENT")
    # Cache das respostas da camada 3, com chave derivada do conteúdo.
    analise_cache_dir: str = ".cache-analise"

    # Quantos achados a camada 3 analisa em paralelo.
    #
    # O modelo de raciocínio leva ~20s por achado, então nove achados em
    # sequência levam três minutos — mais que qualquer timeout razoável de
    # navegador. Paralelizar é o que traz isso para a casa dos segundos.
    #
    # O teto precisa caber na cota do deployment: acima dela o serviço devolve
    # 429, o SDK tenta de novo com espera exponencial, e o tempo total fica
    # PIOR que o sequencial — foi o que aconteceu numa medição real, 4m56s
    # contra 2m57s da rodada anterior. Subir isto sem subir a cota junto
    # piora.
    analise_paralela: int = 4

    # Origens autorizadas a chamar a API pelo navegador, separadas por vírgula.
    #
    # Sem isto o frontend não funciona, e falha do jeito mais confuso possível:
    # o navegador bloqueia a resposta e o erro chega como falha de rede
    # genérica, não como "CORS negou". O backend precisa dizer explicitamente
    # de quais origens aceita chamada.
    #
    # Vazio libera `localhost` para desenvolvimento e nada mais — produção
    # precisa declarar a origem do Container App do frontend.
    cors_origins: str = ""

    @property
    def origens_permitidas(self) -> list[str]:
        declaradas = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        if declaradas:
            return declaradas
        return ["http://localhost:3000", "http://127.0.0.1:3000"]

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
