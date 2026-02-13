from my_credentials.utils import mask_private_key


beginning = "QyNTUxOQAAACA90hws0gjiiAQiSIot"
middle = "SIotI75OxBCx298ebMxOPpinPJNsOw"
end = "gUaNmX/fgvtxSJBmOs8bOWjZX8Cy8H"

m_beginning = f"QyNT{26 * '*'}"
m_middle = f"{30 * '*'}"
m_end = f"{26 * '*'}Cy8H"


def compare(content, masked):
    key = (f"-----BEGIN OPENSSH PRIVATE KEY-----"
           f"\n{content}\n-----END OPENSSH PRIVATE KEY-----\n")
    masked_key = key.replace(content, masked)
    assert mask_private_key(key) == masked_key


def test_mask_key_short():
    compare(content="short-key", masked="***")


def test_mask_key_one_lines():
    compare(content=beginning, masked=m_beginning)


def test_mask_key_two_lines():
    compare(content=f"{beginning}\n{end}", masked=f"{m_beginning}\n{m_end}")


def test_mask_key_multi_line():
    compare(
        content=f"{beginning}\n{middle}\n{end}",
        masked=f"{m_beginning}\n{m_middle}\n{m_end}",
    )
