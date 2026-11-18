# Caddy with the Route 53 DNS provider, so certificates can be issued for hosts that are not
# reachable from the internet (ACME DNS-01 challenge instead of HTTP-01 / TLS-ALPN-01).
# Build for the host's own architecture, for example on an arm64 host:
#   docker build -t devlake-caddy:2.11.9-route53-1.6.3 devops/deployment/caddy
ARG CADDY_VERSION=2.11.9

FROM caddy:${CADDY_VERSION}-builder AS builder
ARG CADDY_DNS_ROUTE53_VERSION=v1.6.3
RUN xcaddy build --with github.com/caddy-dns/route53@${CADDY_DNS_ROUTE53_VERSION}

FROM caddy:${CADDY_VERSION}
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
