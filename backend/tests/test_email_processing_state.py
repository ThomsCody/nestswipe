from app.services.email_processing_state import (
    get_polling_state,
    track_email_processing,
)


def test_overlapping_parsers_remain_active_until_both_finish():
    with track_email_processing(123, remaining_emails=3):
        started_at = get_polling_state(123)["started_at"]
        with track_email_processing(123):
            assert get_polling_state(123) == {
                "is_polling": True,
                "started_at": started_at,
                "remaining_emails": 4,
            }
        assert get_polling_state(123)["remaining_emails"] == 3
    assert get_polling_state(123) == {
        "is_polling": False,
        "started_at": None,
        "remaining_emails": 0,
    }


async def test_poll_status_is_scoped_to_authenticated_household(
    client, auth_headers, test_user
):
    with track_email_processing(test_user.household_id + 1):
        response = await client.get(
            "/api/v1/listings/poll-status", headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json() == {
            "is_polling": False,
            "started_at": None,
            "remaining_emails": 0,
        }
        with track_email_processing(test_user.household_id, remaining_emails=5):
            response = await client.get(
                "/api/v1/listings/poll-status", headers=auth_headers
            )
            assert response.json()["is_polling"]
            assert response.json()["remaining_emails"] == 5
            assert response.json()["started_at"] is not None


async def test_poll_status_requires_authentication(client):
    response = await client.get("/api/v1/listings/poll-status")
    assert response.status_code == 403
