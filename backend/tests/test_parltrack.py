"""The Parltrack connector on tiny dumps written in the exact line format of the real ones."""

import hashlib
import json
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from compression import zstd
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from influence.repositories import parltrack
from influence.repositories.parltrack import ParltrackError, ProcedureEntry
from influence.schemas.atlas import Amendment

RETRIEVED_AT = datetime(2026, 10, 3, 9, 30, tzinfo=UTC)
AI_ACT = "2021/0106(COD)"

type Record = dict[str, object]


def write_lines(path: Path, lines: Sequence[str]) -> Path:
    path.write_bytes(zstd.compress("".join(f"{line}\n" for line in lines).encode()))
    return path


def write_dump(path: Path, records: Sequence[object]) -> Path:
    """One record per line: `[` opens the first, `,` every later one, `]` ends the file."""
    lines = [
        ("[" if index == 0 else ",") + json.dumps(record, ensure_ascii=False)
        for index, record in enumerate(records)
    ]
    return write_lines(path, [*lines, "]"])


# --- iter_dump ----------------------------------------------------------------------------


def test_iter_dump_reads_first_middle_and_last_line_markers(tmp_path: Path) -> None:
    records: list[Record] = [{"n": 1}, {"n": 2, "name": "Dragoş"}, {"n": 3}]
    dump = write_dump(tmp_path / "ep_x.json.zst", records)

    assert list(parltrack.iter_dump(dump)) == records


def test_iter_dump_ignores_blank_lines_and_an_empty_array(tmp_path: Path) -> None:
    spaced = write_lines(tmp_path / "spaced.json.zst", ['[{"n": 1}', "", ',{"n": 2}', "]"])
    empty = write_lines(tmp_path / "empty.json.zst", ["[]"])

    assert list(parltrack.iter_dump(spaced)) == [{"n": 1}, {"n": 2}]
    assert list(parltrack.iter_dump(empty)) == []


def test_iter_dump_prefilter_parses_only_lines_holding_the_value(tmp_path: Path) -> None:
    # The second line is not JSON at all: it must be dropped before parsing, which is
    # what makes one procedure cheap to pull out of 1.27 million records.
    dump = write_lines(
        tmp_path / "ep_x.json.zst",
        ['[{"reference": "2021/0106(COD)"}', ",not json", ',{"note": "2021/0106(COD)"}', "]"],
    )

    assert list(parltrack.iter_dump(dump, containing=AI_ACT)) == [
        {"reference": AI_ACT},
        {"note": AI_ACT},
    ]


def test_iter_dump_rejects_a_line_that_is_not_an_object(tmp_path: Path) -> None:
    dump = write_lines(tmp_path / "ep_x.json.zst", ["[[1, 2]", "]"])

    with pytest.raises(ParltrackError, match="not a JSON object"):
        list(parltrack.iter_dump(dump))


def test_iter_dump_reports_corrupt_truncated_and_missing_files(tmp_path: Path) -> None:
    garbage = tmp_path / "garbage.json.zst"
    garbage.write_bytes(b"this is not zstd")
    whole = zstd.compress(b'[{"n": 1}\n,{"n": 2}\n]\n')
    truncated = tmp_path / "truncated.json.zst"
    truncated.write_bytes(whole[: len(whole) - 4])
    bad_json = write_lines(tmp_path / "bad.json.zst", ['[{"n": 1', "]"])

    for path in (garbage, truncated, bad_json, tmp_path / "absent.json.zst"):
        with pytest.raises(ParltrackError, match="unreadable Parltrack dump"):
            list(parltrack.iter_dump(path))


# --- dump_source_document -----------------------------------------------------------------


def test_dump_source_document_hashes_the_file_and_names_the_public_dump(tmp_path: Path) -> None:
    dump = write_dump(tmp_path / "ep_amendments.json.zst", [{"n": 1}])

    document = parltrack.dump_source_document(dump, RETRIEVED_AT)

    assert document.document_id == "doc:parltrack:ep_amendments"
    assert document.url == "https://parltrack.org/dumps/ep_amendments.json.zst"
    assert document.sha256 == hashlib.sha256(dump.read_bytes()).hexdigest()
    assert document.source_kind == "parltrack"
    assert document.procedure_id is None
    assert document.published_at is None
    assert document.retrieved_at == RETRIEVED_AT
    assert document.extraction_status == "not_applicable"
    assert document.reuse_terms == "ODbL v1.0 (Parltrack)"


