# Brief analysis

> Filled in during the first eight minutes, before any code is written.
> Requirement identifiers assigned here are used for the rest of the session, in
> commit messages, in the pull request, and in the walkthrough.

## Requirements

Separate what the brief states from what it assumes. An implied requirement is
still a requirement, but it is one we chose to read into the text, and saying so
is the difference between analysis and guessing.

| ID | Requirement (quote the brief) | Kind | Our reading | Confidence |
| --- | --- | --- | --- | --- |
| R1 | "Build an MCP server that exposes the minimum set of tools a Duvo agent needs to do a buyer's job." | explicit | A small, deliberately chosen tool surface. Minimum is a judged decision we must defend, not the smallest number of tools we can get away with. | high |
| R2 | "Stubbing the StoreLink calls is fine — the integration plumbing isn't what we're testing." | explicit | We are permitted to run against a mock upstream. The mock must still be real enough to satisfy R6 and R7 end to end. | high |
| R3 | "what you expose, what you choose *not* to expose, what shapes you return, and how you name things" | explicit | Non-exposure is a graded deliverable. Every StoreLink endpoint we decline to wrap needs a stated reason. | high |
| R4 | "List your decisions briefly in the README." | explicit | The tool-surface decisions and their rationale live in the README, not only in this document. | high |
| R5 | "Connect your MCP server to an MCP client of your choice (Claude Desktop, Claude Code, custom — whatever you'd reach for)." | explicit | A real client completes a real protocol handshake against our server. `scripts/mcp_check.sh` is run before any client is attached. | high |
| R6 | "Check on-hand vs. last 24h of POS for both" (stores 47 and 102, SKU 8847291) | explicit | Two reads per store: current on-hand for the SKU, and POS activity for the SKU over a trailing twenty-four hour window. | high |
| R7 | "raise a replenishment order for any store where the gap exceeds 6 units" | explicit | A fixed decision threshold of six units, evaluated per store, strictly greater than. See T2 for the direction of the gap and T3 for the strictness of "exceeds". | high |
| R8 | (unstated) how many units to order once the threshold is crossed | implied | The brief specifies the trigger and is silent on the quantity. This is a genuine specification hole, resolved deterministically on the server. See T13. | medium |
| R9 | "Show it working in the recording." | explicit | An observed end-to-end run, not a described one. This is the CLAUDE.md rule one obligation applied to the demonstration itself. | high |
| R10 | "an FDE debugging at 11pm when something is broken" | explicit | Structured, correlatable diagnostic output: request identifiers, upstream call outcomes, timings, which store key was used by name and never by value. | high |
| R11 | "a Korral category buyer reading the audit log the next morning trying to understand what the agent did on their behalf" | explicit | A separate, plain-language, append-only trail of actions taken on the buyer's behalf, including the arithmetic behind each decision and whether an order was newly created or replayed. | high |
| R12 | "Implement secret loading" for "a per-store API key" | explicit | One credential per store, loaded from outside the process, resolved per request. Already provided by `secrets_provider.py`. | high |
| R13 | "what happens when (a) a key rotates while a request is in flight" | explicit | Rotation is detected without a restart, and an in-flight failure caused by rotation has a defined, safe outcome that differs between reads and writes. See T6. | high |
| R14 | "(b) the agent asks for a store your server doesn't have credentials for" | explicit | Fail closed, before any upstream call, with a typed error that tells Korral's IT what to fix and reveals nothing about other stores or any key material. | high |
| R15 | "Both should fail safely and informatively — Korral's IT will judge you on both." | explicit | Safe and informative are both required; neither a silent success nor an opaque failure passes. | high |
| R16 | "Write a short `DEPLOYMENT.md`" | explicit | Short, and covering the six topics the brief lists. | high |
| R17 | "include a runnable artifact (Dockerfile or equivalent)" | explicit | A reviewer can build and run it. The build itself must be observed, not assumed. | high |
| R18 | "StoreLink is not reachable from the public internet" | explicit | Our server runs inside Korral's network next to StoreLink. Any design that calls StoreLink from Duvo-hosted infrastructure is dead on arrival. | high |
| R19 | "No customer data may leave Korral's GCP tenancy" | explicit | A hard boundary condition on every byte we return, including everything that reaches the agent's model context. See T3, which is the sharpest conflict in the brief. | high |
| R20 | "You will ship updates frequently after go-live" | explicit | Deployment must support routine redeploys and a fast, low-ceremony rollback that does not touch secrets. | high |
| R21 | "Cover: where this runs, how it gets there, how secrets are handled, who owns the pipeline (Duvo or Korral), how you ship a fix at 11pm if something breaks, and what you'd want to confirm with Korral's IT before day 1." | explicit | Six named sections in `DEPLOYMENT.md`. The last one is where every unresolved assumption in this document surfaces. | high |
| R22 | "Auth: X-Korral-Store-Key: <key> header, sent on every request." | explicit | Every outbound StoreLink call carries the header. There is no unauthenticated path. | high |
| R23 | "Each key is scoped to a single store" | explicit | Key selection is a function of the store being acted on. Endpoints that are not store-scoped create a contradiction. See T12. | high |
| R24 | "rotated weekly by Korral's IT" | explicit | Rotation is routine and frequent, not exceptional. It must be detected rather than scheduled, because the brief names no day or time. | high |
| R25 | (unstated) the agent may call the same tool twice | implied | Agents retry. A duplicate replenishment order is a real financial event, so writes must be idempotent and the replay must remain visible downstream. See T4. | medium |
| R26 | (unstated) the six-unit threshold is Korral's policy, not the caller's choice | implied | A stated business rule is a server-side constant, never a tool parameter. See T2. | high |
| R27 | (unstated) identifiers and quantities arriving from a model may be wrong | implied | Unknown store, unknown SKU, malformed identifier, SKU not stocked at that store, and non-positive quantities are all rejected at the boundary with typed errors. See T5. | high |
| R28 | (unstated) POS returns transactions, not a total | implied | The endpoint is described as "Recent POS transactions for a SKU", so aggregation into a unit count is our job. See T8 and A5. | medium |
| R29 | (unstated) the estate is large: "~180 stores, ~18,000 active SKUs" | implied | `GET /v1/stores` is very likely paginated, and a tool that silently returns the first page is worse than no tool. See T9. | medium |
| R30 | (unstated) tool results become an export of customer data | implied | CLAUDE.md rule ten. Whatever we return crosses the system boundary into a model's context, whether or not the brief frames it that way. | high |

