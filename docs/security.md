# Security model

The service is designed for hostile/untrusted source material and bounded
automation:

- HTTP fetch accepts only credential-free HTTP(S), allowlisted hosts and bounded
  redirects/retries/body size; DNS is resolved before every request and every
  resolved address must be global/non-special;
- 4xx responses are non-retryable source errors, while 5xx responses are
  bounded retryable upstream errors and are never stored as artifacts;
- private, loopback, link-local, reserved and multicast IP literals are rejected;
- local fixture/import paths must stay under configured roots;
- raw artifact writes are atomic and storage keys cannot escape the root;
- AI document data is isolated from trusted extraction instructions;
- no `eval`, arbitrary code execution, shell tool, model-controlled URL fetch or
  Core activation operation exists;
- role boundaries separate reader, editor and admin mutation paths;
- secrets are environment settings and redacted from structured logs;
- request and pipeline correlation IDs support incident tracing.

The local `X-Role` mechanism is a replaceable boundary. Production deployment
must put a real authenticated gateway/identity provider in front of the service.
