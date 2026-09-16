from datetime import UTC, datetime


def test_link_mutations_require_csrf(client, registered):
    response = client.post(
        "/api/v1/whatsapp/link", json={"phone": "+573001234567"}
    )
    assert response.status_code == 403


def test_link_rejects_non_e164_phone(client, registered, csrf_headers):
    response = client.post(
        "/api/v1/whatsapp/link",
        headers=csrf_headers,
        json={"phone": "300 123 4567"},
    )
    assert response.status_code == 422


def test_create_link_challenge_stores_only_hash(client, registered, csrf_headers):
    response = client.post(
        "/api/v1/whatsapp/link",
        headers=csrf_headers,
        json={"phone": "+573001234567"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert body["masked_phone"] == "+57******4567"
    assert len(body["code"]) == 6
    assert body["expires_at"].endswith(("Z", "+00:00"))

    from app.database import session_scope
    from app.models import WhatsAppLinkChallenge

    with session_scope() as db:
        row = db.query(WhatsAppLinkChallenge).one()
        assert row.phone_e164 == "+573001234567"
        assert row.code_hash != body["code"]
        assert body["code"] not in row.code_hash


def test_status_masks_phone_and_never_returns_code(client, registered, csrf_headers):
    created = client.post(
        "/api/v1/whatsapp/link",
        headers=csrf_headers,
        json={"phone": "+573001234567"},
    ).json()

    response = client.get("/api/v1/whatsapp/status")

    assert response.status_code == 200
    assert response.json() == {
        "status": "pending",
        "masked_phone": "+57******4567",
        "expires_at": created["expires_at"],
        "verified_at": None,
    }
    assert "code" not in response.text


def test_new_challenge_consumes_previous_one(client, registered, csrf_headers):
    first = client.post(
        "/api/v1/whatsapp/link",
        headers=csrf_headers,
        json={"phone": "+573001234567"},
    )
    second = client.post(
        "/api/v1/whatsapp/link",
        headers=csrf_headers,
        json={"phone": "+573009876543"},
    )
    assert first.status_code == second.status_code == 201

    from app.database import session_scope
    from app.models import WhatsAppLinkChallenge

    with session_scope() as db:
        rows = db.query(WhatsAppLinkChallenge).order_by(WhatsAppLinkChallenge.created_at).all()
        assert len(rows) == 2
        assert rows[0].consumed_at is not None
        assert rows[1].consumed_at is None


def test_unlink_revokes_link_and_pending_challenges(client, registered, csrf_headers):
    client.post(
        "/api/v1/whatsapp/link",
        headers=csrf_headers,
        json={"phone": "+573001234567"},
    )
    from app.database import session_scope
    from app.models import WhatsAppLink

    with session_scope() as db:
        db.add(
            WhatsAppLink(
                user_id=registered["user"]["id"],
                phone_e164="+573001234567",
                provider_jid="573001234567@s.whatsapp.net",
                instance_name="pulso",
                verified_at=datetime.now(UTC),
            )
        )

    response = client.delete("/api/v1/whatsapp/link", headers=csrf_headers)

    assert response.status_code == 204
    assert client.get("/api/v1/whatsapp/status").json() == {
        "status": "unlinked",
        "masked_phone": None,
        "expires_at": None,
        "verified_at": None,
    }
