variable "vps_id" {
  description = "ID of the KVM 2 bought by hand in hPanel, which Terraform adopts."
  type        = string
}

variable "data_center_id" {
  description = "Hostinger data center ID of that VPS."
  type        = number
}

variable "template_id" {
  description = "Hostinger OS template ID; the same Ubuntu as prod. Changing it reinstalls the VPS."
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