def test_dump_source_document_rejects_other_names_and_missing_files(tmp_path: Path) -> None:
    other = tmp_path / "notes.txt"
    other.write_text("x", encoding="utf-8")

    with pytest.raises(ParltrackError, match="not a Parltrack dump name"):
        parltrack.dump_source_document(other, RETRIEVED_AT)
    with pytest.raises(ParltrackError, match="unreadable Parltrack dump"):
        parltrack.dump_source_document(tmp_path / "ep_absent.json.zst", RETRIEVED_AT)


# --- Catalog ------------------------------------------------------------------------------


def ai_act_dossier() -> Record:
    """Shaped like the real 2021/0106(COD) dossier, cut down to the fields that are read."""
    return {
        "procedure": {
            "reference": AI_ACT,
            "title": " Artificial Intelligence Act ",
            "subject": {"3.30.06": "Information technologies", "3.40.06": None},
            "stage_reached": "Procedure completed",
            "final": {
                "title": "Regulation 2024/1689",
                "url": "https://eur-lex.europa.eu/smartapi/cgi/sga_doc?smartapi!celexplus!prod!CELEXnumdoc&lg=EN&numdoc=32024R1689",
            },
        },
        "committees": [
            "not a committee",
            {"type": "Committee Opinion", "committee": "ENVI", "rapporteur": [{"name": "X Y"}]},
            {
                "type": "Joint Responsible Committee",
                "committee": ["IMCO", "LIBE"],
                "rapporteur": [
                    {"name": "BENIFEI Brando", "mepref": 124867},
                    {"mepref": 1},
                    {"name": "TUDORACHE Dragoş"},
                ],
            },
        ],
        "events": [
            {
                "date": "2021-04-21T00:00:00",
                "type": "Legislative proposal published",
                "docs": [{"title": "COM(2021)0206"}, {"title": "EUR-Lex"}, {"url": "x"}],
            },
            {"date": "2020-01-01T00:00:00", "type": "Initial legislative proposal published"},
            {
                "date": "not a date",
                "type": "Vote in committee",
                "docs": [{"title": "COM(2021)0206"}],
            },
            {"type": "Debate in Parliament"},
            {"date": "2024-03-13T00:00:00", "type": "Decision by Parliament, 1st reading"},
            {"date": "2024-06-13T00:00:00", "type": "End of procedure in Parliament"},
            {"date": "2024-07-12T00:00:00", "type": "Final act published in Official Journal"},
        ],
        "docs": [{"date": "2025-01-02T00:00:00"}, {"type": "undated"}],
    }


def dossier(reference: object, **procedure: object) -> Record:
    return {"procedure": {"reference": reference, "title": "A title", **procedure}}


def test_build_catalog_reads_every_field_of_a_full_dossier(tmp_path: Path) -> None:
    dump = write_dump(tmp_path / "ep_dossiers.json.zst", [ai_act_dossier()])

    assert list(parltrack.build_catalog(dump)) == [
        ProcedureEntry(
            procedure_id=AI_ACT,
            title="Artificial Intelligence Act",
            stage_reached="Procedure completed",
            status="completed",
            subjects=("3.30.06 Information technologies",),
            celex_final="32024R1689",
            com_references=("COM(2021)206",),
            lead_committee="IMCO/LIBE",
            rapporteurs=("BENIFEI Brando", "TUDORACHE Dragoş"),
            proposed_on=date(2020, 1, 1),
            completed_on=date(2024, 7, 12),
            last_activity_on=date(2025, 1, 2),
        )
    ]


def test_build_catalog_keeps_unknowns_unknown(tmp_path: Path) -> None:
    dump = write_dump(tmp_path / "ep_dossiers.json.zst", [dossier("2019/2001(INI)")])

    assert list(parltrack.build_catalog(dump)) == [
        ProcedureEntry(
            procedure_id="2019/2001(INI)", title="A title", stage_reached=None, status="unknown"
        )
    ]


@pytest.mark.parametrize(
    ("stage", "status"),
    [
        ("Procedure completed", "completed"),
        ("Procedure completed - delegated act enters into force", "completed"),
        ("Procedure lapsed or withdrawn", "withdrawn"),
        ("Procedure rejected", "withdrawn"),
        ("Awaiting committee decision", "ongoing"),
        ("Preparatory phase in Parliament", "ongoing"),
        ("Something the Observatory invents later", "unknown"),
    ],
)
def test_status_follows_stage_reached(tmp_path: Path, stage: str, status: str) -> None:
    dump = write_dump(
        tmp_path / "ep_dossiers.json.zst", [dossier("2019/2001(INI)", stage_reached=stage)]
    )

    (entry,) = parltrack.build_catalog(dump)

    assert (entry.stage_reached, entry.status) == (stage, status)


