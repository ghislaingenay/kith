terraform {
  # use_lockfile (S3-native state locking) is GA from 1.11.
  required_version = ">= 1.11"

  required_providers {
    hostinger = {
      source  = "hostinger/hostinger"
      version = "~> 0.1.23"
    }
  }

  # Private bucket made by hand (docs/deploy-quickstart.md, "Load-test VPS").
  # The region comes from AWS_REGION, the keys from AWS_ACCESS_KEY_ID and
  # AWS_SECRET_ACCESS_KEY.
  backend "s3" {
    bucket       = "kith-terraform-state"
    key          = "loadtest/hostinger.tfstate"
    encrypt      = true
    use_lockfile = true
  }
}

# The token comes from HOSTINGER_API_TOKEN.
provider "hostinger" {}
