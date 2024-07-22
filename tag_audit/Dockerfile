FROM alpine:3.20.1

# ARG datahub_version=0.9.6.4
# ARG action_version=0.0.11

ARG datahub_version=0.12.1.1
ARG action_version=0.0.15

COPY .  /tag_audit


RUN apk update \
    && apk upgrade  \
    && apk add gcc g++ linux-headers cyrus-sasl cyrus-sasl-dev libsasl musl-dev openssl-dev make krb5 krb5-dev cyrus-sasl-gssapiv2 libgsasl-dev \
    && apk add librdkafka librdkafka-dev python3 py3-pip python3-dev \
    && addgroup --system datahub && adduser --system datahub --ingroup datahub \
    && mkdir /tmp/datahub \
    && chown -R datahub /tmp/datahub


RUN python3 -m pip install --break-system-packages --upgrade pip wheel setuptools \
    && python3 -m pip install --break-system-packages --upgrade acryl-datahub==${datahub_version} \
    && python3 -m pip install --break-system-packages --upgrade acryl-datahub-actions==${action_version} \
    && python3 -m pip install --break-system-packages --upgrade gql[all] \
    && cd /tag_audit \
    && pip install --break-system-packages -e .


USER datahub

ENTRYPOINT ["datahub", "--debug", "actions", "run", "-c"]