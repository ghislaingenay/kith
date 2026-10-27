# The load-test VPS (ADR-0021). The operator buys it in hPanel; this module
# adopts it and never buys one. setup.sh one folder up turns it into the Kith
# stack, and recreate.sh reinstalls it.

# Runs as root once the OS is installed, on every recreate.
resource "hostinger_vps_post_install_script" "loadtest" {
  name = "kith-loadtest"
  content = templatefile("${path.module}/post-install.sh.tftpl", {
    authorized_keys = join("\n", var.authorized_keys)
    ssh_host_key    = trimspace(var.ssh_host_key)
  })
}

# Adopts the VPS bought by hand. While this block names it, a lost state is
# imported again rather than bought again.
import {
  to = hostinger_vps.loadtest
  id = var.vps_id
}

resource "hostinger_vps" "loadtest" {
  # The provider requires a plan, but it only matters when buying, which
  # never happens here.
  plan                   = "hostingercom-vps-kvm2-usd-1m"
  data_center_id         = var.data_center_id
  template_id            = var.template_id
  post_install_script_id = hostinger_vps_post_install_script.loadtest.id

  lifecycle {
    # Hostinger has no delete call: destroying cancels the subscription.
    prevent_destroy = true
    # A change to either would replace the VPS, which means buying another.
    ignore_changes = [plan, data_center_id]
  }
}
