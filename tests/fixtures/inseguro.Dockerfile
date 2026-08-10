# syntax=docker/dockerfile:1.9
# escape=\
# Fixture deliberadamente insegura. Cada bloco existe para disparar um controle
# específico — não copie nada daqui.
FROM ubuntu AS base
MAINTAINER alguem@example.com

# Comentário no meio de uma continuação: o parser precisa descartá-lo sem
# quebrar a instrução.
RUN apt-get update && \
    # este comentário está dentro da continuação
    apt-get install -y curl python3 && \
    apt-get upgrade -y

RUN curl -fsSL https://get.example.com/install.sh | sh
RUN sudo chmod -R 777 /opt/app

ENV DATABASE_PASSWORD=SenhaSuperSecreta123
ARG AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
ENV LOG_LEVEL=debug

ADD ./config.json /etc/app/config.json
ADD https://example.com/payload.bin /opt/payload.bin
COPY . /app

EXPOSE 22 8080/tcp

FROM base
# Stage final sem USER e com ENTRYPOINT em forma shell.
RUN <<EOF
echo "heredoc: estas linhas nao podem virar instrucoes"
chmod 777 /tmp/coisa
EOF

ENTRYPOINT /app/start.sh
