import re


def mask_private_key(key):
    def mask_depending_on_length(part, beginning=True):
        if len(part) < 20:
            return "***"
        else:
            if beginning:
                return f"{part[:4]}{'*' * (len(part) - 4)}"
            else:
                return f"{'*' * (len(part) - 4)}{part[-4:]}"

    KEY_PATTERN = (
        r"-----BEGIN (?P<type>.*?) KEY-----"
        r"\s*(?P<body>[\s\S]*?)\s*-----END (?P=type) KEY-----"
    )
    match = re.search(KEY_PATTERN, key)
    content = match.group("body")
    rows = content.split("\n")
    for idx, row in enumerate(rows):
        if idx == 0:
            rows[idx] = mask_depending_on_length(rows[idx])
        elif row == rows[-1]:
            rows[idx] = mask_depending_on_length(rows[idx], False)
            break
        else:
            rows[idx] = f"{'*' * len(row)}"
    masked = "\n".join(rows)
    return key.replace(content, masked)
