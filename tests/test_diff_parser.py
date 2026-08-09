from orchestrator.agents.diff_parser import annotate_diff, changed_files, parse_diff

SINGLE_FILE_DIFF = """diff --git a/app.py b/app.py
index 111..222 100644
--- a/app.py
+++ b/app.py
@@ -3,5 +3,6 @@ import os
 def load():
-    return None
+    value = os.environ["KEY"]
+    return value
 
 def other():
"""


def test_it_finds_every_changed_file(sample_diff):
    assert changed_files(sample_diff) == ["src/billing/invoice.py", "src/billing/retry.py"]


def test_added_lines_are_numbered_against_the_new_file(sample_diff):
    files = {f.path: f for f in parse_diff(sample_diff)}
    added = files["src/billing/retry.py"].added_lines

    assert [line.new_lineno for line in added] == [1, 2, 3, 4, 5, 6, 7, 8, 9]
    assert added[0].text == "import time"


def test_a_new_file_is_flagged_as_new(sample_diff):
    files = {f.path: f for f in parse_diff(sample_diff)}

    assert files["src/billing/retry.py"].is_new is True
    assert files["src/billing/invoice.py"].is_new is False


def test_context_and_removed_lines_are_classified_separately():
    files = parse_diff(SINGLE_FILE_DIFF)
    kinds = [line.kind for line in files[0].lines]

    assert kinds.count("added") == 2
    assert kinds.count("removed") == 1
    assert kinds.count("context") == 3


def test_removed_lines_carry_old_line_numbers_not_new_ones():
    removed = parse_diff(SINGLE_FILE_DIFF)[0].removed_lines

    assert len(removed) == 1
    assert removed[0].new_lineno is None
    assert removed[0].old_lineno == 4


def test_added_line_numbers_follow_the_hunk_header():
    added = parse_diff(SINGLE_FILE_DIFF)[0].added_lines

    assert [line.new_lineno for line in added] == [4, 5]


def test_an_empty_diff_produces_nothing():
    assert parse_diff("") == []
    assert parse_diff(None) == []
    assert annotate_diff("") == ""


def test_binary_files_are_marked_and_not_line_numbered():
    diff = (
        "diff --git a/logo.png b/logo.png\n"
        "index 111..222 100644\n"
        "Binary files a/logo.png and b/logo.png differ\n"
    )
    files = parse_diff(diff)

    assert files[0].is_binary is True
    assert files[0].lines == []
    assert "not reviewable" in annotate_diff(diff)


def test_the_annotated_diff_shows_the_path_and_gutter_line_numbers(sample_diff):
    annotated = annotate_diff(sample_diff)

    assert "FILE: src/billing/invoice.py" in annotated
    assert "FILE: src/billing/retry.py (new file)" in annotated
    assert "   1 + import time" in annotated
    assert "+ line" not in annotated


def test_the_annotated_diff_keeps_removed_lines_without_a_number():
    annotated = annotate_diff(SINGLE_FILE_DIFF)

    assert "     - " in annotated
