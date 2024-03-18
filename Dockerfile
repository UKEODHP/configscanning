# syntax=docker/dockerfile:1
FROM python:3.11-slim-bullseye

RUN rm -f /etc/apt/apt.conf.d/docker-clean; \
    echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update \
    && apt-get install -y apt-transport-https ca-certificates curl gnupg \
    && mkdir -p -m 755 /etc/apt/keyrings \
    && curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.29/deb/Release.key | gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg \
    && echo 'deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.29/deb/ /' | tee /etc/apt/sources.list.d/kubernetes.list \
    && apt-get update \
    && apt-get install -y kubectl

WORKDIR /service-manager-config-scanner
ADD LICENSE.txt requirements.txt ./
ADD configscanning ./configscanning/
ADD pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/pip pip3 install -r requirements.txt .

CMD python -m configscanning.repoupdater $1 $2
