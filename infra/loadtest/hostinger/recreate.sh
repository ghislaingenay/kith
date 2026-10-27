#!/bin/sh
# Reinstalls the load-test VPS's OS with Hostinger's `recreate` call
# (ADR-0021): every file on it is lost. post-install.sh.tftpl runs again, so
# the same keys get in and the host key is unchanged; setup.sh then brings the
# stack back. Run from this folder after `terraform init`, with
# HOSTINGER_API_TOKEN set:
#   sh recreate.sh
set -eu
: "${HOSTINGER_API_TOKEN:?set HOSTINGER_API_TOKEN}"

api="https://developers.hostinger.com/api/vps/v1"
call() { curl -fsS -H "Authorization: Bearer $HOSTINGER_API_TOKEN" -H "Content-Type: application/json" "$@"; }

# The VM's ID, template and post-install script, read from the state.
vps=$(terraform show -json | jq -c '.values.root_module.resources[]? | select(.address == "hostinger_vps.loadtest") | .values')
if [ -z "$vps" ]; then
  echo "recreate: hostinger_vps.loadtest is not in the state; run terraform apply first" >&2
  exit 1
fi
vm_id=$(echo "$vps" | jq -r .id)
body=$(echo "$vps" | jq -c '{template_id, post_install_script_id}')

action_id=$(call -X POST -d "$body" "$api/virtual-machines/$vm_id/recreate" | jq -r .id)
echo "recreate: VM $vm_id, action $action_id"

# Slow polling: the API allows 90 calls a minute.
wait_for() {
  what=$1 url=$2 filter=$3 want=$4
  for _ in $(seq 120); do
    got=$(call "$url" | jq -r "$filter")
    case "$got" in
      "$want") return 0 ;;
      error) echo "recreate: $what failed" >&2; exit 1 ;;
    esac
    sleep 10
  done
  echo "recreate: $what is still '$got' after 20 min" >&2
  exit 1
}
wait_for "the recreate action" "$api/virtual-machines/$vm_id/actions/$action_id" .state success
wait_for "the VM" "$api/virtual-machines/$vm_id" .state running

echo "recreate: VM $vm_id is reinstalled; run setup.sh next"
