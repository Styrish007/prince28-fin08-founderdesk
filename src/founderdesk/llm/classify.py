"""Question router: classifies a question into docs, personal or off_topic.

The router builds messages from a prompt template and the user's question,
parses the model's one-word reply into a label, and defends against injection
by validating the label strictly. It also detects when test questions have
leaked into prompt files.
"""

from __future__ import annotations

from pathlib import Path

from founderdesk.llm.gateway import LLMGateway
from founderdesk.llm.prompts import latest_version

VALID_LABELS = ("docs", "personal", "off_topic")


def build_messages(prompt: str, question: str) -> list[dict[str, str]]:
    """Build the system + user messages for classification.

    The prompt is the system message; the user's text goes inside
    <question> tags so it is treated as data, never as an instruction.
    """
    return [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"<question>\n{question}\n</question>"},
    ]


def parse_label(reply: str) -> str | None:
    """Parse a one-word label from the model's reply.

    Forgiving of trailing punctuation, capitalisation, and hyphens
    ("Docs." → "docs", "off-topic" → "off_topic").
    Returns ``None`` for invalid replies (two labels, no label, or an unknown word).
    This function, not the prompt, is the real defence against injection.
    """
    cleaned = reply.strip().strip(".").strip().lower().replace("-", "_")
    if cleaned in VALID_LABELS:
        return cleaned
    return None


def find_leaks(prompt_dir: Path | str = "prompts") -> list[str]:
    """Find test questions that were pasted into prompt files.

    Reads every ``classify_v*.md`` file in ``prompt_dir`` and looks for
    <question> blocks whose content matches a line in the test set.
    Returns a list of leaked question texts.
    """
    prompt_path = Path(prompt_dir)
    if not prompt_path.is_dir():
        return []

    test_set = _load_test_set()
    if not test_set:
        return []

    leaks: list[str] = []
    for path in sorted(prompt_path.glob("classify_v*.md")):
        text = path.read_text(encoding="utf-8")
        for question in test_set:
            if question in text:
                leaks.append(question)
    return leaks


def _load_test_set() -> list[str]:
    """Load questions from the test set file, if it exists."""
    path = Path("eval/prompt_testset.jsonl")
    if not path.is_file():
        return []
    questions: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        import json

        try:
            obj = json.loads(line)
            if isinstance(obj, dict) and "question" in obj:
                questions.append(obj["question"])
        except json.JSONDecodeError:
            continue
    return questions


async def classify(
    gateway: LLMGateway,
    question: str,
    prompt_version: str | None = None,
) -> tuple[str | None, str]:
    """Classify ``question`` using the given gateway and prompt version.

    Returns ``(label, raw_reply)`` where ``label`` is one of
    ``docs``, ``personal``, ``off_topic`` or ``None`` if invalid.
    """
    prompt_path = latest_version("classify") if prompt_version is None else Path(prompt_version)
    if prompt_path is None:
        return None, ""
    prompt = prompt_path.read_text(encoding="utf-8")
    messages = build_messages(prompt, question)
    reply = await gateway.generate(messages)
    label = parse_label(reply.text)
    return label, reply.text
