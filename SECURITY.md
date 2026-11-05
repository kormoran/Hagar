# Security Policy

## Supported versions

Security fixes target the latest release line. At the time of writing that
is **0.3.x**. Older tags may be useful for reproduction, but they are not
maintained.

## Reporting a vulnerability

Please **do not open a public issue** for a security problem.

Use GitHub's private vulnerability reporting:

<https://github.com/kormoran/Hagar/security/advisories/new>

Include:

- the affected version or commit;
- a minimal reproduction;
- the impact you observed;
- any relevant configuration, with secrets removed.

You should receive an acknowledgement within a few days. There is no
bug bounty.

## Threat model and known boundaries

Hagar constrains an untrusted language model; it is not an operating
system security boundary.

- The filesystem sandbox is path-based. Symlinks are invisible to it, but
  hard links, mounts, junctions and TOCTOU races are the user's
  responsibility. See `Docs/it/ARCHITECTURE.md` §6.1.
- The sandbox does not isolate the process. For a strong boundary use a
  dedicated volume, a separate user, a mount namespace or a container.
- The Vault is plain Markdown and is not encrypted. It can contain the
  full conversation, decisions and summaries; protect it like source
  code or notes.
- The audit log may contain file contents and tool results. It is not
  redacted beyond `audit.max_field_chars`; treat it as sensitive.
- API keys are read from environment variables and are not written to
  configuration or logs. Do not put secrets in `hagar.yaml`.
- MCP and OAuth tokens are stored in local cache files. Protect those
  files and prefer the narrowest scopes.
- The model can be induced to misuse a legitimate tool. Policy rules,
  confirmations and audit are the controls; review them before granting
  write, network or shell capabilities.

## Local model servers

Ollama and (forthcoming) LM Studio are local services. Bind them to loopback unless
you intentionally want LAN access, and do not expose them to the
internet. Hagar does not add authentication to those servers.

## Out of scope

- a local attacker who can already read or write the Hagar workspace,
  the Vault or the Python environment;
- denial of service caused by huge local models, Vaults or conversation
  histories;
- vulnerabilities in third-party models, model servers or MCP servers.
