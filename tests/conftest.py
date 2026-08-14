"""Fixtures compartilhadas.

O limitador de requisições é um objeto de processo, o que é correto em
produção e traiçoeiro em teste: sem zerar entre um teste e outro, o primeiro
que esgotar a janela faz o próximo receber 429 e falhar por um motivo que não
tem nada a ver com o que ele testa. Já aconteceu de a ordem salvar; ordem não
é garantia.
"""

import pytest


@pytest.fixture(autouse=True)
def _zerar_limitador():
    from conformidade.api.limite import _limitador

    _limitador._marcas.clear()
    yield
    _limitador._marcas.clear()