def test_completion_date_falls_back_and_needs_a_completed_procedure(tmp_path: Path) -> None:
    ended = {"date": "2020-02-03T00:00:00", "type": "End of procedure in Parliament"}
    records: list[Record] = [
        {**dossier("2019/2001(INI)", stage_reached="Procedure completed"), "events": [ended]},
        {**dossier("2019/2002(INI)", stage_reached="Procedure completed"), "events": "odd"},
        {**dossier("2019/2003(INI)", stage_reached="Awaiting vote"), "events": [ended]},
    ]
    dump = write_dump(tmp_path / "ep_dossiers.json.zst", records)

    entries = list(parltrack.build_catalog(dump))

    assert [entry.completed_on for entry in entries] == [date(2020, 2, 3), None, None]
    assert [entry.last_activity_on for entry in entries] == [
        date(2020, 2, 3),
        None,
        date(2020, 2, 3),
    ]


def test_older_dossier_shapes_are_read(tmp_path: Path) -> None:
    record: Record = {
        **dossier(
            "2008/0001(CNS)",
            subject=["8.70 Budget of the Union"],
            final={"url": "https://eur-lex.europa.eu/no-celex-here"},
        ),
        "committees": [
            {"responsible": False, "committee": "BUDG"},
            {"responsible": True, "committee": [], "rapporteur": "nobody"},
        ],
    }
    untyped_final: Record = dossier("2008/0002(CNS)", final={"url": 7}, subject=3)
    dump = write_dump(tmp_path / "ep_dossiers.json.zst", [record, untyped_final])

    first, second = parltrack.build_catalog(dump)

    assert first.subjects == ("8.70 Budget of the Union",)
    assert (first.celex_final, first.lead_committee, first.rapporteurs) == (None, None, ())
    assert (second.celex_final, second.subjects) == (None, ())


def test_build_catalog_skips_and_counts_dossiers_it_cannot_use(tmp_path: Path) -> None:
    records: list[Record] = [
        {"activities": []},
        {"procedure": "odd"},
        dossier("COM(2019)0308"),
        dossier(None),
        dossier("2019/2001(INI)", title="   "),
        dossier("2019/2002(INI)"),
    ]
    dump = write_dump(tmp_path / "ep_dossiers.json.zst", records)
    skipped: Counter[str] = Counter()

    entries = list(parltrack.build_catalog(dump, skipped))

    assert [entry.procedure_id for entry in entries] == ["2019/2002(INI)"]
    assert skipped == {"no_procedure": 2, "reference_not_a_procedure": 2, "invalid": 1}
    # Without a tally the same dossiers are skipped just as quietly.
    assert len(list(parltrack.build_catalog(dump))) == 1


def test_catalog_round_trips_through_json_lines(tmp_path: Path) -> None:
    dump = write_dump(
        tmp_path / "ep_dossiers.json.zst", [ai_act_dossier(), dossier("2019/2001(INI)")]
    )
    entries = list(parltrack.build_catalog(dump))
    target = tmp_path / "catalog" / "procedures.jsonl"

    assert parltrack.write_catalog(entries, target) == 2

    assert target.read_text(encoding="utf-8").count("\n") == 2
    assert list(parltrack.read_catalog(target)) == entries


def test_read_catalog_reports_unreadable_files(tmp_path: Path) -> None:
    broken = tmp_path / "broken.jsonl"
    broken.write_text('{"procedure_id": "nope"}\n', encoding="utf-8")

    for path in (broken, tmp_path / "absent.jsonl"):
        with pytest.raises(ParltrackError, match="unreadable procedure catalog"):
            list(parltrack.read_catalog(path))


# --- Amendments ---------------------------------------------------------------------------


def committee_record(**changes: object) -> Record:
    """Shaped like a real `ep_amendments` record of the AI Act."""
    record: Record = {
        "src": "https://www.europarl.europa.eu/doceo/document/ENVI-AM-704585_EN.pdf",
        "peid": "PE704.585v01-00",
        "reference": AI_ACT,
        "date": "2022-01-25T00:00:00",
        "committee": ["ENVI"],
        "seq": 68,
        "id": "PE704.585-68",
        "orig_lang": "EN",
        "old": ["(1) The purpose of this", "Regulation is to"],
        "new": ["(1) The purpose of this", "Regulation is not to"],
        "authors": "  César Luena,  Javi   López, ,Margrete Auken on behalf of the Verts/ALE Group",
        "meps": [197721, None, 125042],
        "location": [["Proposal for a regulation", "Recital 1"]],
        "justification": "     Clearer.\n",
        "meta": {"created": "2022-02-24T00:23:49"},
    }
    return {**record, **changes}


