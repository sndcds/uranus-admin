"""Complete deterministic catalogues, with whole-message English fallback."""

from datetime import date

from app.schemas.notifications import Locale

CATALOGUE: dict[str, dict[str, str]] = {
    "de": {
        "hello": "Hallo,",
        "single": "Deine Veranstaltung „{title}“ findet bald statt",
        "multiple": "{count} deiner Veranstaltungen finden bald statt",
        "quality_one": "Ein Hinweis zu deinen Kulturbytes-Einträgen",
        "quality_many": "{count} Hinweise zu deinen Kulturbytes-Einträgen",
        "intro": (
            "Deine Veranstaltung „{title}“ findet am {date} statt und ist aktuell als "
            "{status} gespeichert."
        ),
        "publish": (
            "Damit sie rechtzeitig auf Kulturbytes sichtbar wird, kannst du die Angaben "
            "noch einmal prüfen und sie veröffentlichen, sobald alles bereit ist."
        ),
        "intentional": (
            "Wenn der aktuelle Status bewusst so gewählt ist, musst du nichts weiter tun."
        ),
        "today": "Deine Veranstaltung findet heute statt.",
        "tomorrow": "Deine Veranstaltung findet bereits morgen statt.",
        "days": "Deine Veranstaltung findet in {count} Tagen statt.",
        "event_action": "Veranstaltung bearbeiten",
        "venue_action": "Veranstaltungsort bearbeiten",
        "organization_action": "Organisation bearbeiten",
        "space_action": "Raum bearbeiten",
        "action_guidance": (
            "Melde dich bei Kulturbytes an und öffne den entsprechenden Eintrag "
            "in deinem Dashboard."
        ),
        "footer": (
            "Du erhältst diese Nachricht, weil diese E-Mail-Adresse für "
            "Benachrichtigungen der Organisation „{organization}“ in Kulturbytes "
            "hinterlegt ist."
        ),
        "draft": "Entwurf",
        "review": "In Prüfung",
        "event": "Veranstaltung",
        "event_date": "Veranstaltungstermin",
        "event_link": "Veranstaltung",
        "venue": "Veranstaltungsort",
        "organization": "Organisation",
        "space": "Raum",
        "ticket_link": "Ticket-Link",
        "registration_link": "Anmelde-Link",
        "online_link": "Online-Link",
        "web_link": "Website",
        "source_link": "Quell-Link",
        "url": "Link",
        "link_title": "{field} prüfen",
        "urgent": "Der Termin steht kurz bevor.",
        "important": "Dieser Hinweis betrifft einen bevorstehenden Termin.",
        "event_without_dates.title": "Termin fehlt",
        "event_without_dates.explanation": (
            "Für diese Veranstaltung ist aktuell noch kein Termin hinterlegt."
        ),
        "event_without_dates.recommendation": (
            "Ergänze mindestens einen Termin, damit Besucherinnen und Besucher sehen "
            "können, wann die Veranstaltung stattfindet."
        ),
        "event_without_location.title": "Veranstaltungsort ergänzen",
        "event_without_location.explanation": (
            "Für diese Veranstaltung ist aktuell kein Ort und keine gültige "
            "Online-Alternative hinterlegt."
        ),
        "event_without_location.recommendation": (
            "Ergänze einen Veranstaltungsort oder eine gültige Online-Adresse, damit "
            "Besucherinnen und Besucher wissen, wo die Veranstaltung stattfindet."
        ),
        "event_date_without_location.title": "Ort für einen Termin ergänzen",
        "event_date_without_location.explanation": (
            "Für diesen Termin ist aktuell kein gültiger Ort hinterlegt."
        ),
        "event_date_without_location.recommendation": (
            "Ergänze für den Termin einen gültigen Veranstaltungsort oder eine Online-Alternative."
        ),
        "url_syntax.title": "Link prüfen",
        "url_syntax.explanation": (
            "Ein hinterlegter Link scheint kein gültiges URL-Format zu haben."
        ),
        "url_syntax.recommendation": "Prüfe die Adresse und speichere sie erneut.",
        "venue_missing_logo.title": "Logo ergänzen",
        "venue_missing_logo.explanation": (
            "Für „{name}“ ist aktuell noch kein Hauptlogo hinterlegt."
        ),
        "venue_missing_logo.recommendation": (
            "Ein gut erkennbares Logo macht den Veranstaltungsort auf Kulturbytes "
            "leichter wiedererkennbar."
        ),
        "organization_missing_logo.title": "Logo ergänzen",
        "organization_missing_logo.explanation": (
            "Für „{name}“ ist aktuell noch kein Hauptlogo hinterlegt."
        ),
        "organization_missing_logo.recommendation": (
            "Ein gut erkennbares Logo macht deine Organisation auf Kulturbytes leichter "
            "wiedererkennbar."
        ),
    },
    "da": {
        "hello": "Hej,",
        "single": "Dit arrangement „{title}“ finder snart sted",
        "multiple": "{count} af dine arrangementer finder snart sted",
        "quality_one": "Et forslag til dine opslag på Kulturbytes",
        "quality_many": "{count} forslag til dine opslag på Kulturbytes",
        "intro": (
            "Dit arrangement „{title}“ finder sted den {date} og har stadig status „{status}“."
        ),
        "publish": (
            "Du kan gennemgå oplysningerne og offentliggøre arrangementet, når det hele "
            "er klar, så det bliver synligt på Kulturbytes i god tid."
        ),
        "intentional": (
            "Hvis du bevidst har valgt den nuværende status, behøver du ikke gøre noget."
        ),
        "today": "Dit arrangement finder sted i dag.",
        "tomorrow": "Dit arrangement finder allerede sted i morgen.",
        "days": "Dit arrangement finder sted om {count} dage.",
        "event_action": "Rediger arrangementet",
        "venue_action": "Rediger arrangementsstedet",
        "organization_action": "Rediger organisationen",
        "space_action": "Rediger lokalet",
        "action_guidance": ("Log ind på Kulturbytes, og åbn det relevante opslag i dit dashboard."),
        "footer": (
            "Du modtager denne besked, fordi denne e-mailadresse er tilmeldt "
            "notifikationer for organisationen „{organization}“ på Kulturbytes."
        ),
        "draft": "kladde",
        "review": "under gennemgang",
        "event": "Arrangement",
        "event_date": "Arrangementsdato",
        "event_link": "Arrangement",
        "venue": "Arrangementssted",
        "organization": "Organisation",
        "space": "Lokale",
        "ticket_link": "Billetlink",
        "registration_link": "Tilmeldingslink",
        "online_link": "Onlinelink",
        "web_link": "Hjemmeside",
        "source_link": "Kildelink",
        "url": "Link",
        "link_title": "Tjek: {field}",
        "urgent": "Arrangementet finder sted meget snart.",
        "important": "Dette forslag vedrører et kommende arrangement.",
        "event_without_dates.title": "Tilføj en dato",
        "event_without_dates.explanation": "Der er endnu ikke angivet en dato for arrangementet.",
        "event_without_dates.recommendation": (
            "Tilføj mindst én dato, så besøgende kan se, hvornår arrangementet finder sted."
        ),
        "event_without_location.title": "Tilføj et arrangementssted",
        "event_without_location.explanation": (
            "Der er hverken angivet et sted eller en gyldig onlineadresse for arrangementet."
        ),
        "event_without_location.recommendation": (
            "Tilføj et arrangementssted eller en gyldig onlineadresse, så besøgende ved, "
            "hvor arrangementet finder sted."
        ),
        "event_date_without_location.title": "Tilføj et sted til datoen",
        "event_date_without_location.explanation": (
            "Der er ikke angivet et gyldigt sted for denne dato."
        ),
        "event_date_without_location.recommendation": (
            "Tilføj et gyldigt arrangementssted eller en onlineadresse for denne dato."
        ),
        "url_syntax.title": "Tjek linket",
        "url_syntax.explanation": (
            "Et af de gemte links ser ikke ud til at have et gyldigt adresseformat."
        ),
        "url_syntax.recommendation": "Tjek adressen, og gem den igen.",
        "venue_missing_logo.title": "Tilføj et logo",
        "venue_missing_logo.explanation": "Der er endnu ikke angivet et hovedlogo for „{name}“.",
        "venue_missing_logo.recommendation": (
            "Et tydeligt logo gør arrangementsstedet lettere at genkende på Kulturbytes."
        ),
        "organization_missing_logo.title": "Tilføj et logo",
        "organization_missing_logo.explanation": (
            "Der er endnu ikke angivet et hovedlogo for „{name}“."
        ),
        "organization_missing_logo.recommendation": (
            "Et tydeligt logo gør din organisation lettere at genkende på Kulturbytes."
        ),
    },
    "en": {
        "hello": "Hello,",
        "single": "Your event “{title}” is coming up soon",
        "multiple": "{count} of your events are coming up soon",
        "quality_one": "One suggestion for your Kulturbytes listings",
        "quality_many": "{count} suggestions for your Kulturbytes listings",
        "intro": "Your event “{title}” takes place on {date} and is currently saved as {status}.",
        "publish": (
            "You can review the details and publish it when everything is ready, so "
            "people can find it on Kulturbytes in time."
        ),
        "intentional": "If the current status is intentional, you do not need to do anything.",
        "today": "Your event takes place today.",
        "tomorrow": "Your event takes place tomorrow.",
        "days": "Your event takes place in {count} days.",
        "event_action": "Edit event",
        "venue_action": "Edit venue",
        "organization_action": "Edit organization",
        "space_action": "Edit room",
        "action_guidance": (
            "Sign in to Kulturbytes and open the relevant entry in your dashboard."
        ),
        "footer": (
            "You are receiving this message because this email address is registered for "
            "notifications for the organization “{organization}” on Kulturbytes."
        ),
        "draft": "Draft",
        "review": "Under review",
        "event": "Event",
        "event_date": "Event date",
        "event_link": "Event",
        "venue": "Venue",
        "organization": "Organization",
        "space": "Room",
        "ticket_link": "Ticket link",
        "registration_link": "Registration link",
        "online_link": "Online link",
        "web_link": "Website",
        "source_link": "Source link",
        "url": "Link",
        "link_title": "Check {field}",
        "urgent": "The event is just around the corner.",
        "important": "This suggestion concerns an upcoming event.",
        "event_without_dates.title": "Add a date",
        "event_without_dates.explanation": "This event does not have a date yet.",
        "event_without_dates.recommendation": (
            "Add at least one date so visitors can see when the event takes place."
        ),
        "event_without_location.title": "Add a venue",
        "event_without_location.explanation": (
            "This event has neither a venue nor a valid online alternative."
        ),
        "event_without_location.recommendation": (
            "Add a venue or a valid online address so visitors know where the event takes place."
        ),
        "event_date_without_location.title": "Add a venue for this date",
        "event_date_without_location.explanation": "No valid venue is specified for this date.",
        "event_date_without_location.recommendation": (
            "Add a valid venue or an online alternative for this date."
        ),
        "url_syntax.title": "Check a link",
        "url_syntax.explanation": "A saved link does not appear to have a valid URL format.",
        "url_syntax.recommendation": "Check the address and save it again.",
        "venue_missing_logo.title": "Add a logo",
        "venue_missing_logo.explanation": "“{name}” does not have a main logo yet.",
        "venue_missing_logo.recommendation": (
            "A clear logo makes the venue easier to recognize on Kulturbytes."
        ),
        "organization_missing_logo.title": "Add a logo",
        "organization_missing_logo.explanation": "“{name}” does not have a main logo yet.",
        "organization_missing_logo.recommendation": (
            "A clear logo makes your organization easier to recognize on Kulturbytes."
        ),
    },
}
MONTHS = {
    "de": (
        "Januar Februar März April Mai Juni Juli August September Oktober November Dezember"
    ).split(),
    "da": (
        "januar februar marts april maj juni juli august september oktober november december"
    ).split(),
    "en": (
        "January February March April May June July August September October November December"
    ).split(),
}


def catalogue(requested: str) -> tuple[Locale, dict[str, str]]:
    # Never combine German/Danish fragments with English. A missing required key falls
    # back the entire message. Tests require exact key parity in released catalogues.
    if requested in {"de", "da"} and CATALOGUE[requested].keys() >= CATALOGUE["en"].keys():
        return ("de" if requested == "de" else "da"), CATALOGUE[requested]
    return "en", CATALOGUE["en"]


def format_date(value: str, locale: Locale) -> str:
    day = date.fromisoformat(value)
    punctuation = "." if locale in {"de", "da"} else ""
    return f"{day.day}{punctuation} {MONTHS[locale][day.month - 1]} {day.year}"
