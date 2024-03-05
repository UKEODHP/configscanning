# syntax=docker/dockerfile:1
FROM python:3.11-slim-bullseye

RUN rm -f /etc/apt/apt.conf.d/docker-clean; \
    echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update -y && apt-get upgrade -y && apt-get install -y ca-certificates curl gnupg git \

WORKDIR /service-manager-config-scanner
ADD LICENSE.txt requirements.txt ./
ADD configscanning ./configscanning/
ADD pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/pip pip3 install -r requirements.txt .

CMD python -m configscanning.repoupdater $1 $2
