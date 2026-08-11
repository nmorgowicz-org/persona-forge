# Security Policy

## Supported Versions

Security fixes are applied to the latest release and the `main` branch. Development branches
and old container tags are not independently supported. Production deployments should use an
immutable image digest or SHA tag.

## Reporting a Vulnerability

Do not open a public issue for a suspected vulnerability or include credentials, private
voice recordings, generated speech, model cache contents, or deployment details in a public
report.

Use one of these private channels:

- Open a [private GitHub security advisory](https://github.com/nmorgowicz-org/persona-forge/security/advisories/new).
- Email `nick@morgowicz.com` with the subject `persona-forge security report`.

Include the affected commit or image digest, reproduction steps, expected impact, and any
known mitigations. Redact Hugging Face tokens and other credentials.

## Scope

Reports about this repository's API, container packaging, dependency configuration, model or
voice data exposure, authentication handling, generated artifacts, and deployment guidance
are in scope. Vulnerabilities in upstream Qwen, OpenVINO, PyTorch, or Hugging Face components
should also be reported to their maintainers; report them here when this project introduces
or materially worsens the exposure.

The service does not provide authentication or TLS. Do not publish port 8318 to an untrusted
network without an authenticated reverse proxy and appropriate transport security.
