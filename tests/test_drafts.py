"""Tests for lpad.drafts."""

import time

from lpad.drafts import (
    create_draft,
    get_draft,
    list_drafts,
    prune_drafts,
    remove_draft,
    update_draft,
)


class TestCreateAndGet:
    def test_create_and_get(self):
        draft = create_draft("curl", "Fix TLS", "Description here")
        assert draft.id  # Non-empty ID
        assert len(draft.id) == 4  # Short hash
        assert draft.package == "curl"
        assert draft.title == "Fix TLS"
        assert draft.description == "Description here"
        assert draft.path.exists()

        loaded = get_draft(draft.id, package="curl")
        assert loaded is not None
        assert loaded.title == "Fix TLS"
        assert loaded.description == "Description here"

    def test_get_nonexistent(self):
        assert get_draft("aaaa", package="curl") is None

    def test_get_without_package_scans_all(self):
        draft = create_draft("curl", "Fix TLS", "Description")
        loaded = get_draft(draft.id)
        assert loaded is not None
        assert loaded.package == "curl"


class TestListDrafts:
    def test_empty(self):
        assert list_drafts() == []

    def test_lists_by_package(self):
        create_draft("curl", "Bug 1", "Desc 1")
        create_draft("curl", "Bug 2", "Desc 2")
        create_draft("vim", "Bug 3", "Desc 3")

        curl_drafts = list_drafts(package="curl")
        assert len(curl_drafts) == 2

        all_drafts = list_drafts()
        assert len(all_drafts) == 3

    def test_titles_parsed(self):
        create_draft("curl", "Fix TLS", "Description")
        drafts = list_drafts(package="curl")
        assert drafts[0].title == "Fix TLS"


class TestUpdateDraft:
    def test_update(self):
        draft = create_draft("curl", "Old title", "Old desc")
        draft.title = "New title"
        draft.description = "New desc"
        update_draft(draft)

        loaded = get_draft(draft.id, package="curl")
        assert loaded is not None
        assert loaded.title == "New title"
        assert loaded.description == "New desc"


class TestRemoveDraft:
    def test_remove(self):
        draft = create_draft("curl", "Title", "Desc")
        assert remove_draft(draft.id, package="curl") is True
        assert get_draft(draft.id, package="curl") is None

    def test_remove_nonexistent(self):
        assert remove_draft("aaaa", package="curl") is False


class TestPruneDrafts:
    def test_dry_run(self):
        draft = create_draft("curl", "Old", "Desc")
        # Backdate the draft file's mtime
        import os

        old_time = time.time() - 60 * 60 * 24 * 31  # 31 days ago
        os.utime(draft.path, (old_time, old_time))

        removed = prune_drafts(older_than_days=30, dry_run=True)
        assert len(removed) == 1
        assert draft.path.exists()  # Not actually removed

    def test_actual_prune(self):
        draft = create_draft("curl", "Old", "Desc")
        import os

        old_time = time.time() - 60 * 60 * 24 * 31
        os.utime(draft.path, (old_time, old_time))

        removed = prune_drafts(older_than_days=30, dry_run=False)
        assert len(removed) == 1
        assert not draft.path.exists()

    def test_recent_not_pruned(self):
        create_draft("curl", "Recent", "Desc")
        removed = prune_drafts(older_than_days=30, dry_run=True)
        assert len(removed) == 0


class TestDraftIdUniqueness:
    def test_different_titles_different_ids(self):
        d1 = create_draft("curl", "Title A", "Desc")
        d2 = create_draft("curl", "Title B", "Desc")
        assert d1.id != d2.id
