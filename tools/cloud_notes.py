"""
The notes of one version as plain text, for OrcaCloud.

OrcaSlicer's Plugins dialog shows the OrcaCloud changelog as plain text in its
Changelog tab (a table cell that keeps line breaks), and so does the plugin's
page on OrcaCloud. The changelogs are Markdown wrapped at 78 columns, which
there reads as "### New", "**bold**" and sentences broken in the middle. This
keeps one line per item, without Markdown, in English and then in Portuguese.

    python tools/cloud_notes.py 3.9.1 > notes.txt
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIMIT = 4000          # bytes OrcaCloud keeps of a changelog


def section(text, version):
    """The lines under "## <version>", up to the next "## "."""
    out, on = [], False
    for line in text.splitlines():
        if line.startswith("## "):
            if on:
                break
            on = line[3:].strip() == version
            continue
        if on:
            out.append(line.rstrip())
    return out


def plain(text):
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text)      # links
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    return text


def render(lines):
    """Headings on their own line, one line per item, nested items indented."""
    out, current = [], None          # current: [prefix, raw text], cleaned once whole

    def flush():
        if current is not None:
            out.append(current[0] + plain(current[1]))

    for line in lines:
        stripped = line.strip()
        bullet = re.match(r"^[-*]\s+(.*)", line)
        numbered = re.match(r"^\s+(\d+)\.\s+(.*)", line)
        if not stripped or stripped.startswith("### ") or bullet or numbered:
            flush()
            current = None
        if not stripped:
            continue
        if stripped.startswith("### "):
            if out:
                out.append("")
            out.append(plain(stripped[4:]))
        elif bullet:
            current = ["• ", bullet.group(1)]
        elif numbered:
            current = ["   " + numbered.group(1) + ". ", numbered.group(2)]
        elif current is not None:
            current[1] += " " + stripped
        else:
            current = ["", stripped]
    flush()
    while out and not out[-1]:
        out.pop()
    return "\n".join(out)


def notes(version, root=ROOT):
    parts = []
    for name, title in (("CHANGELOG.md", None), ("CHANGELOG.pt-BR.md", "Português (Brasil)")):
        path = os.path.join(root, name)
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as f:
            body = render(section(f.read(), version))
        if body:
            parts.append(body if title is None else title + "\n\n" + body)
    text = "\n\n—\n\n".join(parts)
    if len(text.encode("utf-8")) > LIMIT and parts:
        text = parts[0]                     # English alone, rather than Portuguese cut short
    return text.encode("utf-8")[:LIMIT].decode("utf-8", "ignore")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(notes(sys.argv[1]))
