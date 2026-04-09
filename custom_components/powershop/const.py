"""Constants for Powershop integration."""

DOMAIN = "powershop"

# Configuration keys
CONF_EMAIL = "email"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_ACCOUNT_NUMBER = "account_number"
CONF_PROPERTY_ID = "property_id"

# Production Firebase config — Powershop's own public project identifier.
#
# NOTE: This is NOT a secret credential.
# Firebase web API keys ("AIzaSy...") are intentionally public values — Google
# embeds them verbatim in every Android APK, iOS IPA, and web JS bundle for the
# Firebase project. Powershop's key is already publicly discoverable. The key is a project *identifier*, not an
# authentication token; it cannot be used to access any data without completing
# the full OTP → custom-token → ID-token authentication flow. Replacing it with
# an environment variable is not meaningful here because (a) it must always be
# Powershop's specific value and (b) it is already public knowledge.
# See: https://firebase.google.com/docs/projects/api-keys
FIREBASE_API_KEY = "AIzaSyCYCKXQhGmo7haJxAAyO_7mIPrV7jtxsK8"  # noqa: S105 — public project identifier, not a secret
FIREBASE_SIGN_IN_URL = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken"
FIREBASE_REFRESH_URL = "https://securetoken.googleapis.com/v1/token"

# Powershop auth + API endpoints
EMAIL_CONNECTOR_URL = "https://auth.powershop.nz/cf/email-connector"
OTP_VALIDATOR_URL = "https://auth.powershop.nz/cf/email-otp-authenticator"
GRAPHQL_URL = "https://api.powershop.nz/v1/graphql/"
BRAND = "powershop"  # used in auth endpoint payloads
BRAND_GQL = "POWERSHOP"  # GraphQL BrandChoices enum value