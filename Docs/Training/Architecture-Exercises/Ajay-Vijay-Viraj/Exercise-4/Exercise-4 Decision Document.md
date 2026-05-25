## Decision

**Variant B (REST-first monolith) is recommended.**

## Trade-off Summary

|Axis|Variant B|Variant D|Winner|
|---|---|---|---|
|Simplicity|5 services, REST calls|Orchestrator + 5 activities|**B**|
|Operational Cost|$500–800/mo|$1,200–1,800/mo|**B**|
|Failure Isolation|One service down|All jobs blocked|**B**|
|Migration Speed|8 weeks|16+ weeks|**B**|
|Observability|Manual correlation|Built-in tracing|D|
|Consistency|Eventual|Strong ordering|D|

**B wins on: simplicity, cost, failure isolation, speed. These matter more for S2.**

## Why B Wins

1. **Simpler to run** — No orchestrator complexity, no state store recovery logic
2. **Cheaper** — Saves ~$1,000/month (18 months = $18k saved)
3. **Safer for field ops** — If one service fails, other jobs still work. If orchestrator fails in D, everything stops.
4. **Faster to launch** — Can deploy Profile Service first, prove concept, add services. D requires everything built before any value.

## What We Give Up

- No built-in workflow visibility → Add a Dashboard service later (easy)
- SAP retry logic in the service, not orchestrator → Add idempotency keys in Sync Service
- Mobile app controls workflow sequence → Add validation checks in Engagement Service

## When We'd Switch to D

If any of these happen, we reconsider:

1. > 50 failed jobs/day due to timeouts
    
2. > 3 data loss incidents in SAP
    
3. Workflow becomes too complex (more than 5 steps, branching)
4. On-call team spends >2 hours/week debugging failures