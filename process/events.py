"""Lifecycle event seam for the Notification module (no notification logic lives here).

After a status change is committed, the Processing routes call publish(). The Notification
module registers a listener once at start-up and decides who is told what:

    from process.events import subscribe
    subscribe(my_notification_handler)   # handler(event: dict) -> None

Event payload: {"event": "COMPLAINT_STATUS_CHANGED", "complaint_id", "old_status",
"new_status", "actor_id", "remarks"}. With no listener registered this is a no-op. A failing
listener is logged and swallowed: a notification problem must never undo a committed change.
"""
import logging

log = logging.getLogger(__name__)
STATUS_CHANGED = "COMPLAINT_STATUS_CHANGED"

_listeners = []


def subscribe(listener):
    if listener not in _listeners:
        _listeners.append(listener)


def unsubscribe(listener):
    if listener in _listeners:
        _listeners.remove(listener)


def publish(event, **payload):
    message = {"event": event, **payload}
    for listener in list(_listeners):
        try:
            listener(message)
        except Exception:  # noqa: BLE001 - isolate listener failures
            log.exception("Lifecycle listener failed for %s", event)