def without(record: Record, *keys: str) -> Record:
    return {key: value for key, value in record.items() if key not in keys}


def test_committee_amendment_maps_every_field(tmp_path: Path) -> None:
    dump = write_dump(tmp_path / "ep_amendments.json.zst", [committee_record()])

    assert list(parltrack.committee_amendments(dump, AI_ACT, RETRIEVED_AT)) == [
        Amendment(
            amendment_id="am:2021-0106-COD:ENVI:PE704.585-68",
            procedure_id=AI_ACT,
            document_id="doc:parltrack:ep_amendments",
            stage="committee",
            committee="ENVI",
            number=68,
            author_ids=("actor:mep:197721", "actor:mep:125042"),
            author_names=(
                "César Luena",
                "Javi López",
                "Margrete Auken on behalf of the Verts/ALE Group",
            ),
            tabled_on=date(2022, 1, 25),
            target_provision="Proposal for a regulation - Recital 1",
            old_text="(1) The purpose of this\nRegulation is to",
            new_text="(1) The purpose of this\nRegulation is not to",
            justification="Clearer.",
            language="en",
        )
    ]


@pytest.mark.parametrize(
    ("name", "read"),
    [
        ("ep_amendments", parltrack.committee_amendments),
        ("ep_plenary_amendments", parltrack.plenary_amendments),
    ],
)
def test_an_amendment_cites_the_dump_it_was_read_from(
    tmp_path: Path, name: str, read: Callable[..., Iterator[Amendment]]
) -> None:
    dump = write_dump(tmp_path / f"{name}.json.zst", [committee_record()])

    (amendment,) = read(dump, AI_ACT, RETRIEVED_AT)

    # The join a graph or evidence card makes: the cited document is a retrieved, hashed one.
    assert amendment.document_id == parltrack.dump_source_document(dump, RETRIEVED_AT).document_id


def test_plenary_amendment_keeps_the_responsible_committee_out_of_the_id(tmp_path: Path) -> None:
    record: Record = {
        "src": "https://www.europarl.europa.eu/doceo/document/A-9-2023-0188-AM-001-771_EN.pdf",
        "reference": AI_ACT,
        "date": "2023-06-07T00:00:00",
        "seq": "2",
        "id": "A9-0188/2023-2",
        "new": ["Having regard to the opinion of the", "European Central Bank,"],
        "location": ["Citation 4 a (new)", "  ", ["Annex", "point 1"], 7],
        "committee": "IMCO",
    }
    dump = write_dump(tmp_path / "ep_plenary_amendments.json.zst", [record])

    (amendment,) = parltrack.plenary_amendments(dump, AI_ACT, RETRIEVED_AT)

    assert amendment.amendment_id == "am:2021-0106-COD:PLENARY:A9-0188-2023-2"
    assert amendment.document_id == "doc:parltrack:ep_plenary_amendments"
    assert (amendment.stage, amendment.committee, amendment.number) == ("plenary", "IMCO", 2)
    assert amendment.target_provision == "Citation 4 a (new); Annex - point 1"
    assert amendment.old_text is None
    assert amendment.new_text == "Having regard to the opinion of the\nEuropean Central Bank,"
    assert (amendment.author_ids, amendment.author_names) == ((), ())
    assert (amendment.justification, amendment.language) == (None, None)


def test_unknown_original_differs_from_a_known_empty_one(tmp_path: Path) -> None:
    records = [
        without(committee_record(id="PE1-1"), "old"),
        committee_record(id="PE1-2", old=[]),
        without(committee_record(id="PE1-3", old=["Deleted wording"]), "new"),
    ]
    dump = write_dump(tmp_path / "ep_amendments.json.zst", records)

    unknown, insertion, deletion = parltrack.committee_amendments(dump, AI_ACT, RETRIEVED_AT)

    assert unknown.old_text is None
    assert insertion.old_text == ""
    assert (deletion.old_text, deletion.new_text) == ("Deleted wording", "")


