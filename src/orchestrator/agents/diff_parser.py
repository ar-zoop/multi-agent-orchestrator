import re
from dataclasses import dataclass, field

HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
DIFF_HEADER = re.compile(r"^diff --git a/(.+?) b/(.+)$")
BINARY_MARKER = "Binary files "


@dataclass
class DiffLine:
    kind: str
    new_lineno: int | None
    old_lineno: int | None
    text: str


@dataclass
class FileDiff:
    path: str
    lines: list[DiffLine] = field(default_factory=list)
    is_new: bool = False
    is_deleted: bool = False
    is_binary: bool = False

    @property
    def added_lines(self) -> list[DiffLine]:
        return [line for line in self.lines if line.kind == "added"]

    @property
    def removed_lines(self) -> list[DiffLine]:
        return [line for line in self.lines if line.kind == "removed"]


def _new_path(header_path: str, fallback: str) -> str:
    path = header_path.strip()
    if path.startswith("b/"):
        path = path[2:]
    if path == "/dev/null":
        return fallback
    return path


def parse_diff(diff_text: str) -> list[FileDiff]:
    files: list[FileDiff] = []
    current: FileDiff | None = None
    new_lineno = 0
    old_lineno = 0

    for raw in (diff_text or "").splitlines():
        header = DIFF_HEADER.match(raw)
        if header:
            current = FileDiff(path=header.group(2))
            files.append(current)
            continue

        if current is None:
            if raw.startswith("--- ") or raw.startswith("+++ "):
                current = FileDiff(path="unknown")
                files.append(current)
            else:
                continue

        if raw.startswith(BINARY_MARKER):
            current.is_binary = True
            continue
        if raw.startswith("new file mode"):
            current.is_new = True
            continue
        if raw.startswith("deleted file mode"):
            current.is_deleted = True
            continue
        if raw.startswith("--- "):
            if raw[4:].strip() == "/dev/null":
                current.is_new = True
            continue
        if raw.startswith("+++ "):
            current.path = _new_path(raw[4:], current.path)
            if raw[4:].strip() == "/dev/null":
                current.is_deleted = True
            continue

        hunk = HUNK_HEADER.match(raw)
        if hunk:
            old_lineno = int(hunk.group(1))
            new_lineno = int(hunk.group(3))
            continue

        if raw.startswith("+"):
            current.lines.append(DiffLine("added", new_lineno, None, raw[1:]))
            new_lineno += 1
        elif raw.startswith("-"):
            current.lines.append(DiffLine("removed", None, old_lineno, raw[1:]))
            old_lineno += 1
        elif raw.startswith(" ") or raw == "":
            current.lines.append(DiffLine("context", new_lineno, old_lineno, raw[1:]))
            new_lineno += 1
            old_lineno += 1

    return [f for f in files if f.lines or f.is_binary]


def annotate_diff(diff_text: str) -> str:
    blocks = []
    for file_diff in parse_diff(diff_text):
        header = f"FILE: {file_diff.path}"
        if file_diff.is_new:
            header += " (new file)"
        if file_diff.is_deleted:
            header += " (deleted)"
        if file_diff.is_binary:
            blocks.append(f"{header}\n(binary file, not reviewable)")
            continue

        rendered = []
        for line in file_diff.lines:
            marker = {"added": "+", "removed": "-", "context": " "}[line.kind]
            lineno = "    " if line.new_lineno is None else f"{line.new_lineno:>4}"
            rendered.append(f"{lineno} {marker} {line.text}")
        blocks.append(header + "\n" + "\n".join(rendered))

    return "\n\n".join(blocks)


def changed_files(diff_text: str) -> list[str]:
    return [f.path for f in parse_diff(diff_text)]
