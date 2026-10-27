variable "plan" {
  description = "Hostinger plan item; the same KVM 2 as prod. The suffix is the billing term (1m, 12m, 24m)."
  type        = string
  default     = "hostingercom-vps-kvm2-usd-1m"
}

variable "data_center_id" {
  description = "Hostinger data center ID; the same one as prod."
  type        = number
}

variable "template_id" {
  description = "Hostinger OS template ID of Ubuntu 24.04. Changing it reinstalls the VPS."
  type        = number
}

variable "authorized_keys" {
  description = "SSH public keys allowed in as root: the operator's and CI's."
  type        = list(string)
}

variable "ssh_host_key" {
  description = "The VPS's ed25519 host private key (OpenSSH format), kept the same across reinstalls so known_hosts stays valid."
  type        = string
  sensitive   = true
}
