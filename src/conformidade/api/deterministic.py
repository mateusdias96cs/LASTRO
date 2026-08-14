"""Rotas do agente determinístico."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from conformidade.agents.deterministic import (
    ControlDescriptor,
    DeterministicReport,
    analyze,
    list_controls,
)
from conformidade.agents.deterministic.models import ArtifactKind

router = APIRouter(prefix="/api/v1", tags=["determinístico"])

# O arquivo é lido inteiro em memória para o parse. O teto evita que um upload
# grande derrube o processo — configuração real de um artefato desses tem
# alguns KB; 2 MiB é folga generosa.
MAX_UPLOAD_BYTES = 2 * 1024 * 1024


@router.get("/controls", response_model=list[ControlDescriptor])
def get_controls() -> list[ControlDescriptor]:
    """Catálogo de controles avaliados.

    É a lista que o corpus do RAG precisa cobrir: todo `control_id` emitido por
    um achado aparece aqui.
    """
    return list_controls()


@router.post("/analyze", response_model=DeterministicReport)
async def post_analyze(file: Annotated[UploadFile, File()]) -> DeterministicReport:
    """Recebe o arquivo, devolve a estrutura parseada junto com os achados."""
    # `MAX + 1` e não o arquivo inteiro: basta um byte além do teto para saber
    # que estourou, e o excedente nunca chega à memória.
    content = await file.read(MAX_UPLOAD_BYTES + 1)

    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"arquivo acima do limite de {MAX_UPLOAD_BYTES} bytes",
        )
    if not content.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="arquivo vazio")

    report = analyze(content, file.filename or "upload")

    if report.artifact.kind == ArtifactKind.UNKNOWN:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "formato não reconhecido; esperado Dockerfile, docker-compose "
                "ou manifesto Kubernetes"
            ),
        )

    return report
