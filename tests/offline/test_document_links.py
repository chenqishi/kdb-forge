"""Check local inline Markdown links in the current maintenance documents."""
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[2]
INLINE_LINK = re.compile(
    r'\[[^\]\n]*\]\(\s*(?:<(?P<angle>[^>\n]+)>|(?P<bare>[^\s)]+))'
    r'(?:\s+"[^"]*")?\s*\)'
)


def test_current_document_relative_links_exist():
    documents = [ROOT / name for name in ('README.md', 'AGENTS.md', 'CLAUDE.md', 'MEMORY.md')]
    documents.extend(sorted((ROOT / 'docs').rglob('*.md')))
    errors = []
    checked = 0
    for document in documents:
        fence = None
        with document.open(encoding='utf-8') as stream:
            for lineno, line in enumerate(stream, 1):
                stripped = line.lstrip()
                marker = re.match(r'(`{3,}|~{3,})', stripped)
                if marker:
                    if fence is None:
                        fence = marker.group()
                    elif stripped.startswith(fence):
                        fence = None
                    continue
                if fence:
                    continue
                for match in INLINE_LINK.finditer(line):
                    target = match.group('angle') or match.group('bare')
                    url = urlsplit(target)
                    if url.scheme or url.netloc or not url.path:
                        continue
                    checked += 1
                    resolved = (document.parent / unquote(url.path)).resolve()
                    if not resolved.is_relative_to(ROOT) or not resolved.exists():
                        errors.append(f'{document.relative_to(ROOT)}:{lineno}: {target}')
    assert checked > 0, 'No local Markdown links were checked'
    assert not errors, 'Missing or non-portable document targets:\n' + '\n'.join(errors)