## Traps and contradictions

**This section is never empty.**

For each finding: the concern, the evidence in the brief, the resolution, and why
the resolution does not violate anything the brief states.

### Checked for

1. An upstream recommendation or default that conflicts with a stated business
   rule — checked, see T1.
2. A fixed business rule that the interface invites a caller to override —
   checked, see T2 and T3.
3. A requirement whose literal implementation moves customer data somewhere it
   should not go, including into a model's context — checked, see T3 in the
   findings table and the extended note below it.
4. Duplicate submissions, retries, and idempotency — checked, see T4.
5. Unknown, malformed, or out-of-range identifiers and quantities — checked, see
   T5.
6. Credential lifecycle: rotation, revocation, and mid-request behaviour —
   checked, see T6 and T7.
7. Timezone, trading hours, and calendar arithmetic — checked, see T8.
8. Unit mismatches between cases and units, currency, or time periods — checked,
   see T9.
9. Pagination, partial data, and upstream failure semantics — checked, see T10
   and T11.
10. Health, restart, and rollback behaviour under partial degradation — checked,
    see T14.

### Findings

| # | Concern | Evidence | Resolution | Why this does not break the brief |
| --- | --- | --- | --- | --- |
| T1 | Supplier lead time is offered as an input and invites us to modify a stated rule. StoreLink exposes "Supplier details (incl. lead time)", and it is tempting to widen or narrow the six-unit trigger for a long-lead-time supplier. The excerpt documents no replenishment recommendation field, so the classic recommendation-versus-rule conflict is not present in the text; lead time is the nearest thing to it. | "GET /v1/suppliers/{supplier_id} Supplier details (incl. lead time)" against "raise a replenishment order for any store where the gap exceeds 6 units". | The threshold is six units, unconditionally. Lead time is returned to the buyer as context on the order and never enters the trigger arithmetic. If Korral later wants lead-time-sensitive thresholds, that is a policy change made by a buyer, not an inference made by our server. | The brief states the rule and separately lists an endpoint. It never says lead time modifies the rule, so honouring the rule literally and surfacing lead time as information satisfies both sentences. |
| T2 | The direction of "the gap" is undefined, and the two readings produce opposite behaviour. "on-hand vs. last 24h of POS" could mean on-hand minus units sold, or units sold minus on-hand. | "Check on-hand vs. last 24h of POS for both, and raise a replenishment order for any store where the gap exceeds 6 units", read against the buyer's job as described in the context: "deciding whether a store is going to be empty by afternoon". | Gap equals units sold in the last twenty-four hours minus current on-hand, in units. A positive gap means yesterday's demand would exhaust today's shelf. The tool returns `on_hand_units`, `pos_units_24h`, and `gap_units` explicitly so the buyer can see the subtraction, and the audit line records all three. | The brief never states the direction. The reading we chose is the only one that matches the stated business purpose of predicting an empty shelf; the opposite reading would place orders at well-stocked stores, which contradicts the context paragraph. |
| T3 | Six is a business rule that a tool interface would happily accept as a parameter, and "exceeds" has a boundary that a model will guess at. | "where the gap exceeds 6 units". | `REPLENISHMENT_GAP_THRESHOLD_UNITS = 6` is a module-level constant in `duvo_fde.domain`. No tool accepts a threshold argument, and no tool accepts an "order anyway" override. "Exceeds" is strict: a gap of exactly six does not order; seven does. A test pins the boundary at 6, 7, and a negative gap. | The brief states the rule as fact, not as a default. Refusing to let a caller change it is the strictest possible compliance with what is written, and strict inequality is the plain-English meaning of "exceeds". |
| T4 | Duplicate replenishment orders. The brief never mentions retries, but the caller is an agent and the write is a purchase. | "POST /v1/stores/{store_id}/replenishment Raise a replenishment order" with no idempotency semantics documented anywhere in the excerpt. | Every order is placed through `IdempotencyStore.execute` with a deterministic key derived server-side from store identifier, SKU, quantity, and the store-local ordering date. The `OperationResult` is passed onward intact, and the audit line records `created` or `duplicate` so the buyer's morning read is not inflated by a retry. | The brief asks for an order to be raised. Raising it exactly once when asked twice is a stricter reading of "raise a replenishment order", not a weaker one, and the replay is reported rather than hidden. |
| T5 | Identifiers arrive from a model and may be unknown, malformed, or simply invented. Quantities may be zero, negative, or absurd. | The demo names "SKU 8847291" and "stores 47 and 102" as bare numbers with no stated format; nothing in the brief constrains what an agent may pass. | Validate at the boundary before any upstream call or credential lookup: store identifier and SKU must match the expected shape, quantity must be a positive integer, and an unrecognised identifier raises `UnknownEntityError`. A SKU that is valid but not stocked at that store is a distinct, non-error outcome reported as "not stocked", never as a zero on-hand reading. | The brief says nothing about validation, so nothing is contradicted. Rejecting a malformed request is the only behaviour that can be described as failing "safely and informatively". |
| T6 | A key rotating mid-request is defined for reads and dangerous for writes, and the brief asks for one answer to what are really two questions. | "Implement secret loading and a story for what happens when (a) a key rotates while a request is in flight". | The provider re-stats the credential file on every read, so the new key is picked up without a restart. On a `401` from StoreLink: for a `GET`, re-read the key and retry once, because a read has no side effect. For the `POST`, never retry blindly. Retry only through the idempotency layer when no order was recorded as created; otherwise return a typed error stating that the credential rotated mid-request and that the order's status is unknown and must be confirmed with `GET /v1/stores/{store_id}/replenishment/{order_id}` before any further attempt. | The brief requires a safe and informative outcome. A blind `POST` retry across a rotation risks a second real order, which would be neither. Declining to guess and telling the operator exactly what to check is informative in the sense Korral's IT will grade. |
| T7 | Failing closed for a missing credential is in tension with being informative. Naming the missing store confirms to the caller that we do not hold that key. | "the agent asks for a store your server doesn't have credentials for ... Both should fail safely and informatively". | Refuse before any network call with a stable error code and a message that names the requested store and the remediation, for example that no credential file is present for that store. Never enumerate which stores do have credentials, never echo any key material, and never vary the message in a way that turns the error into an oracle for the rest of the estate. Key values are registered with the redacting logger so they cannot reach a log, an error, or the audit trail. | The brief asks for information about the failure that occurred, not information about the credential store as a whole. Naming the one store the caller already named leaks nothing the caller did not supply. |
| T8 | Time arithmetic. "Last 24h" is ambiguous across a European estate, "by afternoon" is a store-local judgement, the format of `since` is undocumented, and weekly rotation has no stated day or hour. | "GET /v1/stores/{store_id}/pos?sku={sku}&since=..." and "last 24h of POS"; "~180 stores" in a "European specialty grocery chain"; "rotated weekly by Korral's IT". | Compute the window as an absolute twenty-four hours ending at the current instant, send `since` as an ISO-8601 timestamp with an explicit UTC offset, and use the injectable `Clock` so tests are deterministic. Record both the UTC instant and, where the store's timezone is known, the store-local time in the audit line, because the buyer reasons in store-local hours. Rotation is detected by file change, never by a schedule, so the absence of a stated rotation hour cannot break us. | The brief does not define the window's boundaries or the parameter format. A trailing twenty-four hours from now is the plain reading of "last 24h", and recording both clocks satisfies the buyer's need without changing the arithmetic. |
| T9 | Unit mismatch between the threshold, the pack size, and the ordering unit. Grocery replenishment is commonly placed in cases, and the SKU name embeds a weight. | "the gap exceeds 6 units" and "SKU 8847291 (Madeta butter 250g)"; the POST body's schema is not given anywhere in the excerpt. | Everything internal is held in units, and every field name carries its unit: `on_hand_units`, `pos_units_24h`, `gap_units`, `order_quantity_units`. Grams are a pack attribute and never enter the arithmetic. No silent conversion to cases is performed. Whether StoreLink's replenishment payload expects units or cases, and what the case size is for this SKU, go on the day-one confirmation list in `DEPLOYMENT.md`. | The brief states the threshold in units, so working in units is literal compliance. Refusing to invent a case conversion avoids reading a field the upstream may never return, per CLAUDE.md rule five. |
| T10 | Partial upstream failure silently changes the decision. If the POS call fails and the failure degrades to zero units sold, the gap becomes negative and a store that needed stock is judged healthy. | The buyer task spans two stores — "Check on-hand vs. last 24h of POS for both" — and the excerpt documents no error semantics for any endpoint. | A failed or missing upstream read is never coerced to zero. Each store is reported with its own explicit status, so the result for stores 47 and 102 can legitimately be "ordered" and "not evaluated: POS unavailable". The agent is told which store was not assessed, and the audit line records the non-assessment. | The brief asks for both stores to be checked. Reporting honestly that one could not be checked is closer to that instruction than silently reporting a store as healthy on data we never received. |
| T11 | Pagination and truncation on the store list. | "GET /v1/stores List stores" against "~180 stores". No page parameters are documented in the excerpt. | We do not expose a general "list all stores" tool. Every tool in our surface takes an explicit store identifier, which also resolves T12. If a listing capability is later required, it must page explicitly and report whether more results exist rather than returning a silently truncated first page. | The brief asks for the minimum set of tools and explicitly grades what we choose not to expose. Declining an endpoint whose pagination behaviour is undocumented is a defensible minimum, and it is recorded in the README per R4. |
| T12 | Direct contradiction between per-store key scoping and endpoints that are not store-scoped. `GET /v1/stores`, `GET /v1/skus/{sku}` and `GET /v1/suppliers/{supplier_id}` have no store in their path, yet "Auth: X-Korral-Store-Key ... sent on every request" and "Each key is scoped to a single store". No key can be the correct key for a call that names no store. | The endpoint list and the authentication paragraph, read together. | Every tool we expose carries a store context, and non-store-scoped calls are signed with that store's key. SKU and supplier lookups are therefore always made in the context of the store whose data the buyer is examining. `GET /v1/stores` is not exposed at all, because there is no principled key for it. Whether a store key is in fact accepted on the SKU and supplier endpoints is the first item on the day-one confirmation list. | The brief says a key is sent on every request and that keys are per store; sending the acting store's key satisfies both sentences literally. It never says these endpoints are callable without a store context. |
| T13 | Specification hole: the trigger is defined, the quantity is not. | "raise a replenishment order for any store where the gap exceeds 6 units" — the brief states no quantity anywhere. | The quantity is computed deterministically on the server as the gap in units, so an order restores the shelf to roughly one day of observed demand. It is never chosen by the model, never passed in by the caller, and the tool response shows the arithmetic that produced it. This is recorded as assumption A4, the sharpest one in this document. | The brief specifies when to order and is silent on how much. Any implementation must choose something; choosing deterministically on the server, disclosing the rule, and flagging it as an assumption violates nothing and delegates no calculation to a model, per CLAUDE.md rule two. |
| T14 | Degradation, restart, and rollback. StoreLink is on a private network, so the most likely production failure is a network path problem rather than an application crash, and a naive health check would restart a process that is working. | "StoreLink is not reachable from the public internet" and "You will ship updates frequently after go-live". | Liveness asserts only that the process is running. A credential file that is temporarily unreadable while a last known good value is still held is reported as degraded and stays in service. Secrets live in a mounted directory outside the image, so an image rollback at eleven at night never touches credentials and never requires a rotation. | The brief asks for safe failure and frequent shipping. Keeping a correctly serving instance in service, and separating the artifact's lifecycle from the credential's, is the only way both hold at once. |
| T15 | Step 1 permits a stub; step 2 requires a real run. A stub thin enough to satisfy "the integration plumbing isn't what we're testing" is not enough to demonstrate the buyer task on camera. | "Stubbing the StoreLink calls is fine" against "Use it to complete this real buyer task end-to-end ... Show it working in the recording." | The mock upstream must serve real fixture data for SKU 8847291 at stores 47 and 102, with one store above the threshold and one at or below it, so the demonstration proves the rule discriminates rather than merely that a call succeeds. `fixtures/upstream.json` currently contains only placeholder records, so every field shape we consume is an assumption until those fixtures are written. | The brief grants permission to stub; it does not require the stub to be trivial. Making the stub faithful is the only way to satisfy step two while using the permission granted in step one. |

