import os
import shutil

import pytest

from career_ai.config import REPO_ROOT
from career_ai.notion_api import NotionClient
from career_ai.notion_sync import init_database, push

pytestmark = pytest.mark.live
SAMPLE = REPO_ROOT / "examples" / "sample-data" / "applications" / "샘플전자_S001"


def test_push_sample_to_real_notion(tmp_path):
    token = os.environ.get("NOTION_TOKEN")
    parent = os.environ.get("NOTION_TEST_PARENT_PAGE")
    if not token or not parent:
        pytest.skip("NOTION_TOKEN, NOTION_TEST_PARENT_PAGE 필요")
    client = NotionClient(token)
    data_source_id = init_database(client, parent)["data_source_id"]
    app = tmp_path / "샘플전자_S001"
    shutil.copytree(SAMPLE, app)
    first = push(app, client, data_source_id)
    second = push(app, client, data_source_id)
    assert first["created"] is True
    assert second["page_id"] == first["page_id"]
    assert second["removed_blocks"] > 0
