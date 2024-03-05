# syntax=docker/dockerfile:1
FROM python:3.11-slim-bullseye

RUN rm -f /etc/apt/apt.conf.d/docker-clean; \
    echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update -y && apt-get upgrade -y && apt-get install -y ca-certificates curl gnupg git \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg | gpg --dearmor -o /etc/apt/keyrings/kubernetes-archive-keyring.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/kubernetes-archive-keyring.gpg] https://apt.kubernetes.io/ kubernetes-xenial main" | tee /etc/apt/sources.list.d/kubernetes.list \
#    && apt-get update -y && apt-get install -y kubectl \
#    && snap install kubectl --classic \
#    && curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" \
#    && sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl
    && apt-get install -y apt-transport-https \
    && curl -s https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key add - \
    && echo "deb https://apt.kubernetes.io/ kubernetes-xenial main" | tee /etc/apt/sources.list.d/kubernetes.list \
    && apt-get update \
    && apt-get install -y kubectl


WORKDIR /service-manager-config-scanner
ADD LICENSE.txt requirements.txt ./
ADD configscanning ./configscanning/
ADD pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/pip pip3 install -r requirements.txt .

CMD python -m configscanning.repoupdater $1 $2