**Extended note on item three of the checklist, customer data crossing the
boundary.** This is the sharpest contradiction in the brief and it is not stated
as one. Korral's IT says "No customer data may leave Korral's GCP tenancy". Our
server can run inside that tenancy and satisfy that sentence for every byte it
holds. But the caller is "a Duvo agent", and everything a tool returns is placed
into that agent's model context. If the model is hosted outside Korral's tenancy
— which is the ordinary case and which the brief never rules out — then every
tool response is an export of Korral data, regardless of where the container
runs. The resolution has three parts, none of which contradicts anything the
brief states. First, treat the tool return payload, not the network diagram, as
the export boundary, and return the minimum that completes the buyer's job: for
POS we return an aggregated unit count for the SKU and window, never the
underlying transaction rows, so no basket, loyalty, payment, timestamp-level or
staff detail is ever serialised. Second, never pass an upstream response body
through unmodified; every field returned is one we deliberately chose. Third,
put the model's hosting location at the top of the day-one confirmation list in
`DEPLOYMENT.md`, with the two viable answers named: a model served inside
Korral's own tenancy, or a written agreement that aggregated, non-personal stock
figures fall outside Korral's definition of customer data. The brief asks us to
check on-hand against the last twenty-four hours of POS; a unit total answers
that question completely, so the minimisation costs the buyer nothing.

