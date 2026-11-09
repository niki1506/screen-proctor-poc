"""Local OCR recognition of visible AI interfaces, independent of screen changes."""

import re

import cv2
import numpy as np

SERVICES = {
    "ChatGPT": ("chatgpt", ("chatgpt.com", "chat.openai.com")),
    "Claude": ("claude", ("claude.ai",)),
    "Gemini": ("gemini", ("gemini.google.com",)),
    "Copilot": ("copilot", ("copilot.microsoft.com",)),
    "Perplexity": ("perplexity", ("perplexity.ai",)),
    "DeepSeek": ("deepseek", ("chat.deepseek.com",)),
}
CHAT_CUES = (
    "message",
    "send",
    "ask anything",
    "ask me anything",
    "new chat",
    "type your",
    "prompt",
    "what can i help",
    "how can i help",
)


def classify_text(rows, height):
    """Require header service identity plus a separate chat control.

    Text in an article/email mentioning a brand is insufficient. Returned cues
    are allowlisted labels, never a dump of screen contents or prompts. OCR
    locations and confidence refer to the processed region, not source pixels.
    """
    tokens = []
    for box, text, confidence in rows or []:
        if confidence < 0.65 or not np.isfinite(confidence):
            continue
        normalized = re.sub(r"\s+", " ", text.lower()).strip()
        if len(re.sub("[^a-z]", "", normalized)) < 3:
            continue
        tokens.append(
            (
                normalized,
                float(confidence),
                float(np.mean(np.array(box)[:, 1])) / height,
            )
        )
    readable = len(tokens) >= 3
    controls = [
        (cue, score)
        for text, score, y in tokens
        for cue in CHAT_CUES
        if cue in text and (y > 0.35 or cue == "new chat") and len(text) < 90
    ]
    for service, (brand, domains) in SERVICES.items():
        for text, confidence, y in tokens:
            # Exact brand/header labels prevent a paragraph about AI from qualifying.
            named_header = y < 0.35 and text in (brand, brand + " ai", brand + " plus")
            domain_header = y < 0.22 and any(
                re.search(
                    r"(?<![a-z0-9.-])" + re.escape(domain) + r"(?![a-z0-9.-])", text
                )
                for domain in domains
            )
            if (named_header or domain_header) and controls:
                return {
                    "readable": True,
                    "match": service,
                    "score": min(confidence, max(s for _, s in controls)),
                    "matched_cues": [service, max(controls, key=lambda x: x[1])[0]],
                    "identity_basis": "domain_and_chat_control"
                    if domain_header
                    else "header_brand_and_chat_control",
                }
    # Explicit generic assistant label can only establish a candidate interface.
    generic = [
        (score, y)
        for text, score, y in tokens
        if text in ("ai assistant", "ai chat", "ai chatbot") and y < 0.35
    ]
    if generic and controls:
        return {
            "readable": True,
            "match": "unidentified_ai_assistant",
            "score": min(generic[0][0], max(s for _, s in controls)),
            "matched_cues": ["AI assistant header", controls[0][0]],
            "identity_basis": "generic_assistant_header_and_chat_control",
        }
    return {"readable": readable, "match": None}


class InterfaceScanner:
    def __init__(self):
        self.engine = None

    def scan(self, image):
        if self.engine is None:
            from rapidocr_onnxruntime import RapidOCR

            self.engine = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=2)
        h, w = image.shape[:2]
        scale = min(3.0, 2560 / max(w, h))
        view = cv2.resize(
            image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC
        )
        rows, _ = self.engine(view)
        return classify_text(rows, view.shape[0])
