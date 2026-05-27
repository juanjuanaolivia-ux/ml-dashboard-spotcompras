"""
reconstruct_configs.py
Reconstruye ml_config.json, ml_tokens.json y ml_email_config.json
desde variables de entorno (GitHub Actions secrets).
Correr ANTES de run_daily.py en el workflow.
"""
import os, json, time

def env(key, required=True):
    val = os.environ.get(key, '')
    if required and not val:
        raise ValueError(f"Falta variable de entorno: {key}")
    return val

# ml_config.json
config = {
    "client_id":     env("ML_CLIENT_ID"),
    "client_secret": env("ML_CLIENT_SECRET"),
    "redirect_uri":  env("ML_REDIRECT_URI"),
    "site_id":       "MLA"
}
with open("ml_config.json", "w") as f:
    json.dump(config, f, indent=2)
print("ml_config.json OK")

# ml_tokens.json
tokens = {
    "access_token":  "",           # se renovará automáticamente con el refresh_token
    "token_type":    "Bearer",
    "expires_in":    21600,
    "scope":         "offline_access read write",
    "user_id":       int(env("ML_USER_ID")),
    "refresh_token": env("ML_REFRESH_TOKEN"),
    "expires_at":    0             # forzar refresh inmediato
}
with open("ml_tokens.json", "w") as f:
    json.dump(tokens, f, indent=2)
print("ml_tokens.json OK")

# ml_email_config.json
email_cfg = {
    "smtp_host":     env("SMTP_HOST"),
    "smtp_port":     env("SMTP_PORT"),
    "smtp_user":     env("SMTP_USER"),
    "smtp_password": env("SMTP_PASSWORD"),
    "from_name":     env("EMAIL_FROM_NAME"),
    "to":            json.loads(env("EMAIL_TO")),   # JSON array: ["a@b.com","c@d.com"]
    "railway_url":   env("RAILWAY_URL"),
    "railway_update_key": env("RAILWAY_UPDATE_KEY")
}
with open("ml_email_config.json", "w") as f:
    json.dump(email_cfg, f, indent=2)
print("ml_email_config.json OK")

print("Configs reconstruidas exitosamente.")