## Assumptions

| ID | Assumption | Why it is needed | What changes if it is wrong |
| --- | --- | --- | --- |
| A1 | The gap is units sold in the last twenty-four hours minus current on-hand units. | The trigger in R7 cannot be computed without a direction, and the brief gives none. | The trigger inverts. Every ordering decision in the demonstration flips, so this is stated aloud on camera and shown in the tool output. |
| A2 | "Exceeds" is strictly greater than, so a gap of exactly six does not raise an order. | The boundary must be pinned in a test. | One additional store per run would receive an order. The change is a single comparison operator and one test. |
| A3 | The six-unit threshold is Korral's policy and applies to every store and SKU. | It is implemented as a constant with no override path. | If the threshold is per category or per store, it becomes configuration owned by Korral, still server-side, still never a tool parameter. |
| A4 | The order quantity equals the gap in units. | R8 is unspecified and something must be ordered. | Under-ordering or over-ordering against Korral's real replenishment policy. The quantity rule is one function, isolated so it can be replaced without touching the trigger. |
| A5 | `GET /v1/stores/{store_id}/pos` returns a list of transactions that we aggregate into a unit count, as implied by the wording "Recent POS transactions". | We must know whether to sum or to read a total. | If the endpoint returns a pre-aggregated total, our aggregation step is removed and the field we read changes. Recorded because reading a field the upstream never returns is a named prior failure. |
| A6 | `since` accepts an ISO-8601 timestamp with an explicit UTC offset. | The parameter is shown only as `since=...`. | The request is rejected or, worse, silently misinterpreted as a different window. Confirmed with Korral's IT before day one. |
| A7 | A store's API key is accepted on the non-store-scoped endpoints `GET /v1/skus/{sku}` and `GET /v1/suppliers/{supplier_id}`. | T12 has no other resolution that keeps every request authenticated. | SKU and supplier enrichment becomes unavailable to us, and those tools are withdrawn from the surface rather than left broken. The ordering decision does not depend on them. |
| A8 | The replenishment payload is expressed in units, matching the threshold. | The POST body schema is not documented. | Every order quantity is wrong by the case multiple, which is a serious commercial error. This is why field names carry units and why no conversion is performed silently. |
| A9 | StoreLink does not deduplicate replenishment orders, so deduplication is entirely our responsibility. | It determines whether the idempotency layer is load-bearing. | If StoreLink does deduplicate, our layer becomes belt and braces and costs nothing. The asymmetry of harm makes this the safe assumption. |
| A10 | The agent's model is hosted outside Korral's GCP tenancy. | It forces the data-minimisation decisions described under T3. | If the model runs inside the tenancy, our minimisation is stricter than required and remains correct. No rework is needed. |
| A11 | One replica of the server runs, so the in-process `IdempotencyStore` is sufficient. | The existing store is process-local by design. | With more than one replica, deduplication must move to shared state. Already recorded as a known trade-off in `docs/06-assumptions-and-risks.md`. |
| A12 | A store's timezone is discoverable from `GET /v1/stores/{store_id}`. | Store-local times make the audit trail readable to a buyer. | The audit trail records UTC only, which is correct but harder for the buyer to reason about. The ordering arithmetic is unaffected. |
| A13 | Store identifiers are the bare values used in the brief, such as `47` and `102`, and SKUs are numeric strings such as `8847291`. | Boundary validation needs a shape to check. | Validation rejects legitimate identifiers. The format rule is one validator with one test, and it is deliberately permissive rather than clever. |

