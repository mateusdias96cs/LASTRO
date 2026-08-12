"""Críticos falsos, para provar que o conjunto de casos discrimina.

Mesmo papel dos duplos da camada 3, e mesma razão: sem eles, a avaliação só
seria exercitada junto com o crítico real, e um caso que passasse não diria se
o mérito é do crítico ou de o caso ser fácil demais.

Aqui os duplos são **funções**, não classes. `criticar` é uma função pura, não
método de um Protocol — imitar a forma da camada 3 criaria uma classe com um
método só para parecer simétrica.

Os dois duplos são os extremos do eixo que importa nesta camada:

* `critico_cego` é a ausência da trava. Aprova tudo, inclusive citação
  inventada e controle trocado. Existe para responder "e se não houvesse
  camada 4?" com um número em vez de com uma suposição;
* `critico_paranoico` é a trava que não confia em nada. Rebaixa tudo, inclusive
  a saída impecável. Existe porque um crítico que sempre rebaixa passaria em
  qualquer conjunto que só verificasse "pegou o erro?" — ele pega todos, por
  acidente. É o duplo que obriga o conjunto a ter casos que devem APROVAR.

Nenhum dos dois usa LLM, como o crítico real. A trava é determinística
justamente porque quem envia o arquivo é quem poderia querer enganá-la.
"""

from __future__ import annotations

from conformidade.agents.analysis.contracts import AchadoAnalisado, Confianca, EntradaAnalise
from conformidade.agents.critic.contracts import (
    AchadoCriticado,
    Objecao,
    Reparo,
    VereditoCritico,
)


def critico_cego(entrada: EntradaAnalise, saida: AchadoAnalisado) -> AchadoCriticado:
    """Aprova tudo, sem olhar.

    Mede o custo de não ter a camada 4: cada caso que ele "passa" é uma
    afirmação sem respaldo que chegaria ao usuário com aparência de verificada.
    """
    return AchadoCriticado(
        control_id=entrada.control_id,
        veredito=VereditoCritico.APROVADO,
        analisado=saida,
    )


def critico_paranoico(entrada: EntradaAnalise, saida: AchadoAnalisado) -> AchadoCriticado:
    """Rebaixa tudo, mesmo quando não há o que reparar.

    O contrato proíbe reparo sem objeção, então este duplo precisa **inventar**
    uma — e inventa com nome próprio (`desconfianca_sistematica`), que nenhum
    verificador real emite. Assim o caso consegue distinguir "rebaixou pelo
    motivo certo" de "rebaixou por rebaixar", que é exatamente a diferença que
    um conjunto fraco não veria.

    O contrato também proíbe `analisado_original` idêntico ao corrigido. Quando
    a saída já está no piso — sem citação e com confiança baixa — não há o que
    rebaixar, e o campo fica de fora em vez de forçar uma diferença artificial.
    """
    rebaixado = saida.model_copy(update={"citacoes": [], "confianca": Confianca.BAIXA})
    objecao = Objecao(
        verificador="desconfianca_sistematica",
        detalhe=(
            "duplo paranoico: rebaixa toda saída por princípio, sem ter "
            "encontrado problema real nesta"
        ),
        reparo=Reparo.CONFIANCA_REBAIXADA,
    )
    return AchadoCriticado(
        control_id=entrada.control_id,
        veredito=VereditoCritico.REBAIXADO,
        analisado=rebaixado,
        analisado_original=saida if rebaixado != saida else None,
        objecoes=(objecao,),
    )
