import json
from src.handlers import github_client
from unittest.mock import Mock

def test_get_pr_changed_files_pagination(monkeypatch):
    monkeypatch.setattr(github_client, "_get_token", lambda: "dummy-token")
    
    # Mock requests.get to return 2 pages
    def mock_get(url, *args, **kwargs):
        mock_resp = Mock()
        if "page=2" not in url:
            # Page 1
            mock_resp.json.return_value = [{"filename": "src/main.py"}, {"filename": "src/auth/login.py"}]
            mock_resp.headers = {"Link": '<https://api.github.com/repos/org/repo/pulls/1/files?page=2>; rel="next"'}
            mock_resp.raise_for_status = Mock()
        else:
            # Page 2
            mock_resp.json.return_value = [{"filename": "README.md"}]
            mock_resp.headers = {}
            mock_resp.raise_for_status = Mock()
        return mock_resp

    monkeypatch.setattr(github_client.requests, "get", mock_get)

    files = github_client.get_pr_changed_files("org/repo", 1)
    assert files == ["src/main.py", "src/auth/login.py", "README.md"]

def test_get_pr_changed_files_rename(monkeypatch):
    monkeypatch.setattr(github_client, "_get_token", lambda: "dummy-token")
    
    # Mock requests.get to return a renamed file
    def mock_get(url, *args, **kwargs):
        mock_resp = Mock()
        mock_resp.json.return_value = [{"filename": "src/utils/login.py", "previous_filename": "src/auth/login.py", "status": "renamed"}]
        mock_resp.headers = {}
        mock_resp.raise_for_status = Mock()
        return mock_resp

    monkeypatch.setattr(github_client.requests, "get", mock_get)

    files = github_client.get_pr_changed_files("org/repo", 1)
    
    # The fix ensures both the new path and the old path are evaluated!
    assert "src/utils/login.py" in files
    assert "src/auth/login.py" in files
    assert len(files) == 2

def test_get_pr_approvers_stale_and_dismissed(monkeypatch):
    monkeypatch.setattr(github_client, "_get_token", lambda: "dummy-token")
    
    def mock_get(url, *args, **kwargs):
        mock_resp = Mock()
        # Alice approves, but then requests changes
        # Bob approves, but it is dismissed
        # Charlie approves, and then comments
        # Dave requests changes, then approves
        mock_resp.json.return_value = [
            {"user": {"login": "alice"}, "state": "APPROVED"},
            {"user": {"login": "bob"}, "state": "APPROVED"},
            {"user": {"login": "bob"}, "state": "DISMISSED"},
            {"user": {"login": "charlie"}, "state": "APPROVED"},
            {"user": {"login": "charlie"}, "state": "COMMENTED"},
            {"user": {"login": "alice"}, "state": "CHANGES_REQUESTED"},
            {"user": {"login": "dave"}, "state": "CHANGES_REQUESTED"},
            {"user": {"login": "dave"}, "state": "APPROVED"},
        ]
        mock_resp.headers = {}
        mock_resp.raise_for_status = Mock()
        return mock_resp

    monkeypatch.setattr(github_client.requests, "get", mock_get)

    approvers = github_client.get_pr_approvers("org/repo", 1)
    
    assert "charlie" in approvers
    assert "dave" in approvers
    assert "alice" not in approvers
    assert "bob" not in approvers
    assert len(approvers) == 2
