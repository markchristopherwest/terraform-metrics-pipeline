# Terraform runner: applies the module every INTERVAL_SECONDS.
# The module itself is bind-mounted at /terraform (real or mock); providers are
# cached on a volume so restarts do not re-download them.
FROM hashicorp/terraform:1.13

RUN apk add --no-cache bash coreutils curl jq util-linux tzdata

ENV TF_IN_AUTOMATION=1 \
    TF_INPUT=0 \
    TF_PLUGIN_CACHE_DIR=/var/cache/terraform-plugins \
    TF_DIR=/terraform \
    REPORTS_DIR=/reports \
    STATE_DIR=/var/lib/prisma-reports \
    INTERVAL_SECONDS=300 \
    TF_PARALLELISM=3

RUN mkdir -p /var/cache/terraform-plugins /var/lib/prisma-reports /reports

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

WORKDIR /terraform
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
