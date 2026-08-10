"""Self-healing sync: a wiped upstream gets everything back.

The cloud half is /api/sync/inventory (what do you hold?); the sim-PC half is
sync.mark_missing_unsynced (re-queue whatever the cloud lost)."""

import sync
from models import Lap
from tests.conftest import lap_payload
from tests.test_sync import sync_payload


def test_inventory_lists_laps_per_event(client, auth):
    client.post("/api/sync/laps",
                json=sync_payload([lap_payload(client_id="inv1"),
                                   lap_payload(client_id="inv2")]),
                headers=auth)
    inv = client.post("/api/sync/inventory", json={"events": ["expo-2026"]},
                      headers=auth).get_json()
    assert sorted(inv["client_ids"]) == ["inv1", "inv2"]
    # An event this instance doesn't know yet → empty, not an error.
    inv = client.post("/api/sync/inventory", json={"events": ["volgend-jaar"]},
                      headers=auth).get_json()
    assert inv["client_ids"] == []


def test_inventory_requires_token(client):
    assert client.post("/api/sync/inventory", json={}).status_code == 401


def test_mark_missing_unsynced_requeues_lost_laps(client, auth, event, app):
    for i in range(3):
        client.post("/api/laps", json=lap_payload(client_id=f"heal{i}"),
                    headers=auth)
    with app.app_context():
        Lap.query.update({Lap.synced: True})  # as if all were delivered
        from models import db
        db.session.commit()

        # The cloud was wiped: it reports holding nothing.
        assert sync.mark_missing_unsynced(set()) == 3
        assert Lap.query.filter_by(synced=False).count() == 3

        # After re-delivery, a complete upstream relapses nothing.
        Lap.query.update({Lap.synced: True})
        db.session.commit()
        assert sync.mark_missing_unsynced({"heal0", "heal1", "heal2"}) == 0


def test_partial_loss_only_requeues_the_gap(client, auth, event, app):
    for i in range(3):
        client.post("/api/laps", json=lap_payload(client_id=f"gap{i}"),
                    headers=auth)
    with app.app_context():
        from models import db
        Lap.query.update({Lap.synced: True})
        db.session.commit()
        assert sync.mark_missing_unsynced({"gap0", "gap2"}) == 1
        relapsed = Lap.query.filter_by(synced=False).all()
        assert [l.client_id for l in relapsed] == ["gap1"]
