"""Verified source identifiers shared by dashboard counts and creation statistics."""

RECORD_TABLES = {
    "organizations": "organization",
    "venues": "venue",
    "spaces": "space",
    "events": "event",
    "event_dates": "event_date",
    "users": '"user"',
    "partner_requests": "organization_partner_request",
    "team_memberships": "organization_member_link",
    "images": "pluto_image",
}
# Statistics deliberately keeps the seven types in the product reference.
# Membership row creation remains a distinct metric in the existing dashboard.
STATISTICS_SOURCES = {
    "user": (RECORD_TABLES["users"], "created_at", "Benutzer"),
    "organization": (RECORD_TABLES["organizations"], "created_at", "Organisationen"),
    "event": (RECORD_TABLES["events"], "created_at", "Veranstaltungen"),
    "venue": (RECORD_TABLES["venues"], "created_at", "Veranstaltungsorte"),
    "space": (RECORD_TABLES["spaces"], "created_at", "Räume"),
    "partner_request": (RECORD_TABLES["partner_requests"], "created_at", "Partneranfragen"),
    "team_invitation": (RECORD_TABLES["team_memberships"], "invited_at", "Teameinladungen"),
}
