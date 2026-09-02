# Security

## Reporting a vulnerability

Please report security issues privately through
[GitHub's private vulnerability reporting](https://github.com/BenvinD/claimlens/security/advisories/new)
rather than in a public issue. Include reproduction steps and the affected
version or commit. Expect an acknowledgement within a few working days.

## Secret handling

API keys are read from environment variables only. `configs/default.yaml` names
the variable to read (`api_key_env`) and never holds a value. `.env` is
gitignored; `.env.example` documents the shape.

The code paths that touch keys never log or print them — `claimlens smoke`
deliberately reports only "present (value hidden)". If a key does reach a commit,
rotate it at the provider; removing the commit is not sufficient.

## Untrusted input

ClaimLens processes attacker-influenced content by design: claim transcripts are
written by customers, and submitted images may contain text aimed at the
reviewing model. Two properties limit the blast radius:

- The prompt declares transcript and in-image text to be **data**, to be flagged
  and never obeyed, and fences the transcript in a delimited block.
- More importantly, the rule layer **never reads claim text**. Verdicts derive
  only from structured image observations, so injected instructions can at most
  raise a `text_instruction_present` flag. Delimiter fencing is defence in depth;
  this indifference is the actual defence.

When changing `src/claimlens/rules/`, preserve that property: the decision path
must not start consuming free text.

## Scope note

Image bytes are decoded locally with Pillow before any model call. Keep Pillow
current — image decoders are a recurring source of CVEs, and the dependency is
pinned in `uv.lock` for exactly that reason.
