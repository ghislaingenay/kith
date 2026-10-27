# All setup.sh needs: where to SSH, and as whom.
output "address" {
  value = hostinger_vps.loadtest.ipv4_address
}

output "ssh_user" {
  value = "root"
}
