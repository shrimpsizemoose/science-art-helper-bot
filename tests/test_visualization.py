import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.models import Broadcast, Registration, User
from src.r2_upload import is_r2_configured, upload_to_r2
from src.visualization import (
    build_registration_timeline,
    collect_event_data,
    generate_and_upload_visualization,
    generate_visualization_html,
    save_visualization_local,
)


class TestIsR2Configured:
    def test_returns_false_when_no_vars_set(self):
        with patch.dict(os.environ, {}, clear=True):
            assert is_r2_configured() is False

    def test_returns_false_when_partial_vars_set(self):
        with patch.dict(
            os.environ,
            {"R2_ENDPOINT_URL": "http://example.com", "R2_BUCKET_NAME": "bucket"},
            clear=True,
        ):
            assert is_r2_configured() is False

    def test_returns_true_when_all_vars_set(self):
        with patch.dict(
            os.environ,
            {
                "R2_ENDPOINT_URL": "http://example.com",
                "R2_ACCESS_KEY_ID": "key",
                "R2_SECRET_ACCESS_KEY": "secret",
                "R2_BUCKET_NAME": "bucket",
                "R2_PUBLIC_URL": "http://public.com",
            },
            clear=True,
        ):
            assert is_r2_configured() is True


class TestUploadToR2:
    def test_upload_calls_boto3(self):
        with patch.dict(
            os.environ,
            {
                "R2_ENDPOINT_URL": "http://example.com",
                "R2_ACCESS_KEY_ID": "key",
                "R2_SECRET_ACCESS_KEY": "secret",
                "R2_BUCKET_NAME": "bucket",
                "R2_PUBLIC_URL": "http://public.com",
            },
            clear=True,
        ):
            with patch("src.r2_upload.boto3.client") as mock_client:
                mock_s3 = MagicMock()
                mock_client.return_value = mock_s3

                url = upload_to_r2(b"content", "test.html")

                mock_s3.put_object.assert_called_once()
                assert url == "http://public.com/test.html"

    def test_upload_with_prefix(self):
        with patch.dict(
            os.environ,
            {
                "R2_ENDPOINT_URL": "http://example.com",
                "R2_ACCESS_KEY_ID": "key",
                "R2_SECRET_ACCESS_KEY": "secret",
                "R2_BUCKET_NAME": "bucket",
                "R2_PUBLIC_URL": "http://public.com/",
                "R2_UPLOAD_PREFIX": "visualizations/",
            },
            clear=True,
        ):
            with patch("src.r2_upload.boto3.client") as mock_client:
                mock_s3 = MagicMock()
                mock_client.return_value = mock_s3

                url = upload_to_r2(b"content", "test.html")

                call_kwargs = mock_s3.put_object.call_args[1]
                assert call_kwargs["Key"] == "visualizations/test.html"
                assert url == "http://public.com/visualizations/test.html"


class TestBuildRegistrationTimeline:
    def test_empty_registrations(self):
        result = build_registration_timeline([])
        assert result == {"labels": [], "cumulative": []}

    def test_single_registration(self, temp_db, sample_event, sample_user):
        reg = Registration.create(
            user=sample_user,
            event=sample_event,
            registered_at=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
        )
        result = build_registration_timeline([reg])
        assert result["labels"] == ["2025-01-15"]
        assert result["cumulative"] == [1]

    def test_multiple_registrations_same_day(self, temp_db, sample_event):
        users = [
            User.create(telegram_id=i, username=f"user{i}")
            for i in range(1, 4)
        ]
        base_time = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
        regs = [
            Registration.create(
                user=u,
                event=sample_event,
                registered_at=base_time + timedelta(hours=i),
            )
            for i, u in enumerate(users)
        ]
        result = build_registration_timeline(regs)
        assert result["labels"] == ["2025-01-15"]
        assert result["cumulative"] == [3]

    def test_multiple_registrations_different_days(self, temp_db, sample_event):
        users = [
            User.create(telegram_id=i, username=f"user{i}")
            for i in range(1, 4)
        ]
        regs = [
            Registration.create(
                user=users[0],
                event=sample_event,
                registered_at=datetime(2025, 1, 15, tzinfo=timezone.utc),
            ),
            Registration.create(
                user=users[1],
                event=sample_event,
                registered_at=datetime(2025, 1, 16, tzinfo=timezone.utc),
            ),
            Registration.create(
                user=users[2],
                event=sample_event,
                registered_at=datetime(2025, 1, 17, tzinfo=timezone.utc),
            ),
        ]
        result = build_registration_timeline(regs)
        assert result["labels"] == ["2025-01-15", "2025-01-16", "2025-01-17"]
        assert result["cumulative"] == [1, 2, 3]


