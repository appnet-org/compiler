def strip(s: str) -> str:
    s = s.strip()
    if s.startswith("'") and s.endswith("'"):
        s = s[1:-1]
    elif s.startswith("\"") and s.endswith("\""):
        s = s[1:-1]
    return s