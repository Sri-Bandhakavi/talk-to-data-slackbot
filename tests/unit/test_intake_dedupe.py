from talk_to_data_slackbot.intake.dedupe import InMemoryEventDeduper


def test_new_event_id_is_not_duplicate() -> None:
    deduper = InMemoryEventDeduper()

    assert deduper.is_duplicate("Ev0123456789012345678901") is False


def test_marked_event_id_becomes_duplicate() -> None:
    deduper = InMemoryEventDeduper()
    event_id = "Ev0123456789012345678901"

    deduper.mark(event_id)

    assert deduper.is_duplicate(event_id) is True


def test_mark_is_idempotent() -> None:
    deduper = InMemoryEventDeduper()
    event_id = "Ev0123456789012345678901"

    deduper.mark(event_id)
    deduper.mark(event_id)

    assert deduper.is_duplicate(event_id) is True
