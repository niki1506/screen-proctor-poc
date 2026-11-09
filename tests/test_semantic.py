import cv2
import numpy as np
import pytest

from screenproctor.semantic import InterfaceScanner, classify_text


def row(text, y, score=0.95):
    return [[[10, y], [200, y], [200, y + 20], [10, y + 20]], text, score]


def test_brand_and_chat_control_required():
    result = classify_text(
        [row("ChatGPT", 40), row("New chat", 180), row("Message ChatGPT", 700)], 1000
    )
    assert result["match"] == "ChatGPT"
    assert result["identity_basis"] == "header_brand_and_chat_control"
    assert "Message ChatGPT" not in result["matched_cues"]


@pytest.mark.parametrize(
    "rows",
    [
        [row("Email", 40), row("Our article discusses ChatGPT", 400), row("Send", 700)],
        [row("ChatGPT", 400), row("Message", 700), row("Send", 800)],
        [row("ChatGPT", 40), row("A document discussing artificial intelligence", 400)],
        [row("chatgpt.com.evil.example", 40), row("Message", 700), row("Send", 800)],
        [row("notchatgpt.com", 40), row("Message", 700), row("Send", 800)],
        [row("ChatGPT", 40, 0.4), row("Message", 700), row("Send", 800)],
    ],
)
def test_mentions_spoofed_domains_and_low_confidence_are_not_interfaces(rows):
    assert classify_text(rows, 1000)["match"] is None


def test_domain_and_generic_assistant():
    result = classify_text(
        [row("https://claude.ai/chat", 40), row("Message", 700)], 1000
    )
    assert result["match"] == "Claude"
    assert (
        classify_text([row("AI ASSISTANT", 40), row("Type your question", 700)], 1000)[
            "match"
        ]
        == "unidentified_ai_assistant"
    )


def test_unreadable_text_is_not_clean():
    result = classify_text([row("DELL", 700), row("x", 40)], 1000)
    assert not result["readable"] and result["match"] is None


def test_real_local_ocr_recognizes_readable_interface():
    image = np.full((720, 1280, 3), 240, np.uint8)
    for text, y in [
        ("ChatGPT", 70),
        ("New chat", 180),
        ("How can I help you?", 350),
        ("Message ChatGPT", 600),
        ("Send", 670),
    ]:
        cv2.putText(
            image, text, (50, y), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (10, 10, 10), 2
        )
    result = InterfaceScanner().scan(image)
    assert result["match"] == "ChatGPT"
