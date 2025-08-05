# Configuration file for Okta IDX automated flow

# Okta Configuration
OKTA_DOMAIN = "<TARGET_DOMAIN>.okta.com"
OKTA_BASE_URL = f"https://{OKTA_DOMAIN}"
USERNAME = "<USERNAME@TARGET_DOMAIN>"
PASSWORD = "<CAPTURED_PASSWORD>"

# Vault Configuration
VAULT_BASE_URL = "<VAULT_URL>"
VAULT_REDIRECT_URI = f"{VAULT_BASE_URL}/ui/vault/auth/oidc/oidc/callback"

# Battleplan Configuration
BATTLEPLAN_BASE_URL = "<BATTLEPLAN_URL>"
BATTLEPLAN_AUTH = "<BATTLEPLAN_AUTH_BASE64_FROM_ADMIN:PASSWORD>"
AGENT_IP = "<TARGET_IP>"
