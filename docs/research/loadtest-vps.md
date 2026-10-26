# Load-test VPS: always-on Hostinger vs per-run ephemeral server

Context: production is one Hostinger VPS running the docker compose stack in
`infra/docker-compose.prod.yml` (Caddy, app, arq worker, Next.js, Postgres 16,
Redis 7, OpenSearch 2.19). We want a second machine, used only for k6 load
tests, started by GitHub Actions when a git tag is pushed. The machine must
match prod's hardware so the results say something about prod.

All sources are primary (provider API specs, provider docs, pricing pages,
provider GitHub orgs) and were read on **2026-10-26**. Prices exclude VAT.

## Recommendation

**Option (a): an always-on Hostinger VPS on the same plan as prod.** Wipe it
between runs (`docker compose down -v`, or the API's `recreate` call for a
fully clean OS), and later turn it into staging.

Why:

1. **Hostinger VPS CPUs run on a credit system, and Hetzner's do not.** Each
   plan can burst to 100% of its vCPUs while it has credits, then drops to
   30% (KVM 2). Prod will behave this way under sustained load, so SLO numbers
   only mean something if the test machine throttles the same way. A server
   from another provider can't do that (see section 3).
2. **Hostinger has no hourly billing and no "delete VM" API call**, so
   ephemeral servers on Hostinger don't work: each run would buy a new
   subscription of at least one month (section 1).
3. The extra cost is small: about $9 to $15 a month (KVM 2, depending on
   term) against under €1 a month for ephemeral Hetzner servers. That buys
   numbers measured on prod's own platform, plus a ready staging box.

Choose option (b), ephemeral Hetzner servers, only if a "roughly comparable"
number is good enough and cost matters more than fidelity. In that case use
CCX13 (dedicated vCPU) for stable numbers between runs, and treat the results
as a ceiling that prod can only reach while it still has CPU credits.

Whichever you pick, **run k6 somewhere other than the machine under test**,
for example on the GitHub Actions runner or a small separate box. If k6 shares
the 2 vCPUs with the stack, it competes with the app for CPU and, on Hostinger,
for CPU credits too.

## 1. Hostinger

### Prod plan in use

- `docs/deploy-quickstart.md` (line 33) does not name a plan. It asks for
  "Ubuntu 24.04, **4 GB RAM minimum**, 2 vCPU, 40 GB disk", and says the stack
  uses about 2.7 GB. Its only Hostinger-specific note is the SSH-keys panel
  (line 167).
- Hostinger's smallest plan with 2 vCPU is **KVM 2: 2 vCPU, 8 GB RAM, 100 GB
  NVMe, 8 TB bandwidth, AMD EPYC**. KVM 1 has only 1 vCPU and 4 GB, which is
  below the documented minimum. Source: https://www.hostinger.com/vps-hosting
- **KVM 2 price:** $8.79/mo promotional, renewing at $14.99/mo, as listed for
  the 2-year term. "All plans are paid upfront. The monthly rate reflects the
  total plan price divided by the number of months in your plan."
  Source: https://www.hostinger.com/vps-hosting
- I could not find a public list price for the 1-month term (see Open
  questions). The `GET /api/billing/v1/catalog` endpoint returns every price
  for each period. Its spec example is `hostingercom-vps-kvm2-usd-1m`, "KVM 2
  (billed every month)", 1799 cents with 899 cents for the first period. That
  is only an example value, not a quote.
  Source: https://developers.hostinger.com/openapi/openapi.json

### API, CLI, Terraform

- **Public REST API:** base URL `https://developers.hostinger.com`, bearer
  token created in hPanel, 90 requests/min. Purchases can return `202
  Accepted` while payment is still processing.
  Source: https://docs.hostinger.com/api-reference/overview
