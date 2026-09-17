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
