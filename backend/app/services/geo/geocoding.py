"""Deterministic address strategy v1. Importance never participates in matching."""

import hashlib
import json
import math
import re
import unicodedata
from typing import Any
from uuid import uuid4

from app.errors import APIError
from app.schemas.geocode import GeocodeCandidate, GeocodeStatus
from app.services.nominatim import short_text

ADDRESS_FIELDS = ("name", "street", "house_number", "postal_code", "city", "country", "state")
ADDRESS_KEYS = (
    "road",
    "house_number",
    "postcode",
    "city",
    "town",
    "village",
    "municipality",
    "county",
    "state",
    "country",
    "country_code",
)
QUERY_VERSION = SCORING_VERSION = 1
# ISO 3166-1 alpha-2/alpha-3 correspondence. Names limited to verified upstream DE/DA/EN
# country_codes_en_de_da.csv entries for Germany and Denmark; unknown names score zero.
ISO_PAIRS = (
    "ADAND AEARE AFAFG AGATG AIAIA ALALB AMARM AOAGO AQATA ARARG ASASM ATAUT AUAUS AWABW "
    "AXALA AZAZE BABIH BBBRB BDBGD BEBEL BFBFA BGBGR BHBHR BIBDI BJBEN BLBLM BMBMU BNBRN "
    "BOBOL BQBES BRBRA BSBHS BTBTN BVBVT BWBWA BYBLR BZBLZ CACAN CCCCK CDCOD CFCAF CGCOG "
    "CHCHE CICIV CKCOK CLCHL CMCMR CNCHN COCOL CRCRI CUCUB CVCPV CWCUW CXCXR CYCYP CZCZE "
    "DEDEU DJDJI DKDNK DMDMA DODOM DZDZA ECECU EEEST EGEGY EHESH ERERI ESESP ETETH FIFIN "
    "FJFJI FKFLK FMFSM FOFRO FRFRA GAGAB GBGBR GDGRD GEGEO GFGUF GGGGY GHGHA GIGIB GLGRL "
    "GMGMB GNGIN GPGLP GQGNQ GRGRC GSSGS GTGTM GUGUM GWGNB GYGUY HKHKG HMHMD HNHND HRHRV "
    "HTHTI HUHUN IDIDN IEIRL ILISR IMIMN ININD IOIOT IQIRQ IRIRN ISISL ITITA JEJEY JMJAM "
    "JOJOR JPJPN KEKEN KGKGZ KHKHM KIKIR KMCOM KNKNA KPPRK KRKOR KWKWT KYCYM KZKAZ LALAO "
    "LBLBN LCLCA LILIE LKLKA LRLBR LSLSO LTLTU LULUX LVLVA LYLBY MAMAR MCMCO MDMDA MEMNE "
    "MFMAF MGMDG MHMHL MKMKD MLMLI MMMMR MNMNG MOMAC MPMNP MQMTQ MRMRT MSMSR MTMLT MUMUS "
    "MVMDV MWMWI MXMEX MYMYS MZMOZ NANAM NCNCL NENER NFNFK NGNGA NINIC NLNLD NONOR NPNPL "
    "NRNRU NUNIU NZNZL OMOMN PAPAN PEPER PFPYF PGPNG PHPHL PKPAK PLPOL PMSPM PNPCN PRPRI "
    "PSPSE PTPRT PWPLW PYPRY QAQAT REREU ROROU RSSRB RURUS RWRWA SASAU SBSLB SCSYC SDSDN "
    "SESWE SGSGP SHSHN SISVN SJSJM SKSVK SLSLE SMSMR SNSEN SOSOM SRSUR SSSSD STSTP SVSLV "
    "SXSXM SYSYR SZSWZ TCTCA TDTCD TFATF TGTGO THTHA TJTJK TKTKL TLTLS TMTKM TNTUN TOTON "
    "TRTUR TTTTO TVTUV TWTWN TZTZA UAUKR UGUGA UMUMI USUSA UYURY UZUZB VAVAT VCVCT VEVEN "
    "VGVGB VIVIR VNVNM VUVUT WFWLF WSWSM YEYEM YTMYT ZAZAF ZMZMB ZWZWE "
)
COUNTRIES = {
    alias.casefold(): pair[:2].lower()
    for pair in ISO_PAIRS.split()
    for alias in (pair[:2], pair[2:])
}
COUNTRIES.update(
    {
        name: code
        for code, names in {
            "de": ("germany", "deutschland", "tyskland"),
            "dk": ("denmark", "dänemark", "danmark"),
        }.items()
        for name in names
    }
)


def canonical(value: object) -> str:
    return " ".join(unicodedata.normalize("NFC", str(value)).split()) if value is not None else ""


def fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def source_fingerprint(row: dict[str, Any]) -> str:
    extra = "address_addition" if row["entity_type"] == "organization" else "osm_id"
    return fingerprint({key: canonical(row.get(key)) for key in (*ADDRESS_FIELDS, extra)})


