"""Limite de requisições por IP nas rotas que custam dinheiro.

**Por que existe.** `/auditar` é público e sem autenticação, e cada chamada
dispara até uma dezena de chamadas ao Azure OpenAI, quatro em paralelo, ~20s
cada. Sem limite, um laço de `curl` faz duas coisas ao mesmo tempo: queima a
cota do modelo e satura `maxReplicas: 3`, tirando o site do ar. Não exige
habilidade nenhuma, e é o dano que dá para causar hoje.

**Escrito à mão, e não com uma biblioteca.** Não por purismo: é uma janela
deslizante em cima de um `deque`, e a dependência traria middleware,
integração com Redis e configuração que este serviço não usa. O que segue cabe
numa tela e não tem parte que eu não saiba explicar.

**Não é defesa contra DDoS distribuído.** Contra isso só WAF na borda, que
custa mais que a assinatura inteira. Isto resolve o caso real de um único
cliente em laço, que é o que está exposto.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

# Uma auditoria leva ~2 minutos e ninguém legítimo faz dez seguidas. O teto é
# folgado de propósito: limite que atrapalha o uso honesto é trocar um problema
# por outro, e o objetivo aqui é o laço automatizado, não a pessoa curiosa.
JANELA_SEGUNDOS = 600
MAX_NA_JANELA = 15

# Teto de IPs rastreados. Sem ele o próprio dicionário vira o alvo: basta
# variar o IP de origem para crescer memória sem limite.
MAX_IPS = 10_000


class JanelaDeslizante:
    """Conta requisições por chave numa janela de tempo móvel.

    Janela deslizante e não balde de fichas porque o comportamento é mais fácil
    de explicar a quem toma um 429: "quinze a cada dez minutos" é uma frase; a
    taxa de recarga de um balde não é.
    """

    def __init__(self, janela: int = JANELA_SEGUNDOS, maximo: int = MAX_NA_JANELA) -> None:
        self.janela = janela
        self.maximo = maximo
        self._marcas: dict[str, deque[float]] = defaultdict(deque)
        # As rotas síncronas do FastAPI rodam num pool de threads, então este
        # estado é mesmo compartilhado entre threads.
        self._trava = threading.Lock()

    def _expirar(self, marcas: deque[float], agora: float) -> None:
        limite = agora - self.janela
        while marcas and marcas[0] < limite:
            marcas.popleft()

    def _coletar(self, agora: float) -> None:
        """Descarta chaves cuja janela venceu inteira."""
        vencidas = [k for k, m in self._marcas.items() if not m or m[-1] < agora - self.janela]
        for k in vencidas:
            del self._marcas[k]

    def permitir(self, chave: str) -> tuple[bool, int]:
        """Registra uma tentativa. Devolve (permitida, segundos até liberar)."""
        agora = time.monotonic()
        with self._trava:
            if len(self._marcas) > MAX_IPS:
                self._coletar(agora)
                # Ainda cheio depois da coleta: o serviço está sob abuso amplo.
                # Recusar é melhor que crescer memória até o container morrer.
                if len(self._marcas) > MAX_IPS:
                    return False, self.janela

            marcas = self._marcas[chave]
            self._expirar(marcas, agora)

            if len(marcas) >= self.maximo:
                espera = int(marcas[0] + self.janela - agora) + 1
                return False, max(espera, 1)

            marcas.append(agora)
            return True, 0


_limitador = JanelaDeslizante()


def ip_do_cliente(request: Request) -> str:
    """IP de origem, atrás do proxy do Container Apps.

    **O último valor de `X-Forwarded-For`, não o primeiro.** O cabeçalho é uma
    lista que cada proxy no caminho vai acrescentando à direita. Um cliente
    pode mandar o seu próprio e o ingress acrescenta o IP real depois dele, o
    que torna a última posição a única que o atacante não escolhe. Ler a
    primeira seria ler exatamente o campo que ele controla, e o limite viraria
    decoração: bastaria variar o cabeçalho a cada requisição.
    """
    encaminhado = request.headers.get("x-forwarded-for", "")
    if encaminhado:
        partes = [p.strip() for p in encaminhado.split(",") if p.strip()]
        if partes:
            return partes[-1]
    return request.client.host if request.client else "desconhecido"


def limitar(request: Request) -> None:
    """Dependência das rotas caras.

    Aplicada rota a rota, e não como middleware global, por um motivo concreto:
    middleware pegaria `/health/*`, e as probes do Container Apps batem lá a
    cada poucos segundos. Um 429 numa probe reinicia o container — a defesa
    derrubaria o serviço que ela protege.
    """
    permitida, espera = _limitador.permitir(ip_do_cliente(request))
    if permitida:
        return
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=(
            f"muitas análises em pouco tempo: o limite é {MAX_NA_JANELA} "
            f"a cada {JANELA_SEGUNDOS // 60} minutos. Tente de novo em {espera}s."
        ),
        headers={"Retry-After": str(espera)},
    )
