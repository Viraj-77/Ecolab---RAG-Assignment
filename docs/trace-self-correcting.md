# Self-Correcting Validation — One Round-Trip

Source trace: `docs/raw-traces.txt`, MISUSE TEST 1 (non-existent tech id).

## What the model tried to do

Assign a technology called `gpt-5-nano` to the `llm-capability-office` team
at ring TRIAL.

## The bad code it sent

Tool: `execute`

```python
result = radar.assign('llm-capability-office', 'gpt-5-nano', 1)
```

## The error the server returned

```
Error: Tech 'gpt-5-nano' not found in radar. Did you mean one of:
['gpt-3-5-turbo', 'gpt-5-2-azure-openai', 'gpt-5-4-databricks',
'gpt-5-mini-azure-openai', 'gpt-4o-azure-openai']?
```

The error is structured — it names the missing id, names the operation
that produced the failure (an existence check), and lists the five closest
matches the proxy could find via `difflib.get_close_matches`. The model has
everything it needs to retry without re-reading the radar.

## The corrected code (retry)

The closest plausible match is `gpt-5-2-azure-openai` (Azure OpenAI's
`gpt-5.2` is in the radar; `gpt-5-nano` is the Azure OpenAI model the model
likely *meant*, but it isn't in the radar yet). Two viable retries:

**Retry A — pick an existing alternative:**

```python
result = radar.assign('llm-capability-office', 'gpt-5-2-azure-openai', 1)
```

**Retry B — add the technology first, then assign:**

```python
radar.add_technology(
    id='gpt-5-nano',
    label='GPT-5 Nano (Azure OpenAI)',
    quadrant=0,
)
result = radar.assign('llm-capability-office', 'gpt-5-nano', 1)
```

## The successful result

For Retry A, the proxy runs `assert_tech_exists` (passes — id is in the
radar), `assert_not_duplicate` (passes — `llm-capability-office` does not
yet have `gpt-5-2-azure-openai`), `assert_adopt_has_link` (passes — ring 1
is TRIAL, not ADOPT), then appends the assignment, marks the proxy dirty,
and returns:

```json
{"tech": "gpt-5-2-azure-openai", "ring": 1, "moved": 0}
```

Because this is `execute()`, the sandbox auto-commits after the call:

```
[commit] auto-commit after execute()
```

## Why this is "self-correcting"

The error did three things the framework's Mistake 5 says naive errors miss:

1. **Named the failure precisely** — *"Tech 'gpt-5-nano' not found in radar"*
   instead of *"invalid argument"*.
2. **Listed valid alternatives** — five real tech ids the model can retry with,
   pulled at runtime from the radar via `get_close_matches`. The model does
   not have to call `radar.list_technologies()` again to recover.
3. **Suggested the corrective operation implicitly** — *"Did you mean..."*
   tells the model the next call is `radar.assign(team, <one of these>, ring)`
   without spelling out the syntax (the syntax is already in the tool
   description). Compare with MISUSE TEST 2's error, which goes further and
   spells out *"Use radar.move('llm-capability-office', '<tech>', <new_ring>)
   to change its ring"* — the proxy gives the model the exact next call when
   the structural fix is unambiguous.
