# Sandbox Choice — Why `RestrictedPython`

We picked `RestrictedPython` for the `search`/`execute` sandbox because it
matches the threat model exactly. The radar MCP server runs locally, edits a
single JSON file on disk, holds no credentials, and makes no network calls —
so the only thing the sandbox needs to prevent is the model accidentally (or
mischievously) reaching for `open`, `exec`, `eval`, `import`, `__class__`,
or filesystem APIs to escape the proxy and corrupt unrelated state.
`RestrictedPython` does that at compile time: it rewrites attribute access
through `safer_getattr`, swaps in `safe_builtins` (no `open`, no `compile`,
no `__import__`), guards subscripting and iteration, and fails the compile
on syntax that escapes the policy. We add a 5-second `SIGALRM` timeout for
runaway loops and gate write methods behind a `_ReadOnlyRadar` wrapper for
the `search` path. A heavier sandbox like a subprocess or `isolated-vm`
would add OS-level isolation — useful when the sandbox runs untrusted code
that touches credentials or network — but here the proxy is the only object
the model can reach, the JSON file is non-sensitive, and the per-call cost
of forking processes would dominate the radar's millisecond-scale operations.
This calculus changes the moment this server starts proxying real APIs or
holding tokens; at that point we'd upgrade to subprocess or `isolated-vm` and
re-do the threat model. For a local, file-only DSL editor, `RestrictedPython`
is the right tier.