class TestCollectEventData:
    def test_collects_basic_data(self, temp_db, sample_event):
        data = collect_event_data(sample_event)

        assert data["event"] == sample_event
        assert data["stats"]["total_registrations"] == 0
        assert data["stats"]["confirmed_count"] == 0
        assert data["stats"]["cancelled_count"] == 0
        assert data["stats"]["pending_count"] == 0
        assert data["stats"]["total_broadcasts"] == 0
        assert data["broadcasts"] == []
        assert "generated_at" in data

    def test_counts_registrations_correctly(self, temp_db, sample_event):
        users = [
            User.create(telegram_id=i, username=f"user{i}")
            for i in range(1, 5)
        ]

        Registration.create(user=users[0], event=sample_event, confirmed=True)
        Registration.create(user=users[1], event=sample_event, confirmed=False)
        Registration.create(user=users[2], event=sample_event, cancelled=True)
        Registration.create(user=users[3], event=sample_event, confirmed=True)

        data = collect_event_data(sample_event)

        assert data["stats"]["total_registrations"] == 4
        assert data["stats"]["confirmed_count"] == 2
        assert data["stats"]["cancelled_count"] == 1
        assert data["stats"]["pending_count"] == 1

    def test_includes_broadcasts(self, temp_db, sample_event, sample_broadcast):
        data = collect_event_data(sample_event)

        assert data["stats"]["total_broadcasts"] == 1
        assert len(data["broadcasts"]) == 1
        assert data["stats"]["total_messages_sent"] == 10
        assert data["stats"]["total_messages_failed"] == 2

    def test_calculates_delivery_rate(self, temp_db, sample_event):
        Broadcast.create(
            event=sample_event,
            message_text="Test",
            target_audience="all",
            sent_count=80,
            failed_count=20,
        )

        data = collect_event_data(sample_event)

        assert data["stats"]["delivery_rate"] == 80.0


class TestGenerateVisualizationHtml:
    def test_generates_html(self, temp_db, sample_event):
        html = generate_visualization_html(sample_event)

        assert "<!DOCTYPE html>" in html
        assert sample_event.title in html
        assert sample_event.code in html

    def test_html_contains_chart_js(self, temp_db, sample_event):
        html = generate_visualization_html(sample_event)

        assert "chart.js" in html.lower() or "Chart" in html


class TestSaveVisualizationLocal:
    def test_saves_file_to_tmp(self, temp_db, sample_event):
        html = "<html><body>Test</body></html>"
        path = save_visualization_local(html, sample_event)

        assert path.exists()
        assert path.suffix == ".html"
        assert sample_event.code in path.name
        assert path.read_text() == html

        path.unlink()


class TestGenerateAndUploadVisualization:
    def test_raises_error_when_r2_not_configured(self, temp_db, sample_event):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(RuntimeError, match="R2 not configured"):
                generate_and_upload_visualization(sample_event)

    def test_saves_locally_when_local_mode(self, temp_db, sample_event):
        with patch.dict(os.environ, {}, clear=True):
            result, is_remote = generate_and_upload_visualization(sample_event, local=True)

            assert is_remote is False
            assert Path(result).exists()
            Path(result).unlink()

    def test_uploads_to_r2_when_configured(self, temp_db, sample_event):
        with patch.dict(
            os.environ,
            {
                "R2_ENDPOINT_URL": "http://example.com",
                "R2_ACCESS_KEY_ID": "key",
                "R2_SECRET_ACCESS_KEY": "secret",
                "R2_BUCKET_NAME": "bucket",
                "R2_PUBLIC_URL": "http://public.com",
            },
            clear=True,
        ):
            with patch("src.visualization.upload_to_r2") as mock_upload:
                mock_upload.return_value = "http://public.com/test.html"

                result, is_remote = generate_and_upload_visualization(sample_event)

                assert is_remote is True
                assert result == "http://public.com/test.html"
                mock_upload.assert_called_once()