def query_inputs(row: dict[str, Any]) -> dict[str, str]:
    street, city, postal = (canonical(row.get(key)) for key in ("street", "city", "postal_code"))
    if not street or not (city or postal):
        return {}
    values = {
        "street": canonical(f"{canonical(row.get('house_number'))} {street}"),
        "city": city,
        "postalcode": postal,
        # Source state is a two-character code without a verified provider mapping.
        # Do not invent a state name or send an ambiguous abbreviation.
    }
    country = canonical(row.get("country"))
    code = COUNTRIES.get(country.casefold())
    if code:
        values["countrycodes"] = code
    elif country:
        values["country"] = country
    return {key: value for key, value in values.items() if value}


def query_fingerprint(row: dict[str, Any], limit: int = 5) -> str:
    return fingerprint(
        {
            "version": QUERY_VERSION,
            "inputs": query_inputs(row),
            "format": "jsonv2",
            "addressdetails": "1",
            "namedetails": "1",
            "limit": limit,
        }
    )


def display_address(row: dict[str, Any]) -> str:
    return ", ".join(
        value
        for value in (
            canonical(f"{canonical(row.get('street'))} {canonical(row.get('house_number'))}"),
            canonical(row.get("address_addition")),
            canonical(f"{canonical(row.get('postal_code'))} {canonical(row.get('city'))}"),
            canonical(row.get("country")),
        )
        if value
    )


def score(row: dict[str, Any], address: dict[str, str]) -> tuple[float, list[str]]:
    total = 0.0
    reasons = []
    country = COUNTRIES.get(canonical(row.get("country")).casefold())
    target_country = canonical(address.get("country_code")).casefold()
    if not country or not target_country:
        reasons.append("country_unknown")
    elif country == target_country:
        total += 0.20
        reasons.append("country_exact")
    else:
        reasons.append("country_mismatch")
    comparisons = (
        ("postal_code", [address.get("postcode")], 0.25),
        ("city", [address.get(k) for k in ("city", "town", "village", "municipality")], 0.20),
        ("street", [address.get("road")], 0.20),
        ("house_number", [address.get("house_number")], 0.15),
    )
    for key, targets, weight in comparisons:
        source = canonical(row.get(key)).casefold()
        normalized = [canonical(target).casefold() for target in targets if target]
        if key == "house_number":
            source = source.replace(" ", "")
            normalized = [v.replace(" ", "") for v in normalized]
        if not source or not normalized:
            reasons.append(key + "_missing")
        elif source in normalized:
            total += weight
            reasons.append(key + "_exact")
        else:
            reasons.append(key + "_mismatch")
    return round(total, 2), reasons


def candidates(
    row: dict[str, Any], results: list[dict[str, Any]], limit: int
) -> list[GeocodeCandidate]:
    values: list[GeocodeCandidate] = []
    seen = set()
    for result in results[:limit]:
        try:
            if isinstance(result.get("lat"), bool) or isinstance(result.get("lon"), bool):
                raise ValueError
            lat, lon = float(result["lat"]), float(result["lon"])
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError
            raw_address = result.get("address", {})
            if not isinstance(raw_address, dict):
                raise ValueError
            address = {
                key: canonical(raw_address[key])[:240]
                for key in ADDRESS_KEYS
                if isinstance(raw_address.get(key), str)
            }
            display = short_text(result.get("display_name"), 1024)
            if not display:
                raise ValueError
            osm_type = result.get("osm_type")
            osm_id: str | None = str(result.get("osm_id", ""))
            if osm_type not in ("node", "way", "relation") or not re.fullmatch(
                r"[1-9][0-9]{0,18}", osm_id or ""
            ):
                osm_type, osm_id = None, None
            identity = (osm_type, osm_id) if osm_id else (lat, lon, display)
            if identity in seen:
                continue
            seen.add(identity)
            importance = result.get("importance")
            if importance is not None:
                importance = float(importance)
                if not math.isfinite(importance):
                    raise ValueError
            match_score, reasons = score(row, address)
            values.append(
                GeocodeCandidate.model_validate(
                    dict(
                        id=uuid4(),
                        rank=len(values) + 1,
                        latitude=lat,
                        longitude=lon,
                        display_name=display,
                        osm_type=osm_type,
                        osm_id=osm_id,
                        provider_class=short_text(result.get("class", result.get("category")), 80),
                        provider_type=short_text(result.get("type"), 80),
                        provider_addresstype=short_text(result.get("addresstype"), 80),
                        provider_importance=importance,
                        match_score=match_score,
                        match_reasons=reasons,
                        address=address,
                    )
                )
            )
        except (KeyError, TypeError, ValueError, OverflowError):
            raise APIError(
                503, "geo_provider_unavailable", "Geo provider is unavailable."
            ) from None
    values.sort(key=lambda item: (-item.match_score, item.rank))
    for rank, item in enumerate(values, 1):
        item.rank = rank
    return values


def result_status(items: list[GeocodeCandidate]) -> GeocodeStatus:
    if not items:
        return "not_found"
    gap = items[0].match_score - items[1].match_score if len(items) > 1 else 1.0
    return "candidate" if items[0].match_score >= 0.75 and round(gap, 2) >= 0.15 else "ambiguous"
