from app.schemas.finding import Severity


def finding_priority(severity: Severity, *, published: bool, soon: bool, upcoming: bool) -> int:
    if severity == Severity.error:
        return 1 if published and soon else 2 if published else 3
    if severity == Severity.warning:
        return 4 if upcoming else 5
    return 6