def test_odd_dates_numbers_and_committees_stay_unknown(tmp_path: Path) -> None:
    records = [
        committee_record(id="PE1-1", date="25/01/2022", seq="Amendment1", location=[]),
        without(
            committee_record(id="PE1-2", seq=-1, authors=["Tiemo WÖLKEN"]), "date", "committee"
        ),
        committee_record(id="PE1-3", seq=None, committee=["IMCO", "LIBE"], location="odd"),
    ]
    dump = write_dump(tmp_path / "ep_amendments.json.zst", records)

    first, second, third = parltrack.committee_amendments(dump, AI_ACT, RETRIEVED_AT)

    assert (first.tabled_on, first.number, first.target_provision) == (None, None, None)
    assert (second.tabled_on, second.number, second.committee) == (None, None, None)
    assert second.amendment_id == "am:2021-0106-COD:UNKNOWN:PE1-2"
    assert second.author_names == ("Tiemo WÖLKEN",)
    assert (third.committee, third.number) == ("IMCO/LIBE", None)
    assert third.amendment_id == "am:2021-0106-COD:IMCO-LIBE:PE1-3"


def test_amendments_of_other_procedures_are_not_returned(tmp_path: Path) -> None:
    records = [
        committee_record(reference="2020/0361(COD)"),
        # The reference appears in the text, so the line passes the prefilter.
        committee_record(reference="2020/0361(COD)", justification=f"See {AI_ACT}", id=AI_ACT),
        committee_record(),
    ]
    dump = write_dump(tmp_path / "ep_amendments.json.zst", records)
    skipped: Counter[str] = Counter()

    amendments = list(parltrack.committee_amendments(dump, AI_ACT, RETRIEVED_AT, skipped))

    assert [amendment.amendment_id for amendment in amendments] == [
        "am:2021-0106-COD:ENVI:PE704.585-68"
    ]
    assert skipped == {}
    assert list(parltrack.committee_amendments(dump, "2019/0001(COD)", RETRIEVED_AT)) == []


def test_unusable_amendments_are_skipped_and_counted(tmp_path: Path) -> None:
    records = [
        without(committee_record(), "id"),
        without(committee_record(id="PE1-1"), "old", "new"),
        committee_record(id="PE1-2", old=["  "], new=[]),
        committee_record(id="///"),
        committee_record(),
        committee_record(new=["A second record under the same identifier"]),
    ]
    dump = write_dump(tmp_path / "ep_amendments.json.zst", records)
    skipped: Counter[str] = Counter()

    amendments = list(parltrack.committee_amendments(dump, AI_ACT, RETRIEVED_AT, skipped))

    assert [amendment.new_text for amendment in amendments] == [
        "(1) The purpose of this\nRegulation is not to"
    ]
    assert skipped == {"no_id": 1, "no_text": 2, "invalid": 1, "duplicate_id": 1}
    assert len(list(parltrack.committee_amendments(dump, AI_ACT, RETRIEVED_AT))) == 1


# --- Members ------------------------------------------------------------------------------


def mep_record(mep_id: object, name: object = "Brando BENIFEI") -> Record:
    """Shaped like a real `ep_meps` record: spells are not in date order in the dump."""
    return {
        "UserID": mep_id,
        "Name": {"full": name, "family": "BENIFEI"},
        "Groups": [
            {"groupid": "S&D", "start": "2024-07-16T00:00:00", "end": "9999-12-31T00:00:00"},
            {"groupid": "PSE", "start": "2014-07-01T00:00:00", "end": "2019-07-01T00:00:00"},
            {"Organization": "No identifier", "start": "9999-01-01T00:00:00"},
        ],
        "Constituencies": [
            {"country": "Italy", "start": "2019-07-02T00:00:00", "end": "2024-07-15T00:00:00"},
            None,
            {"country": "Malta", "start": "2014-07-01T00:00:00"},
        ],
        "changes": {"2012-03-09T18:01:40": []},
    }


def test_mep_actors_returns_only_the_requested_members(tmp_path: Path) -> None:
    records: list[Record] = [
        mep_record(1, "Someone ELSE"),
        mep_record("124867"),
        mep_record(124867),
        {"UserID": 197665, "Name": {"full": " Dragoş TUDORACHE "}},
        mep_record(2, "Never REACHED"),
    ]
    dump = write_dump(tmp_path / "ep_meps.json.zst", records)

    first, second = parltrack.mep_actors(dump, [124867, 197665])

    assert first.model_dump(exclude_defaults=True) == {
        "actor_id": "actor:mep:124867",
        "kind": "mep",
        "name": "Brando BENIFEI",
        "mep_id": 124867,
        "country": "Italy",
        "political_group": "S&D",
        "resolution": "mep_id",
    }
    assert (second.name, second.country, second.political_group) == ("Dragoş TUDORACHE", None, None)


