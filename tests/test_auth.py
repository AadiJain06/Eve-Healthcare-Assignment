"""Authentication tests."""


def test_signup_and_login(client):
    resp = client.post(
        "/auth/signup",
        json={"email": "bob@example.com", "full_name": "Bob", "password": "password12"},
    )
    assert resp.status_code == 201
    assert resp.json()["email"] == "bob@example.com"
    assert "hashed_password" not in resp.json()

    resp = client.post(
        "/auth/login", data={"username": "bob@example.com", "password": "password12"}
    )
    assert resp.status_code == 200
    assert resp.json()["token_type"] == "bearer"


def test_signup_duplicate_email(client):
    payload = {"email": "dup@example.com", "full_name": "Dup", "password": "password12"}
    assert client.post("/auth/signup", json=payload).status_code == 201
    assert client.post("/auth/signup", json=payload).status_code == 409


def test_signup_short_password_rejected(client):
    resp = client.post(
        "/auth/signup",
        json={"email": "x@example.com", "full_name": "X", "password": "short"},
    )
    assert resp.status_code == 422


def test_login_wrong_password(client):
    client.post(
        "/auth/signup",
        json={"email": "c@example.com", "full_name": "C", "password": "password12"},
    )
    resp = client.post(
        "/auth/login", data={"username": "c@example.com", "password": "wrongpass1"}
    )
    assert resp.status_code == 401


def test_me_requires_auth(client):
    assert client.get("/auth/me").status_code == 401