- VPS endpoints, from the OpenAPI spec
  (https://developers.hostinger.com/openapi/openapi.json):
  - **Create:** `POST /api/vps/v1/virtual-machines`, "Purchase and setup a new
    virtual machine". It charges the default payment method. If the response
    is 202, "the virtual machine was not set up", and you have to finish setup
    in hPanel. A separate `POST .../{id}/setup` sets up a VM that is already
    purchased.
  - **Start / stop / restart:** `POST .../{id}/start`, `/stop`, `/restart`.
    The stop endpoint says: "This is a compute-only power state change and
    **does not affect billing**. To stop future charges, disable auto-renewal
    on the owning subscription."
  - **Rebuild:** `POST .../{id}/recreate` reinstalls the OS and deletes all
    data and snapshots. Snapshot create and restore are also available
    (`POST .../{id}/snapshot`, `.../snapshot/restore`).
  - **Post-install scripts:** `/api/vps/v1/post-install-scripts`, which can
    play the role of cloud-init.
  - **Delete: none.** The spec has no `DELETE /virtual-machines/{id}`. The
    closest calls are on billing:
    `DELETE /api/billing/v1/subscriptions/{id}/auto-renewal/disable`, which
    lets the VM run until the end of the period it was paid for.
- **Official tools** listed by Hostinger: the `hostinger` CLI
  (`brew install hostinger/tap/hostinger`), the Terraform provider
  `hostinger/hostinger` (example pins 0.1.23), the Ansible collection
  `hostinger.vps`, an MCP server, and PHP/Python/TypeScript SDKs. All of them
  live in the `hostinger` GitHub org. Sources:
  https://docs.hostinger.com/api-reference/tools.md ,
  https://registry.terraform.io/providers/hostinger/hostinger/latest ,
  https://github.com/hostinger/terraform-provider-hostinger

### Billing

- KVM VPS billing periods: "1 month, 12 months or 24 months". "The full
  amount for the selected subscription period is charged upfront." There is
  **no hourly billing**.
  Source: https://www.hostinger.com/support/1583589-can-i-prepay-for-hosting-service-or-domains
- **Stopping a VPS does not save money** (see the stop endpoint above).
- Refunds: KVM VPS purchases can be refunded within 30 days, but "After you
  successfully receive a refund for a VPS plan, a 180-day cooldown period
  applies". So refunds can't be used as a way to pay per run.
  Source: https://www.hostinger.com/support/9088216-what-is-hostinger-refund-policy
- **Result:** an ephemeral Hostinger VPS per run would cost at least one
  1-month subscription per run, and old VMs would stay until their period
  ends. This is not viable.

### CPU model (important for load testing)

- Hostinger VPS plans use **CPU credits**. Usage below the baseline earns
  credits (1 credit = 1 core-second). When credits run out, "Available CPU
  drops to the plan's limit": 40% on KVM 1, **30% on KVM 2/4/8**. Maximum
  balance for KVM 2 is 8,640 core-seconds. Full capacity comes back once the
  balance reaches 20% of maximum. The article was published 2026-10-01 and
  modified 2026-10-09.
  Source: https://www.hostinger.com/support/how-cpu-credits-work-on-hostinger-vps/
- The same article is not consistent with itself. It says "The baseline is
  60% on every plan" but gives the formula `baseline = vCPUs × 0.30`. A
  companion article says a full balance covers "about three hours at 100% on
  all vCPUs" and that the limited level is "between 5% and 20% of capacity
  depending on your plan".
  Source: https://www.hostinger.com/support/6899741-what-is-the-cpu-use-limit-for-vps-at-hostinger/
  - My arithmetic, using the formula: KVM 2 at 100% of 2 vCPUs spends 2
    core-s/s and earns 0.6, so a full balance lasts 8,640 / 1.4 ≈ 100 min.
    Using the "three hours" statement, it lasts about 180 min. **A 45-minute
    run fits only if it starts with a full balance**, so don't schedule runs
    back to back, and don't run a heavy seed/ingest step right before one.
- CPU steal of 1–10% is called normal, and a daily node balancer reduces it.
  Source: https://www.hostinger.com/support/9615642-understanding-cpu-steal-and-its-impact-on-vps-at-hostinger/
- Per-VM metrics are available from `GET /api/vps/v1/virtual-machines/{id}/metrics`
  (OpenAPI spec above). A run could save them next to the k6 summary, to show
  whether throttling happened during the test.

## 2. Hetzner Cloud

### Billing

- "Servers have both a monthly price cap and a price per hour." You pay
  hourly until you reach the cap. "We always round up the hourly usage of a
  server", so a few minutes costs one full hour.
  Source: https://docs.hetzner.com/cloud/billing/faq/
- A server is billed "for as long as it exists ... regardless of whether it
  is turned on or not". **Only deleting it stops billing.**
  Source: https://docs.hetzner.com/cloud/billing/faq/
- A Primary IPv4 costs €0.50/month, and IPv6 is free.
  Source: https://docs.hetzner.com/cloud/servers/overview/

### Plans comparable to Hostinger KVM 2 (2 vCPU AMD, 8 GB)

| Plan | vCPU type | vCPU | RAM | Disk | €/hour | €/month cap |
|---|---|---|---|---|---|---|
| CPX22 (EU) | shared, AMD | 2 | 4 GB | 80 GB | 0.0320 | 19.99 |
| CX33 (EU) | shared, Intel/AMD (either) | 4 | 8 GB | 80 GB | 0.0144 | 8.99 |
| CPX32 (EU) | shared, AMD | 4 | 8 GB | 160 GB | 0.0577 | 35.99 |
| **CCX13** | **dedicated, AMD** | 2 | 8 GB | 80 GB | 0.0697 | 43.49 |

Sources: https://www.hetzner.com/cloud/regular-performance ,
https://www.hetzner.com/cloud/cost-optimized ,
https://www.hetzner.com/cloud/general-purpose

- On 2026-10-26, every Cost-Optimized and Regular Performance (shared) plan
  page said "This product is currently unavailable. Please check back later."
  Hetzner also says plan availability is refreshed about every 15 minutes, so
  a create call can fail even for a plan shown as available. Dedicated CCX
  plans were orderable. Source: https://docs.hetzner.com/cloud/servers/faq/
- No Hetzner plan matches KVM 2 exactly. CCX13 matches its vCPU count, RAM
  and vendor. CPX22 matches the vCPU count and vendor but has half the RAM.

### Automation

- REST API: `POST /servers` takes `user_data`, "Cloud-Init user data to use
  during Server creation. This field is limited to 32KiB". `DELETE
  /servers/{id}` "immediately removes the Server". The rate limit is 3,600
  requests/hour per project.
  Source: https://docs.hetzner.cloud/ (spec: https://docs.hetzner.cloud/cloud.spec.json)
- The official CLI is `hcloud` (latest v1.70.2, released 2026-10-23):
  `hcloud server create --name … --type ccx13 --image ubuntu-24.04
  --location … --ssh-key … --user-data-from-file cloud-init.yml`, then
  `hcloud server delete`. There is an official GitHub Action,
  `hetznercloud/setup-hcloud`, which installs the CLI.
  Sources: https://github.com/hetznercloud/cli/blob/main/docs/reference/manual/hcloud_server_create.md ,
  https://github.com/hetznercloud/setup-hcloud
- Boot time: Hetzner says Cloud servers "are usually ready within seconds".
  It publishes no figure that includes cloud-init. Our cloud-init would
  install Docker and pull the images, and that will take minutes, not
  seconds. *(Estimate, not measured.)*
  Source: https://docs.hetzner.com/robot/general/pricing/hetzner-pricing/

## 3. Is another provider's CPU comparable enough for SLO numbers?

Mostly no, for this project specifically:

- **The throttling is different.** Prod (Hostinger) runs at 100% for a while
  and then drops to about 30% once credits run out. Hetzner shared vCPUs have
  no credit system: the hypervisor shares "usage rights of CPU resources among
  several virtual servers", so the noise comes from neighbours instead.
  Dedicated vCPUs (CCX) give "its own dedicated CPU resources".
  Source: https://docs.hetzner.com/cloud/servers/overview/
  A Hetzner run can't show what prod does after its burst.
- **The CPU generation and clock speed are probably different.** Both are
  AMD, but neither provider publishes the exact EPYC model for these plans on
  the pages read, so per-core speed can differ by an unknown amount.
- **Shared vs dedicated noise:** on shared vCPUs, results change from run to
  run with the neighbours' load. That noise hides regressions between tags.
  Dedicated CCX gives stable run-to-run numbers, which is good for spotting
  regressions, but its absolute numbers say less about prod.
- Hetzner numbers are still useful for **relative** comparisons ("tag v1.4 is
  20% slower than v1.3 on the same CCX13"). They are not a good basis for
  **absolute** prod SLOs ("p95 < 500 ms on prod").

## 4. Cost for 4 runs/month of about 45 minutes

| Option | How it works | Approx. monthly cost |
|---|---|---|
| (a) Always-on Hostinger KVM 2 | Same plan as prod; wiped or recreated per run; later staging | $8.79 (24-month term, renews $14.99); 1-month term price not public (see Open questions) |
| (b1) Ephemeral Hetzner CCX13 | Created per run, deleted after | 4 runs × 1 h (rounded up) × €0.0697 ≈ **€0.28**; ≈ €0.56 if cloud-init pushes a run past one hour |
| (b2) Ephemeral Hetzner CPX22 | Same, shared vCPU | 4 × €0.0320 ≈ **€0.13** (if in stock) |
| Ephemeral Hostinger | Purchase per run | Not viable: each purchase is at least a 1-month subscription, and the API cannot delete a VM |

Option (b) also needs a cleanup step that always runs (`if: always()` in the
workflow, plus deletion of any servers labeled `kith-loadtest` that are left
over). Otherwise a failed job leaves a server billing until it hits its
monthly cap.

## Open questions

- **Price of the KVM 2 1-month term:** not on the public pricing page. Check
  it at checkout or with `GET /api/billing/v1/catalog` (needs an API token).
- **Which plan prod actually runs on:** the repo only gives minimums. Confirm
  KVM 2 (or larger) in hPanel, then buy the same plan for the load-test box.
- **The Hostinger CPU-credit article contradicts itself** (60% baseline vs
  the `vCPUs × 0.30` formula, 30% vs "5% to 20%" limited level). Measure it on
  the real box with a 2-hour CPU burn before you trust SLO numbers.
- **Whether a Hostinger API purchase completes on its own:** a `202` means
  you finish setup by hand in hPanel. This matters for option (a) only once,
  at creation.