## Data flow

**Origin.** All data originates in StoreLink, inside Korral's network, reachable
only from within Korral's GCP tenancy (R18).

**Inbound.** The Duvo agent calls an MCP tool over the transport with a store
identifier, a SKU, and nothing else that matters. Arguments are validated at the
boundary before anything else happens (R27).

**Credential resolution.** The server resolves the per-store key by store
identifier from the mounted secrets directory, re-reading the file on each
access so a weekly rotation is picked up without a restart (R12, R24). A store
with no credential fails closed here, before any network call (R14).

**Upstream.** The server calls StoreLink over the private network with
`X-Korral-Store-Key` on every request (R22). It reads on-hand for the SKU and
POS activity for the SKU over the trailing twenty-four hours (R6).

**Server-held.** Inside the process the server holds the raw upstream responses,
the resolved key value, and the computed arithmetic. The key never leaves this
layer: it is registered with the redacting logger, so it cannot appear in a log
line, an error payload, or an audit record (CLAUDE.md rule seven).

**Decision.** The gap is computed deterministically on the server and compared
against the constant six (R7, R26). No model participates in the calculation or
the comparison. If the threshold is crossed, the order is placed through the
idempotency layer and the `OperationResult` is carried onward with its replay
flag intact (R25).

**Returned to the agent, and therefore exported.** This is the boundary crossing.
The tool returns only: store identifier, SKU identifier and display name,
`on_hand_units`, `pos_units_24h`, `gap_units`, the threshold applied, the
decision, and, where an order was placed, the order identifier, the ordered
quantity in units, and whether the result was newly created or a replay. POS
transaction rows, basket data, payment data, loyalty identifiers, staff
identifiers, and raw upstream response bodies are never returned. Everything in
that list enters the model's context and must be treated as an export of Korral
data whether or not the brief describes it that way (R19, R30, and the extended
note above).

**Sideways, staying inside the tenancy.** Two observability streams are written
locally and never returned to the agent: a structured JSON diagnostic log for the
FDE at eleven at night, carrying request identifiers, upstream outcomes and
timings, and key names but never key values (R10); and an append-only audit
trail written in plain language for the buyer the next morning, recording what
was checked, the arithmetic that produced the decision, what was ordered, and
whether the order was created or replayed (R11).

## Reference material match

**Zero per cent. The reference kit does not match, so it is ignored.** No
reference kit is present in or beside this repository — the paths excluded by
`.gitignore` do not exist — so there is nothing to match against, and no
reference material is consulted for the remainder of this session.
