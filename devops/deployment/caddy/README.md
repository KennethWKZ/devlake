# Caddy HTTPS front door for DevLake

Serves DevLake's config-ui (and Grafana under `/grafana`) over HTTPS, and optionally an
OpenTelemetry Collector's OTLP/HTTP endpoint, from the DevLake host itself. It replaces a
load balancer when the host should be reachable only from trusted networks (an office or
a VPN), so the usual Let's Encrypt HTTP check from the internet cannot reach it.
Certificates are issued with the ACME DNS-01 challenge through Route 53 instead.

## What you need

- A Route 53 hosted zone for the names you use, and A records for them pointing at the
  host's address (use an Elastic IP: an auto-assigned public IP changes on stop/start).
- The host's security group allows TCP 443 only from your trusted networks. Port 80 is
  not needed.
- DevLake's config-ui published on the host (default `127.0.0.1:4000` from Caddy's view)
  and, if used, the collector's OTLP/HTTP receiver (default `127.0.0.1:4319`). Close those
  ports to everyone else in the security group.
- An IAM role the DNS provider can assume (below).

## IAM: a role only this host can use

Keep the Route 53 permission off the instance role itself: other hosts may share it.
Create a role (for example `devlake-caddy-acme`) that trusts the instance role, limited to
this one instance, and that can write only `_acme-challenge` TXT records in one zone.

Trust policy (replace the account, instance role and instance id):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "AWS": "arn:aws:iam::123456789012:role/<instance-role>" },
      "Action": "sts:AssumeRole",
      "Condition": {
        "ArnEquals": { "ec2:SourceInstanceARN": "arn:aws:ec2:<region>:123456789012:instance/<instance-id>" }
      }
    }
  ]
}
```

Permissions (replace the zone id):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "route53:ListResourceRecordSets",
      "Resource": "arn:aws:route53:::hostedzone/<zone-id>"
    },
    {
      "Effect": "Allow",
      "Action": "route53:GetChange",
      "Resource": "arn:aws:route53:::change/*"
    },
    {
      "Effect": "Allow",
      "Action": "route53:ChangeResourceRecordSets",
      "Resource": "arn:aws:route53:::hostedzone/<zone-id>",
      "Condition": {
        "ForAllValues:StringEquals": { "route53:ChangeResourceRecordSetsRecordTypes": "TXT" },
        "ForAllValues:StringLike": { "route53:ChangeResourceRecordSetsNormalizedRecordNames": "_acme-challenge.*" }
      }
    }
  ]
}
```

Within one AWS account the trust policy naming the instance role is enough: the shared
instance role needs no new permission.

## Run

```sh
cd devops/deployment/caddy
cp .env.example .env              # names, zone id, profile
cp aws-config.example aws-config  # role ARN
docker build -t devlake-caddy:2.11.9-route53-1.6.3 .
docker compose up -d
docker compose logs -f caddy      # wait for "certificate obtained successfully" per name
```

Remove a file from `sites/` (or don't mount it) for a site you don't serve.

## Check

```sh
curl -sI https://<DEVLAKE_UI_HOST>/grafana/login          # 200
curl -s -o /dev/null -w '%{http_code}\n' https://<OTEL_HOST>/              # 404
curl -s -o /dev/null -w '%{http_code}\n' -X POST https://<OTEL_HOST>/v1/logs  # 401 without a token
```

## Notes

- Certificates and the ACME account live in the `caddy-data` volume; keep it.
- Caddy renews certificates itself about 30 days before they expire.
- Caddy's admin API listens on `127.0.0.1:2019` on the host.
- Rebuild the image to update Caddy or the DNS provider; pin both versions.
