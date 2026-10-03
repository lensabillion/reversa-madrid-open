"""Stream the EU Transparency Register export into one typed record per organisation.

The register is the only source that gives an organisation a stable identifier (its
`identificationCode`), a category, a head office and a declared lobbying cost. The full
export is one 117 MB XML file of about 18,000 `interestRepresentative` elements, so it is
read as a stream: one entry is alive at a time and memory does not grow with the file.

Three facts about the real file shape this module (measured on the export of 2026-10-02):

- It declares XML 1.1 and holds character references to control characters (`&#x2;`,
  `&#xb;`, `&#x1d;`), which XML 1.1 allows and the standard library's XML 1.0 parser
  rejects. Those references are replaced by a space before parsing; nothing else changes.
- The root element is namespaced, but `metaData`, `resultList` and everything below them
  reset the namespace to none, so entry fields are addressed by their plain names.
- A lobbying cost is declared as a band (`costs/range/min` and `max`), never as an exact
  amount. The band is kept exactly as declared beside its midpoint, so a reader can always
  tell an estimate from a declaration.
"""

import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import cast

from pydantic import ValidationError

from influence.schemas.atlas import Actor, ActorAlias, NonEmpty, RegisterId, register_actor_id
from influence.schemas.scoring import FrozenModel

_ENTRY_TAG = "interestRepresentative"
_CONTAINER_TAG = "resultList"
_EXPORT_DATE_TAG = "exportDate"
_EURO = "€"
_CHARACTER_REFERENCE = re.compile(rb"&#(x[0-9a-fA-F]+|[0-9]+);")
_AMOUNT = re.compile(r"\d+(\.\d+)?")
# XML 1.0 allows only these three characters below the space.
_XML_1_0_WHITESPACE = frozenset({0x9, 0xA, 0xD})
_COST_PARTS = (("exact", "absoluteCost"), ("min", "range/min"), ("max", "range/max"))

