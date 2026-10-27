# The load-test VPS (ADR-0021). This module only makes the machine; setup.sh
# one folder up turns it into the Kith stack, and recreate.sh reinstalls it.

# Runs as root once the OS is installed, on purchase and on every recreate.
resource "hostinger_vps_post_install_script" "loadtest" {
  name = "kith-loadtest"
  content = templatefile("${path.module}/post-install.sh.tftpl", {
    authorized_keys = join("\n", var.authorized_keys)
    ssh_host_key    = trimspace(var.ssh_host_key)
  })
}

resource "hostinger_vps" "loadtest" {
  plan                   = var.plan
  data_center_id         = var.data_center_id
  template_id            = var.template_id
  post_install_script_id = hostinger_vps_post_install_script.loadtest.id

  # Hostinger has no delete call: destroying cancels the subscription.
  lifecycle {
    prevent_destroy = true
  }
}
