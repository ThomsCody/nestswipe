from html.parser import HTMLParser
from unittest.mock import Mock

import pytest

from app.services import email


class ParsedEmail(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.text = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))

    def handle_data(self, data):
        self.text.append(data)


@pytest.fixture
def sendgrid(monkeypatch):
    monkeypatch.setattr(email.settings, "sendgrid_api_key", "test-key")
    monkeypatch.setattr(email.settings, "sendgrid_from_email", "sender@example.test")
    monkeypatch.setattr(
        email.settings, "frontend_url", "https://nestswipe.example.test"
    )
    client = Mock()
    monkeypatch.setattr(email, "SendGridAPIClient", Mock(return_value=client))
    return client


async def send_notification(kind, text):
    kwargs = dict(
        to_email="recipient@example.test",
        to_name=text,
        listing_title=text,
        favorite_id=42,
    )
    if kind == "mention":
        await email.send_mention_email(**kwargs, commenter_name=text, comment_body=text)
    else:
        await email.send_assignment_email(**kwargs, assigner_name=text)


@pytest.mark.parametrize("kind", ["mention", "assignment"])
@pytest.mark.parametrize(
    "text",
    [
        '</blockquote><a href="https://attacker.example">Sign in</a>'
        '<img src="https://attacker.example/pixel" onerror="alert(1)">',
        'Élodie & Thomas — l\'appartement "coup de cœur" <3 &lt;b&gt;',
    ],
)
async def test_notification_renders_untrusted_values_as_text(sendgrid, kind, text):
    await send_notification(kind, text)

    sendgrid.send.assert_called_once()
    message = sendgrid.send.call_args.args[0].get()
    parsed = ParsedEmail(message["content"][0]["value"])
    expected_tags = ["p", "p", "strong", "strong"]
    if kind == "mention":
        expected_tags.append("blockquote")
    expected_tags.extend(["p", "a"])
    assert [tag for tag, _ in parsed.elements] == expected_tags
    assert "".join(parsed.text).count(text) == (4 if kind == "mention" else 3)
    assert [(tag, attrs) for tag, attrs in parsed.elements if tag == "a"] == [
        ("a", {"href": "https://nestswipe.example.test/favorites/42"})
    ]
    # Subjects are plain text, so HTML escaping must not change their contents.
    assert message["subject"].count(text) == 2


@pytest.mark.parametrize("kind", ["mention", "assignment"])
async def test_notification_quotes_link_attribute(sendgrid, monkeypatch, kind):
    frontend_url = 'https://nestswipe.example.test/" onmouseover="alert(1)&x=1'
    monkeypatch.setattr(email.settings, "frontend_url", frontend_url)

    await send_notification(kind, "Alice")

    message = sendgrid.send.call_args.args[0].get()
    parsed = ParsedEmail(message["content"][0]["value"])
    assert [(tag, attrs) for tag, attrs in parsed.elements if tag == "a"] == [
        ("a", {"href": f"{frontend_url}/favorites/42"})
    ]


@pytest.mark.parametrize("kind", ["mention", "assignment"])
async def test_notification_skips_send_without_configuration(
    sendgrid, monkeypatch, kind
):
    monkeypatch.setattr(email.settings, "sendgrid_api_key", "")

    await send_notification(kind, "Alice")

    sendgrid.send.assert_not_called()
