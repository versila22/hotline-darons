import pytest
from fastapi.testclient import TestClient
from bot.twilio_webhook import app

client = TestClient(app)

def test_webhook_receives_message():
    response = client.post(
        "/whatsapp",
        data={
            "From": "whatsapp:+1234567890",
            "Body": "Hello from tests",
            "NumMedia": "0"
        }
    )
    assert response.status_code == 200
    assert "application/xml" in response.headers["content-type"]
    assert b"Message" in response.content

def test_webhook_pii_check():
    response = client.post(
        "/whatsapp",
        data={
            "From": "whatsapp:+1234567890",
            "Body": "My password is password 1234",
            "NumMedia": "0"
        }
    )
    assert response.status_code == 200
    assert b"informations sensibles" in response.content