# The register writes head-office countries as upper-case English names; Have Your Say and
# most other sources write ISO 3166-1 alpha-3 codes. Every name in the 2026-10-02 export
# (139 of them) is listed, so a comparison across sources is made on the code.
REGISTER_COUNTRY_ISO3 = MappingProxyType(
    {
        "ALBANIA": "ALB",
        "ARGENTINA": "ARG",
        "ARMENIA": "ARM",
        "AUSTRALIA": "AUS",
        "AUSTRIA": "AUT",
        "AZERBAIJAN": "AZE",
        "BANGLADESH": "BGD",
        "BELARUS": "BLR",
        "BELGIUM": "BEL",
        "BENIN": "BEN",
        "BERMUDA": "BMU",
        "BOLIVIA": "BOL",
        "BOSNIA-HERZEGOVINA": "BIH",
        "BRAZIL": "BRA",
        "BULGARIA": "BGR",
        "BURKINA FASO": "BFA",
        "CAMBODIA": "KHM",
        "CAMEROON": "CMR",
        "CANADA": "CAN",
        "CAYMAN ISLANDS": "CYM",
        "CHILE": "CHL",
        "CHINA": "CHN",
        "COLOMBIA": "COL",
        "CONGO, DEMOCRATIC REPUBLIC OF": "COD",
        "COSTA RICA": "CRI",
        "COTE D'IVOIRE": "CIV",
        "CROATIA": "HRV",
        "CYPRUS": "CYP",
        "CZECH REPUBLIC": "CZE",
        "DENMARK": "DNK",
        "DOMINICA": "DMA",
        "DOMINICAN REPUBLIC": "DOM",
        "ECUADOR": "ECU",
        "EGYPT": "EGY",
        "EL SALVADOR": "SLV",
        "ESTONIA": "EST",
        "FAROE ISLANDS": "FRO",
        "FINLAND": "FIN",
        "FRANCE": "FRA",
        "GEORGIA": "GEO",
        "GERMANY": "DEU",
        "GHANA": "GHA",
        "GIBRALTAR": "GIB",
        "GREECE": "GRC",
        "GREENLAND": "GRL",
        "GUATEMALA": "GTM",
        "GUINEA": "GIN",
        "GUYANA": "GUY",
        "HONG KONG": "HKG",
        "HUNGARY": "HUN",
        "ICELAND": "ISL",
        "INDIA": "IND",
        "INDONESIA": "IDN",
        "IRELAND": "IRL",
        "ISLE OF MAN": "IMN",
        "ISRAEL": "ISR",
        "ITALY": "ITA",
        "JAPAN": "JPN",
        "JERSEY": "JEY",
        "JORDAN": "JOR",
        "KAZAKHSTAN": "KAZ",
        "KENYA": "KEN",
        "KOREA, REPUBLIC OF": "KOR",
        "KOSOVO (*)": "XKX",
        "LAOS, PEOPLE'S DEMOCRATIC REPUBLIC": "LAO",
        "LATVIA": "LVA",
        "LEBANON": "LBN",
        "LIBERIA": "LBR",
        "LIBYA": "LBY",
        "LIECHTENSTEIN": "LIE",
        "LITHUANIA": "LTU",
        "LUXEMBOURG": "LUX",
        "MACAO": "MAC",
        "MALAYSIA": "MYS",
        "MALI": "MLI",
        "MALTA": "MLT",
        "MARSHALL ISLANDS": "MHL",
        "MARTINIQUE": "MTQ",
        "MAURITIUS": "MUS",
        "MEXICO": "MEX",
        "MOLDOVA, REPUBLIC OF": "MDA",
        "MONACO": "MCO",
        "MONGOLIA": "MNG",
        "MONTENEGRO": "MNE",
        "MOROCCO": "MAR",
        "MOZAMBIQUE": "MOZ",
        "NAMIBIA": "NAM",
        "NEPAL": "NPL",
        "NETHERLANDS": "NLD",
        "NEW CALEDONIA": "NCL",
        "NEW ZEALAND": "NZL",
        "NIGER": "NER",
        "NIGERIA": "NGA",
        "NORTH MACEDONIA": "MKD",
        "NORWAY": "NOR",
        "PAKISTAN": "PAK",
        "PALESTINE (*)": "PSE",
        "PANAMA": "PAN",
        "PAPUA NEW GUINEA": "PNG",
        "PERU": "PER",
        "PHILIPPINES": "PHL",
        "POLAND": "POL",
        "PORTUGAL": "PRT",
        "QATAR": "QAT",
        "REUNION": "REU",
        "ROMANIA": "ROU",
        "RUSSIA, FEDERATION OF": "RUS",
        "RWANDA": "RWA",
        "SAINT LUCIA": "LCA",
        "SAUDI ARABIA": "SAU",
        "SENEGAL": "SEN",
        "SERBIA": "SRB",
        "SEYCHELLES": "SYC",
        "SINGAPORE": "SGP",
        "SLOVAKIA": "SVK",
        "SLOVENIA": "SVN",
        "SOMALIA": "SOM",
        "SOUTH AFRICA": "ZAF",
        "SPAIN": "ESP",
        "SRI LANKA": "LKA",
        "SWEDEN": "SWE",
        "SWITZERLAND": "CHE",
        "TAIWAN": "TWN",
        "TANZANIA, UNITED REPUBLIC OF": "TZA",
        "THAILAND": "THA",
        "TOGO": "TGO",
        "TRINIDAD AND TOBAGO": "TTO",
        "TUNISIA": "TUN",
        "TURKEY": "TUR",
        "UGANDA": "UGA",
        "UKRAINE": "UKR",
        "UNITED ARAB EMIRATES": "ARE",
        "UNITED KINGDOM": "GBR",
        "UNITED STATES": "USA",
        "URUGUAY": "URY",
        "VENEZUELA": "VEN",
        "VIETNAM": "VNM",
        "ZAMBIA": "ZMB",
        "ZIMBABWE": "ZWE",
    }
)
_ISO3_CODES = frozenset(REGISTER_COUNTRY_ISO3.values())


