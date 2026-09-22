"""Canonical admin-only Uranus user label: display_name → username → email → UUID."""

# Fixed source alias u; never interpolate identifiers from request data.
# Blank strings are missing. Admin account/actor identities are separate.
USER_DISPLAY_LABEL_SQL = (
    "COALESCE(NULLIF(u.display_name,''),NULLIF(u.username,''),NULLIF(u.email,''),u.uuid::text)"
)
