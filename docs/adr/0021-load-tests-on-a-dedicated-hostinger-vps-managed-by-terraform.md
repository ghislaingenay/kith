---
status: deferred
date: 2026-10-26
---

# Load tests run on a dedicated, always-on Hostinger VPS that Terraform manages

Deferred 2026-10-28: Kith is a personal project with no traffic to plan for yet, so a second VPS, its Terraform and the tagged Load and Stress runs cost more to run and keep working than the numbers are worth. The Terraform module and setup script were built (#159) and then removed. What stays is the k6 scenario in `loadtest/`, run in smoke mode by the prod-stack smoke test on pull requests, and the Load Test Tenants command it signs in with (#160). Revisit before a launch that could bring real load; the design below still holds, and git history has the removed module.

k6 load tests run against a second VPS on the same Hostinger plan as prod (KVM 2), kept on all the time and reinstalled with the Hostinger API's `recreate` before every run. Prod is the only other server, and a load test on it would slow real Users and spend real money, so it is never the target. The machine has to match prod because the results set prod's SLOs. Hostinger's vCPUs run on CPU credits and fall to 30% when the credits run out, and a server at another provider cannot show that. A server created and deleted for each run was rejected for that reason, and because Hostinger has no delete call and bills by the month, so a fresh server per run would cost a month each time (`docs/research/loadtest-vps.md`).

Terraform is split in two so the setup is not tied to Hostinger: a provider module that only creates the machine and outputs its address, and one setup script that turns any fresh Ubuntu box reachable over SSH into the Kith stack. Moving to another provider means writing a new module and keeping the script. Terraform manages only this VPS. Prod stays hand-built, and no AWS resource is in Terraform. The state is kept in a private S3 bucket (`kith-terraform-state`) with S3's own locking, so CI and a laptop share one state file without committing it to git.

## Considered options

- **Hetzner, one server per run.** It bills by the hour and costs almost nothing, but its CPUs and the lack of CPU credits mean its numbers compare tags with each other and say little about prod.
- **A GitHub runner as the target.** Rejected: the hardware is unlike prod's.
- **Terraform state in HCP Terraform.** Rejected: one more account and token, when an S3 bucket is already there.

**Amended 2026-10-27:** the operator buys the VPS in hPanel and the module adopts it by ID (an `import` block) instead of creating it. The Hostinger provider buys a new VPS whenever its state doesn't know the machine, and a first purchase through the API stopped half-way at "payment initiated", so a purchase by Terraform risked a second subscription.

## Consequences

- The VPS can later become the staging server the deploy plan expects.
- Every run records the CPU credit level at the start and refuses to start when it is low, so runs stay comparable. SLOs hold "until CPU credits run out" until a soak test measures what happens after.
