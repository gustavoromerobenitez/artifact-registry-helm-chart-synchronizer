FROM python:3-alpine

ARG GCLOUD_SDK_CLI_VERSION=467.0.0

WORKDIR /copa

COPY app/helm-charts-sync.py /app/helm-charts-sync.py
COPY app/requirements.txt /app/requirements.txt

ENV PATH=/usr/local/google-cloud-sdk/bin:$PATH

RUN apk update && \
    apk upgrade --available && \
    apk add --no-cache --upgrade curl bash openssl && \
    addgroup -g 1000 python && \
    adduser -u 1000 -D -G python python -h /app && \
    #
    # Install Helm
    curl -fsSL -o get_helm.sh https://raw.githubusercontent.com/helm/helm/master/scripts/get-helm-3 && \
    chmod +x get_helm.sh && \
    bash get_helm.sh && \
    rm -f get_helm.sh && \
    #
    # Install GCloud tool
    curl -sL -o "google-cloud-cli-${GCLOUD_SDK_CLI_VERSION}-linux-x86_64.tar.gz" "https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-cli-${GCLOUD_SDK_CLI_VERSION}-linux-x86_64.tar.gz" && \
    tar -C /usr/local -xf "google-cloud-cli-${GCLOUD_SDK_CLI_VERSION}-linux-x86_64.tar.gz" &>/dev/null && \
    /usr/local/google-cloud-sdk/install.sh --rc-path /etc/bashrc --override-components core gke-gcloud-auth-plugin --quiet && \
    rm "google-cloud-cli-${GCLOUD_SDK_CLI_VERSION}-linux-x86_64.tar.gz" && \
    rm -f /usr/local/google-cloud-sdk/install.* /usr/local/google-cloud-sdk/.install/.backup/bin/anthoscli /usr/local/google-cloud-sdk/bin/anthoscli && \
    /usr/local/google-cloud-sdk/bin/gcloud config set core/custom_ca_certs_file /etc/ssl/certs/ca-certificates.crt && \
    /usr/local/google-cloud-sdk/bin/gcloud config set disable_usage_reporting true && \
    #
    apk del --purge curl bash openssl

USER python

WORKDIR /app

ENV PATH=/app:/usr/local/google-cloud-sdk/bin:$PATH

# Upgrade pip to prevent security vulnerabilities
RUN python -m pip install --upgrade pip && \
    # Install app pre-requisites
    python -m pip install -r /app/requirements.txt

ENTRYPOINT ["python", "/app/helm-charts-sync.py"]
