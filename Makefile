IMAGE ?= conformidade/api
TAG   ?= local

.PHONY: build run up down logs test lint lock sh portao ingerir indexar baseline

build:                ## Constrói a imagem
	docker build -t $(IMAGE):$(TAG) .

run: build            ## Roda o container isolado
	docker run --rm -p 8000:8000 --env-file .env.example $(IMAGE):$(TAG)

up:                   ## Sobe via compose
	docker compose up --build

down:
	docker compose down -v

logs:
	docker compose logs -f api

sh:                   ## Shell dentro da imagem
	docker run --rm -it $(IMAGE):$(TAG) shell

test:
	uv run --extra dev pytest -q

lint:
	uv run --extra dev ruff check . && uv run --extra dev ruff format --check .

lock:                 ## Regenera o uv.lock (rode após mexer no pyproject)
	uv lock

portao:               ## Portão de qualidade — o mesmo que roda no CI
	uv run python scripts/portao.py

baseline:             ## Regrava a linha de base após uma melhoria comprovada
	uv run python scripts/portao.py --sem-lint --sem-testes --gravar-baseline

ingerir:              ## Reingere o corpus a partir do cache local
	uv run python scripts/ingerir.py

indexar:              ## Reindexa (precisa do extra `embed`, ~270s de CPU)
	uv run --extra embed python scripts/indexar.py
