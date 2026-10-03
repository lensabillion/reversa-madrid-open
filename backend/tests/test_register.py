"""The Transparency Register connector, on small files shaped like the real export."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from influence.repositories.register import (
    RegisterEntry,
    RegisterError,
    country_iso3,
    iter_register,
    register_export_date,
    to_actor,
)

# The real export declares XML 1.1, namespaces only its root, and resets the namespace below.
HEAD = (
    "<?xml version='1.1' encoding='UTF-8'?>\n"
    '<ListOfIRPublicDetail xmlns="http://intragate.ec.europa.eu/transparencyregister/odp">\n'
)
METADATA = (
    '  <metaData xmlns="">\n'
    "    <exportDate>2026-10-02T20:00:00.070+00:00</exportDate>\n"
    "    <numberOfIR>2</numberOfIR>\n"
    "  </metaData>\n"
)
TAIL = "</ListOfIRPublicDetail>\n"


def representative(
    code: str,
    name: str,
    *,
    extra_name: str = "",
    fields: str = "",
    closed_year: str = "",
) -> str:
    return (
        "    <interestRepresentative>\n"
        f"      <identificationCode>{code}</identificationCode>\n"
        f"      <name>\n        <originalName>{name}</originalName>{extra_name}\n      </name>\n"
        f"{fields}"
        f"      <financialData>\n        <closedYear>{closed_year}</closedYear>\n"
        "      </financialData>\n"
        "    </interestRepresentative>\n"
    )


def costs(inner: str, currency: str = "€") -> str:
    return f'<costs type="CostRange" currency="{currency}">{inner}</costs>'


def export(*entries: str, metadata: str = METADATA, container: bool = True) -> str:
    body = "".join(entries)
    if container:
        body = f'  <resultList xmlns="">\n{body}  </resultList>\n'
        return f"{HEAD}{metadata}{body}{TAIL}"
    # Without the container the entries sit under the root, which then has no namespace.
    return f"<ListOfIRPublicDetail>{metadata}{body}{TAIL}"


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "register.xml"
    path.write_text(text, encoding="utf-8")
    return path


FULL = representative(
    "880143435725-46",
    "Asociación  Mediterránea\n de Peritos",
    extra_name="\n        <nameInLatinAlphabet>Mediterranean Experts</nameInLatinAlphabet>",
    fields=(
        "      <acronym>ASPERTIC</acronym>\n"
        "      <webSiteURL>http://aspertic.org/</webSiteURL>\n"
        "      <registrationCategory>Trade unions and professional associations"
        "</registrationCategory>\n"
        "      <headOffice>\n        <country>SPAIN</country>\n      </headOffice>\n"
        '      <structure type="Structure">\n'
        "        <isMemberOf>Anti-corruption &#x2;platform&#xd;\n second line</isMemberOf>\n"
        "        <organisationMembers>Member One&#11;Member Two &#x96; ok</organisationMembers>\n"
        "      </structure>\n"
    ),
    closed_year=costs("<range><min>10000</min><max>24999</max></range>"),
)


def test_reads_every_declared_field_of_an_entry(tmp_path: Path) -> None:
    (entry,) = iter_register(write(tmp_path, export(FULL)))

    assert entry == RegisterEntry(
        register_id="880143435725-46",
        name="Asociación Mediterránea de Peritos",
        latin_name="Mediterranean Experts",
        acronym="ASPERTIC",
        category="Trade unions and professional associations",
        country="SPAIN",
        country_code="ESP",
        declared_cost_eur=17499.5,
        declared_cost_raw="min=10000 max=24999 currency=€",
        website="http://aspertic.org/",
        # The control-character references XML 1.0 forbids became spaces; legal ones stayed.
        member_of="Anti-corruption platform second line",
        members="Member One Member Two \x96 ok",
    )


def test_absent_fields_are_none_not_empty(tmp_path: Path) -> None:
    (entry,) = iter_register(write(tmp_path, export(representative("123456-01", "Bare"))))

    assert entry == RegisterEntry(register_id="123456-01", name="Bare")


@pytest.mark.parametrize(
    ("closed_year", "amount", "raw"),
    [
        (costs("<range><max>10000</max></range>"), 5000.0, "max=10000 currency=€"),
        # An open-ended band has no midpoint; the declaration is still reported.
        (costs("<range><min>10000000</min></range>"), None, "min=10000000 currency=€"),
        (costs("<absoluteCost>1234.5</absoluteCost>"), 1234.5, "exact=1234.5 currency=€"),
        (costs("<range><max>lots</max></range>"), None, "max=lots currency=€"),
        (costs("<range><max>10000</max></range>", "$"), None, "max=10000 currency=$"),
        (costs("<range/>"), None, None),
        ("", None, None),
    ],
)
def test_cost_is_a_band_midpoint_beside_the_declaration(
    tmp_path: Path, closed_year: str, amount: float | None, raw: str | None
) -> None:
    text = export(representative("123456-01", "Org", closed_year=closed_year))

    (entry,) = iter_register(write(tmp_path, text))

    assert (entry.declared_cost_eur, entry.declared_cost_raw) == (amount, raw)


def test_total_budget_is_kept_apart_from_lobbying_cost(tmp_path: Path) -> None:
    budget = '<totalBudget currency="€"><absoluteCost>644213</absoluteCost></totalBudget>'
    text = export(representative("123456-01", "NGO", closed_year=budget))

    (entry,) = iter_register(write(tmp_path, text))

    assert (entry.total_budget_eur, entry.declared_cost_eur) == (644213.0, None)


def test_unusable_entries_are_skipped_and_counted(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        export(
            representative("not-an-id", "Bad Id"),
            representative("123456-01", "Good"),
            representative("654321-02", " "),
        ),
    )
    skipped: list[str] = []

    entries = list(iter_register(path, skipped=skipped))

    assert [entry.name for entry in entries] == ["Good"]
    assert len(skipped) == 2
    assert "'not-an-id'" in skipped[0]
    assert "654321-02" in skipped[1]
    # Without a list to fill, skipping still does not stop the stream.
    assert [entry.name for entry in iter_register(path)] == ["Good"]


def test_entries_outside_a_result_list_are_still_read(tmp_path: Path) -> None:
    text = export(
        representative("123456-01", "One"), representative("123457-02", "Two"), container=False
    )

    assert [entry.name for entry in iter_register(write(tmp_path, text))] == ["One", "Two"]


def test_missing_file_is_a_register_error(tmp_path: Path) -> None:
    with pytest.raises(RegisterError, match="Cannot read"):
        list(iter_register(tmp_path / "absent.xml"))


def test_malformed_xml_is_a_register_error(tmp_path: Path) -> None:
    path = write(tmp_path, export(FULL).replace("</acronym>", ""))

    with pytest.raises(RegisterError, match="Cannot read"):
        list(iter_register(path))


def test_truncated_file_is_a_register_error(tmp_path: Path) -> None:
    path = write(tmp_path, export(FULL).removesuffix(TAIL))

    with pytest.raises(RegisterError, match="Cannot read"):
        list(iter_register(path))


def test_a_file_without_entries_is_a_register_error(tmp_path: Path) -> None:
    with pytest.raises(RegisterError, match="No interestRepresentative"):
        list(iter_register(write(tmp_path, export())))


def test_export_date_is_read_from_the_metadata(tmp_path: Path) -> None:
    path = write(tmp_path, export(FULL))

    assert register_export_date(path) == datetime(2026, 10, 2, 20, 0, 0, 70000, tzinfo=UTC)


@pytest.mark.parametrize("entries", [(FULL,), ()])
def test_export_date_is_none_when_the_file_does_not_say(
    tmp_path: Path, entries: tuple[str, ...]
) -> None:
    path = write(tmp_path, export(*entries, metadata=""))

    assert register_export_date(path) is None


def test_unreadable_export_date_is_a_register_error(tmp_path: Path) -> None:
    metadata = '<metaData xmlns=""><exportDate>yesterday</exportDate></metaData>'

    with pytest.raises(RegisterError, match="Unreadable export date 'yesterday'"):
        register_export_date(write(tmp_path, export(FULL, metadata=metadata)))


def test_export_date_of_a_missing_file_is_a_register_error(tmp_path: Path) -> None:
    with pytest.raises(RegisterError, match="Cannot read"):
        register_export_date(tmp_path / "absent.xml")


@pytest.mark.parametrize(
    ("value", "code"),
    [
        (None, None),
        ("BELGIUM", "BEL"),
        (" czech  republic ", "CZE"),
        ("bel", "BEL"),
        ("ATLANTIS", None),
    ],
)
def test_country_names_and_codes_compare_as_iso3(value: str | None, code: str | None) -> None:
    assert country_iso3(value) == code


def test_actor_carries_the_register_identity(tmp_path: Path) -> None:
    (entry,) = iter_register(write(tmp_path, export(FULL)))

    actor = to_actor(entry)

    assert actor.actor_id == "actor:tr:880143435725-46"
    assert (actor.kind, actor.resolution, actor.resolution_score) == (
        "organisation",
        "register_id",
        1.0,
    )
    assert (actor.register_id, actor.country) == ("880143435725-46", "ESP")
    assert (actor.declared_cost_eur, actor.declared_cost_raw) == (
        17499.5,
        "min=10000 max=24999 currency=€",
    )
    assert [(alias.name, alias.source_kind) for alias in actor.aliases] == [
        ("ASPERTIC", "register"),
        ("Asociación Mediterránea de Peritos", "register"),
        ("Mediterranean Experts", "register"),
    ]


def test_actor_keeps_an_unmapped_country_as_declared() -> None:
    actor = to_actor(RegisterEntry(register_id="123456-01", name="Org", country="ATLANTIS"))

    assert actor.country == "ATLANTIS"
    assert [alias.name for alias in actor.aliases] == ["Org"]
