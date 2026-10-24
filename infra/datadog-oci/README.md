# Datadog OCI integration

This is an independent Terraform root for the `thomasrosenblatt` OCI tenancy
and the `ThomasDogFooding` Datadog organization on `datadoghq.com`.
Run Terraform from this directory; the parent `infra/` directory manages the
application server with a separate state and provider version.

## Configuration

- OCI authentication: existing `DEFAULT` profile in `~/.oci/config`.
- Home region: `eu-paris-1`; it was the only subscribed region on 2026-10-24.
- Upstream release: `datadog-integration-v1.2.7`, pinned to commit
  `868f6db4251c1519e34c7c0f7505d9ef8d06c054`.
- Log collection, event collection, and regional vault support are enabled.
- The upstream default also enables metric/resource collection. `logs_only`
  is deliberately omitted because enabling it disables event collection.
- The upstream module discovers subscribed regions automatically. Review the
  plan after subscribing to another region, as it may add infrastructure there.

## Credentials and state

Supply `TF_VAR_datadog_api_key` and `TF_VAR_datadog_app_key` through the process
environment. The production `deploy/.env` contains the existing credentials;
never copy their values into Terraform source or commit them.

Terraform state and saved plans contain secrets, including the generated OCI
integration private key and Datadog API key. Keep this directory private,
preserve the state for future updates, and back it up to access-controlled,
encrypted storage. State, plans, logs, local overrides, and vendored sources
are excluded by the local `.gitignore`.

## Operations

Use Terraform 1.5 or later and OCI provider 8.x. The module also invokes the
OCI CLI, Bash, curl, jq, and timeout. Ensure the working Terraform executable
is on `PATH`, including for subprocesses invoked by the module.

Run `terraform init`, `terraform validate`, and `terraform plan -out=deployment.tfplan`
before applying the saved plan. Do not apply from the parent directory.

The upstream module intentionally rotates its OCI signing key on every apply
using a timestamp trigger. A subsequent plan therefore does **not** converge
to zero changes. The post-install read-only plan also reported Oracle-managed
tag/email normalization and deferred reads. The integration user's group
membership was checked directly in OCI and is present, despite Terraform
proposing to add it again. Review future plans carefully; do not repeatedly
apply them merely to seek a zero-change result.

The initial preparation uses ignored local module copies downloaded through
the authenticated GitHub CLI, with an ignored `override.tf` selecting them.
Only nested VCN module source locations are changed to local paths. The
committed module source remains pinned to the upstream release above.

## Verification

After applying, verify the tenancy in Datadog's OCI integration tile, the
forwarding functions and service connectors in OCI, receipt of OCI Audit logs
in Datadog, and Cloud SIEM analysis of those logs. An absence of security
signals alone does not establish a problem: a detection rule must match.

OCI resources, telemetry ingestion, and Cloud SIEM analysis may incur usage
charges. Terraform does not provide a billing estimate.

## Deployment record — 2026-10-24

- Terraform 1.17.0 initialization and validation passed.
- The initial plan and apply completed: 41 added, 0 changed, 0 destroyed.
- Datadog tenancy registration succeeded for `thomasrosenblatt` in Paris.
- Both `dd-logs-forwarder` and `dd-metrics-forwarder` are ACTIVE.
- Datadog confirms Audit log collection, event collection, metric collection,
  and resource collection are enabled.
- The seven built-in OCI Cloud SIEM rules are enabled, and the existing
  `all ingested logs` security filter is active.
- All three Datadog-managed service connectors (Audit logs, metrics, and
  events) are ACTIVE. The tenancy-root event rule is enabled and ACTIVE.
- End-to-end ingestion verified: `source:oci.audit` returns real OCI logs,
  and `source:oci.audit datadog.cloud_siem:true` returns those logs as selected
  for Cloud SIEM analysis. First verified sample timestamps: approximately
  2026-10-24 22:09:47 Europe/Paris.
- Datadog automatically installed and enabled its official `OCI Audit Logs`
  pipeline. Subsequent records match
  `source:oci.audit datadog.cloud_siem:true @evt.name:*`, with normalized event
  names such as `UpdateServiceConnector` and `GetNamespace` (verified samples
  around 22:11 Europe/Paris). This confirms the fields used by the detection
  rules are being populated.
- Post-apply plan was read only and was not applied; see the rotation behavior
  above.

References:

- https://docs.datadoghq.com/integrations/oracle-cloud-infrastructure/
- https://docs.datadoghq.com/security/cloud_siem/guide/oci-config-guide-for-cloud-siem/

Open the verified log query:
https://app.datadoghq.com/logs?query=source%3Aoci.audit%20datadog.cloud_siem%3Atrue
