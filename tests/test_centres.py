"""Centre and test catalogue tests."""


def test_create_and_list_centre_with_tests(client, auth_headers):
    test_id = client.post(
        "/tests", json={"name": "Lipid", "description": None}, headers=auth_headers
    ).json()["id"]
    centre_id = client.post(
        "/centres", json={"name": "Centre A", "location": "City"}, headers=auth_headers
    ).json()["id"]

    resp = client.post(
        f"/centres/{centre_id}/tests",
        json={"test_id": test_id, "price": "700.00"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["test"]["name"] == "Lipid"

    detail = client.get(f"/centres/{centre_id}").json()
    assert len(detail["centre_tests"]) == 1


def test_create_centre_requires_auth(client):
    assert client.post("/centres", json={"name": "X", "location": "Y"}).status_code == 401


def test_duplicate_test_offering_conflict(client, auth_headers):
    test_id = client.post(
        "/tests", json={"name": "TSH"}, headers=auth_headers
    ).json()["id"]
    centre_id = client.post(
        "/centres", json={"name": "C", "location": "L"}, headers=auth_headers
    ).json()["id"]
    body = {"test_id": test_id, "price": "800.00"}
    assert client.post(
        f"/centres/{centre_id}/tests", json=body, headers=auth_headers
    ).status_code == 201
    assert client.post(
        f"/centres/{centre_id}/tests", json=body, headers=auth_headers
    ).status_code == 409


def test_negative_price_rejected(client, auth_headers):
    test_id = client.post("/tests", json={"name": "VitD"}, headers=auth_headers).json()["id"]
    centre_id = client.post(
        "/centres", json={"name": "C", "location": "L"}, headers=auth_headers
    ).json()["id"]
    resp = client.post(
        f"/centres/{centre_id}/tests",
        json={"test_id": test_id, "price": "-1.00"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_get_missing_centre_404(client):
    assert client.get("/centres/does-not-exist").status_code == 404


def test_list_pagination_shape(client, auth_headers):
    resp = client.get("/centres?limit=5&offset=0")
    body = resp.json()
    assert set(body.keys()) == {"total", "limit", "offset", "items"}
    assert body["limit"] == 5