def test_mep_actors_skips_and_counts_members_it_cannot_describe(tmp_path: Path) -> None:
    records: list[Record] = [mep_record(7, None), mep_record(0), mep_record(8)]
    dump = write_dump(tmp_path / "ep_meps.json.zst", records)
    skipped: Counter[str] = Counter()

    # 99 is absent from the dump, so the reader runs to the end of the file.
    actors = list(parltrack.mep_actors(dump, {7, 0, 8, 99}, skipped))

    assert [actor.mep_id for actor in actors] == [8]
    assert skipped == {"no_name": 1, "invalid": 1}
    assert list(parltrack.mep_actors(dump, [])) == []


def switcher(mep_id: int = 197000) -> Record:
    """A Member who moved from Renew to the EPP in July 2024."""
    return {
        "UserID": mep_id,
        "Name": {"full": "Some MEP"},
        "Groups": [
            {"groupid": "Renew", "start": "2019-07-02T00:00:00", "end": "2024-07-15T00:00:00"},
            {"groupid": "EPP", "start": "2024-07-15T00:00:00", "end": "9999-12-31T00:00:00"},
            {"groupid": "NI", "start": None, "end": None},
        ],
    }


def test_a_member_keeps_every_group_spell_and_the_group_on_a_day_is_the_one_then(
    tmp_path: Path,
) -> None:
    dump = write_dump(tmp_path / "ep_meps.json.zst", [switcher()])

    (member,) = parltrack.mep_members(dump, [197000])

    # The actor shows the latest group; an amendment tabled in 2022 was tabled by Renew.
    assert member.actor.political_group == "EPP"
    spells = member.groups
    assert parltrack.group_on(spells, date(2022, 1, 25)) == "Renew"
    assert parltrack.group_on(spells, date(2025, 1, 1)) == "EPP"
    # The day both spells cover: the one that started last wins, not the undated one.
    assert parltrack.group_on(spells, date(2024, 7, 15)) == "EPP"
    assert parltrack.group_on(spells, None) is None
    assert parltrack.group_on(spells[:2], date(2010, 1, 1)) is None
    assert parltrack.group_on(spells[2:], date(2010, 1, 1)) == "NI"


def test_author_groups_align_with_the_authors_and_stay_out_of_json_when_empty(
    tmp_path: Path,
) -> None:
    dump = write_dump(tmp_path / "ep_amendments.json.zst", [committee_record()])
    (amendment,) = parltrack.committee_amendments(dump, AI_ACT, RETRIEVED_AT)
    # Written before the field existed: the bytes, and so the stage hashes, are unchanged.
    assert "author_groups" not in amendment.model_dump_json()
    annotated = amendment.model_copy(update={"author_groups": ("Renew", None)})
    assert Amendment.model_validate_json(annotated.model_dump_json()) == annotated
    with pytest.raises(ValueError, match="align with author_ids"):
        Amendment.model_validate({**amendment.model_dump(), "author_groups": ["Renew"]})


def test_lone_surrogates_are_replaced_so_the_records_can_be_written(tmp_path: Path) -> None:
    record = committee_record(
        new=["Emoji half \ud83d here"], authors="Name \udc00 X", justification="J \ud800"
    )
    # Escaped as JSON writes it: the dump holds `\ud83d`, which decodes to a lone surrogate.
    dump = write_lines(tmp_path / "ep_amendments.json.zst", ["[" + json.dumps(record), "]"])

    (amendment,) = parltrack.committee_amendments(dump, AI_ACT, RETRIEVED_AT)

    assert amendment.new_text == "Emoji half � here"
    assert amendment.author_names == ("Name � X",)
    assert amendment.justification == "J �"
    assert amendment.model_dump_json().encode("utf-8")


def test_latest_date_is_how_far_a_dump_reaches(tmp_path: Path) -> None:
    dump = write_dump(
        tmp_path / "ep_amendments.json.zst",
        [committee_record(), committee_record(id="X", date="2026-09-01T00:00:00"), {"id": 1}],
    )
    assert parltrack.latest_date(dump) == date(2026, 9, 1)
    assert parltrack.latest_date(write_dump(tmp_path / "none.json.zst", [{"id": 1}])) is None
    with pytest.raises(ParltrackError, match="unreadable Parltrack dump"):
        parltrack.latest_date(tmp_path / "absent.json.zst")
