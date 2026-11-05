"""Pure validation tests for the search filters (FR-017, FR-018) and the shared parsers.

No Flask or database needed. Adjust the import below to however your other tests import schema
(for example `from processing import schema`).
"""
from datetime import datetime
from process import schema
import pytest


def parse(**args):
    return schema.parse_search_filters(args)


def test_no_filters_gives_all_none():
    filters, problem = parse()
    assert problem is None
    assert filters == {"q": None, "category": None, "status": None, "date_from": None, "date_to": None}


def test_blank_and_whitespace_values_count_as_missing():
    filters, problem = parse(q="   ", category="", status=" ", date_from="", date_to=" ")
    assert problem is None
    assert all(v is None for v in filters.values())


def test_query_is_stripped():
    filters, _ = parse(q="  leaking tap ")
    assert filters["q"] == "leaking tap"


@pytest.mark.parametrize("status", ["submitted", "assigned", "in_progress", "resolved", "closed"])
def test_every_real_status_is_accepted(status):
    filters, problem = parse(status=status)
    assert problem is None and filters["status"] == status


@pytest.mark.parametrize("status", ["In_Progress", "IN_PROGRESS", "in progress", "open", "x"])
def test_invalid_or_wrongly_cased_status_is_rejected(status):
    filters, problem = parse(status=status)
    assert filters is None and "Invalid status filter" in problem


@pytest.mark.parametrize("bad", ["05-11-2026", "2026/11/05", "2026-13-01", "2026-02-30", "tomorrow", "2026-11"])
@pytest.mark.parametrize("field", ["date_from", "date_to"])
def test_malformed_dates_are_rejected(field, bad):
    filters, problem = parse(**{field: bad})
    assert filters is None and "Invalid date format" in problem


def test_date_from_is_start_of_day():
    filters, _ = parse(date_from="2026-11-05")
    assert filters["date_from"] == datetime(2026, 11, 5, 0, 0, 0)


def test_date_to_includes_the_whole_day():
    # A complaint raised at 15:30 on 2026-11-05 must match date_to=2026-11-05.
    filters, _ = parse(date_to="2026-11-05")
    assert filters["date_to"] == datetime(2026, 11, 5, 23, 59, 59)
    assert datetime(2026, 11, 5, 15, 30) <= filters["date_to"]
    assert not datetime(2026, 11, 6, 0, 0, 0) <= filters["date_to"]


def test_same_day_range_is_allowed():
    filters, problem = parse(date_from="2026-11-05", date_to="2026-11-05")
    assert problem is None
    assert filters["date_from"] < filters["date_to"]


def test_reversed_range_is_rejected():
    filters, problem = parse(date_from="2026-11-06", date_to="2026-11-05")
    assert filters is None and "date_from" in problem


def test_filters_combine():
    filters, problem = parse(q="lift", category="c1", status="assigned",
                             date_from="2026-11-01", date_to="2026-11-30")
    assert problem is None
    assert filters["q"] == "lift" and filters["category"] == "c1" and filters["status"] == "assigned"


# ---- the parsers the detail page relies on

def test_status_update_accepts_keys_the_page_sends():
    parsed, problem = schema.parse_status_update(
        {"status": "resolved", "remarks": " done ", "resolution_details": " replaced washer "}
    )
    assert problem is None
    assert parsed == {"status": "resolved", "remarks": "done", "resolution_details": "replaced washer"}


@pytest.mark.parametrize("value", [123, ["a"], {"a": 1}, True])
@pytest.mark.parametrize("field", ["remarks", "resolution_details"])
def test_non_string_text_fields_are_rejected(field, value):
    parsed, problem = schema.parse_status_update({"status": "resolved", field: value})
    assert parsed is None and "must be a string" in problem


def test_blank_resolution_details_count_as_missing():
    parsed, _ = schema.parse_status_update({"status": "resolved", "resolution_details": "   "})
    assert parsed["resolution_details"] is None


def test_length_limits_are_inclusive():
    ok, problem = schema.parse_status_update(
        {"status": "resolved", "remarks": "a" * schema.MAX_REMARKS,
         "resolution_details": "b" * schema.MAX_RESOLUTION_DETAILS})
    assert problem is None
    _, problem = schema.parse_status_update({"status": "resolved", "remarks": "a" * (schema.MAX_REMARKS + 1)})
    assert "at most" in problem
    _, problem = schema.parse_status_update(
        {"status": "resolved", "resolution_details": "b" * (schema.MAX_RESOLUTION_DETAILS + 1)})
    assert "at most" in problem


def test_closure_notes_limit_and_type():
    assert schema.parse_close({"closure_notes": "thanks"}) == ("thanks", None)
    assert schema.parse_close({})[1] is None
    assert "at most" in schema.parse_close({"closure_notes": "x" * (schema.MAX_REMARKS + 1)})[1]
    assert "string" in schema.parse_close({"closure_notes": 5})[1]


@pytest.mark.parametrize("value", ["true", 1, "yes", None])
def test_only_json_true_confirms_closure(value):
    assert schema.is_confirmed({"confirmation": value}) is False
    assert schema.is_confirmed({}) is False
    assert schema.is_confirmed({"confirmation": True}) is True


def test_staff_can_only_make_the_two_forward_moves():
    allowed = {(o, n) for o in schema.STATUSES for n in schema.STATUSES if schema.can_transition(o, n)}
    assert allowed == {("assigned", "in_progress"), ("in_progress", "resolved")}