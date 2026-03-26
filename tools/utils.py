import re

def get_slug(name: str) -> str:
    """Standardized slug for company names to avoid duplication."""
    if not name:
        return ""
    # Remove special characters, lowercase, replace spaces with underscores
    s = name.lower().strip()
    s = s.replace(' ', '_').replace('/', '_').replace('-', '_')
    s = re.sub(r'[^a-z0-9_]', '', s)
    return s
