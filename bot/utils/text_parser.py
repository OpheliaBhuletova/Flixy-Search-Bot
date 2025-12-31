import re
from pyrogram.types import InlineKeyboardButton

SMART_OPEN = "“"
SMART_CLOSE = "”"
START_CHAR = ("'", '"', SMART_OPEN)

BTN_URL_REGEX = re.compile(
    r"(\[([^\[]+?)\]\((buttonurl|buttonalert):(?:/{0,2})(.+?)(:same)?\))"
)


def remove_escapes(text: str) -> str:
    result = ""
    escaped = False

    for char in text:
        if escaped:
            result += char
            escaped = False
        elif char == "\\":
            escaped = True
        else:
            result += char

    return result


def split_quotes(text: str):
    if not any(text.startswith(c) for c in START_CHAR):
        return text.split(None, 1)

    idx = 1
    while idx < len(text):
        if text[idx] == "\\":
            idx += 1
        elif text[idx] == text[0] or (
            text[0] == SMART_OPEN and text[idx] == SMART_CLOSE
        ):
            break
        idx += 1

    key = remove_escapes(text[1:idx].strip())
    rest = text[idx + 1:].strip()

    return list(filter(None, [key, rest]))


def parser(text: str, keyword: str):
    buttons = []
    alerts = []
    data = ""
    prev = 0
    idx = 0

    for match in BTN_URL_REGEX.finditer(text):
        data += text[prev:match.start(1)]
        prev = match.end(1)

        if match.group(3) == "buttonalert":
            button = InlineKeyboardButton(
                text=match.group(2),
                callback_data=f"alertmessage:{idx}:{keyword}"
            )
            alerts.append(match.group(4))
            idx += 1
        else:
            button = InlineKeyboardButton(
                text=match.group(2),
                url=match.group(4).replace(" ", "")
            )

        if match.group(5) and buttons:
            buttons[-1].append(button)
        else:
            buttons.append([button])

    data += text[prev:]
    return data, buttons, alerts