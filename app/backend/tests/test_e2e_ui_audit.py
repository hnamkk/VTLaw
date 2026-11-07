import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.e2e_ui_audit import (  # noqa: E402
    detect_network_issues,
    detect_overlay_issues,
    detect_text_issues,
)


def test_detect_text_issues_flags_forbidden_and_mojibake():
    issues = detect_text_issues("Trang báo lỗi Internal Server Error và chuỗi Ã¡ lạ.")
    assert "text_forbidden:Internal Server Error" in issues
    assert "text_mojibake:Ã¡" in issues


def test_detect_text_issues_accepts_clean_vietnamese_text():
    assert detect_text_issues("Kho văn bản đang công bố bình thường.") == []


def test_detect_overlay_issues_flags_next_artifacts():
    issues = detect_overlay_issues(
        {
            "has_next_badge": True,
            "has_next_portal": False,
            "visible_issue_badges": ["2 Issues"],
        }
    )
    assert "overlay:next-badge" in issues
    assert "overlay:issue-badge" in issues


def test_detect_network_issues_ignores_success_statuses():
    assert detect_network_issues([{"status": 200, "url": "http://127.0.0.1:8000/api/v1/documents"}]) == []


def test_detect_network_issues_flags_500():
    issues = detect_network_issues([{"status": 500, "url": "http://127.0.0.1:8000/api/v1/admin/legal-kb/documents"}])
    assert issues == ["network:500:http://127.0.0.1:8000/api/v1/admin/legal-kb/documents"]