class RegisterError(Exception):
    """The register export could not be read, is not well-formed, or holds no entries."""


class RegisterEntry(FrozenModel):
    """One organisation as the register declares it; an absent field is None, never a guess."""

    register_id: RegisterId
    name: NonEmpty
    # Present for names in another script (Greek, Bulgarian); a second spelling to match on.
    latin_name: str | None = None
    acronym: str | None = None
    category: str | None = None
    # As the register writes it ("BELGIUM"); `country_code` is the ISO-3 code to compare on.
    country: str | None = None
    country_code: str | None = None
    # The midpoint of the declared band: an estimate. `declared_cost_raw` is the declaration.
    declared_cost_eur: float | None = None
    declared_cost_raw: str | None = None
    # Non-governmental organisations declare a total budget instead of a lobbying cost.
    total_budget_eur: float | None = None
    website: str | None = None
    # Free text typed by the registrant (prose, lists, URLs), not a list of identifiers. It
    # is kept for display only and must never be used to merge an association with a member.
    member_of: str | None = None
    members: str | None = None


def country_iso3(value: str | None) -> str | None:
    """The ISO-3 code for a register country name or for a code; None when it is neither."""
    if value is None:
        return None
    key = " ".join(value.upper().split())
    if key in _ISO3_CODES:
        return key
    return REGISTER_COUNTRY_ISO3.get(key)


def _legal_reference(match: re.Match[bytes]) -> bytes:
    token = match.group(1)
    code_point = int(token[1:], 16) if token[:1] == b"x" else int(token)
    if code_point >= 0x20 or code_point in _XML_1_0_WHITESPACE:
        return match.group(0)
    return b" "


def _drain(parser: ET.XMLPullParser[ET.Element]) -> Iterator[tuple[str, ET.Element]]:
    # Only start and end events are requested, and those always carry an element.
    return cast("Iterator[tuple[str, ET.Element]]", parser.read_events())


def _events(path: Path) -> Iterator[tuple[str, ET.Element]]:
    """Parse line by line so a control-character reference can be neutralised before parsing.

    A character reference never spans a line break, so each line is safe to rewrite on its
    own; memory is bounded by the longest line and the open element, not by the file.
    """
    parser: ET.XMLPullParser[ET.Element] = ET.XMLPullParser(("start", "end"))
    try:
        with path.open("rb") as handle:
            for line in handle:
                parser.feed(
                    _CHARACTER_REFERENCE.sub(_legal_reference, line) if b"&#" in line else line
                )
                yield from _drain(parser)
            parser.close()
            yield from _drain(parser)
    except (OSError, ET.ParseError) as error:
        raise RegisterError(
            f"Cannot read the Transparency Register export {path}: {error}"
        ) from error


def _text(element: ET.Element, path: str) -> str | None:
    """Whitespace-collapsed text, with empty and absent both reported as None."""
    return " ".join((element.findtext(path) or "").split()) or None


def _amount(text: str | None) -> float | None:
    if text is None or _AMOUNT.fullmatch(text) is None:
        return None
    return float(text)


def _declared_cost(entry: ET.Element) -> tuple[float | None, str | None]:
    """The closed financial year's lobbying cost: (midpoint in euro, the declaration itself).

    A band with only a ceiling ("under 10,000") runs from zero. A band with only a floor
    ("10,000,000 or more") has no midpoint, so the estimate stays None and the declaration
    still says what was declared. A currency other than the euro is never converted.
    """
    costs = entry.find("financialData/closedYear/costs")
    if costs is None:
        return None, None
    declared = {label: _text(costs, path) for label, path in _COST_PARTS}
    parts = [f"{label}={text}" for label, text in declared.items() if text is not None]
    if not parts:
        return None, None
    currency = costs.get("currency", "")
    raw = " ".join([*parts, f"currency={currency}"])
    if currency != _EURO:
        return None, raw
    exact, low, high = (_amount(declared[label]) for label, _ in _COST_PARTS)
    if exact is not None:
        return exact, raw
    if high is None:
        return None, raw
    return ((low or 0.0) + high) / 2, raw


def _entry(element: ET.Element) -> RegisterEntry:
    country = _text(element, "headOffice/country")
    cost, cost_raw = _declared_cost(element)
    return RegisterEntry(
        register_id=_text(element, "identificationCode") or "",
        name=_text(element, "name/originalName") or "",
        latin_name=_text(element, "name/nameInLatinAlphabet"),
        acronym=_text(element, "acronym"),
        category=_text(element, "registrationCategory"),
        country=country,
        country_code=country_iso3(country),
        declared_cost_eur=cost,
        declared_cost_raw=cost_raw,
        total_budget_eur=_amount(
            _text(element, "financialData/closedYear/totalBudget/absoluteCost")
        ),
        website=_text(element, "webSiteURL"),
        member_of=_text(element, "structure/isMemberOf"),
        members=_text(element, "structure/organisationMembers"),
    )


def iter_register(path: Path, *, skipped: list[str] | None = None) -> Iterator[RegisterEntry]:
    """Yield every organisation in the export, one at a time, in file order.

    An entry whose identifier is malformed or whose name is missing cannot be joined to
    anything, so it is skipped; one line per skipped entry is appended to `skipped`, so the
    caller can report the count. A file with no entry at all raises `RegisterError` once
    the stream ends: an empty register is a wrong file, not a register with nobody in it.

    Linear in the file size. Each finished entry is cleared together with its container, so
    peak memory is one entry (measured: under 1 MB traced for the 117 MB export, 5.5 s).
    """
    log = skipped if skipped is not None else []
    container: ET.Element | None = None
    seen = 0
    for event, element in _events(path):
        if event == "start":
            if element.tag == _CONTAINER_TAG:
                container = element
            continue
        if element.tag != _ENTRY_TAG:
            continue
        seen += 1
        try:
            yield _entry(element)
        except ValidationError:
            log.append(
                f"entry {seen}: unusable id {element.findtext('identificationCode')!r} "
                f"or name {element.findtext('name/originalName')!r}"
            )
        element.clear()
        if container is not None:
            # Clearing only the entry would leave one empty shell per entry in the parent.
            container.clear()
    if seen == 0:
        raise RegisterError(f"No {_ENTRY_TAG} element in the Transparency Register export {path}")


def register_export_date(path: Path) -> datetime | None:
    """When the register produced this export; None when the file does not say.

    The date sits in the metadata block before the first entry, so only the head of the
    file is read.
    """
    for event, element in _events(path):
        if event == "start":
            if element.tag == _ENTRY_TAG:
                break
            continue
        if element.tag == _EXPORT_DATE_TAG:
            try:
                return datetime.fromisoformat((element.text or "").strip())
            except ValueError as error:
                raise RegisterError(f"Unreadable export date {element.text!r} in {path}") from error
    return None


def to_actor(entry: RegisterEntry) -> Actor:
    """The register's own identity for an organisation: keyed by its ID, certain by definition."""
    names = sorted({entry.name, *filter(None, (entry.latin_name, entry.acronym))})
    return Actor(
        actor_id=register_actor_id(entry.register_id),
        kind="organisation",
        name=entry.name,
        register_id=entry.register_id,
        category=entry.category,
        # The ISO-3 code where the name is known, so sources compare; else the name as given.
        country=entry.country_code or entry.country,
        declared_cost_eur=entry.declared_cost_eur,
        declared_cost_raw=entry.declared_cost_raw,
        aliases=tuple(ActorAlias(name=name, source_kind="register") for name in names),
        resolution="register_id",
        resolution_score=1.0,
    )
