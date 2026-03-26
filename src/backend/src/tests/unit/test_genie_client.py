# Set test environment variables BEFORE any app imports
import os
os.environ['TESTING'] = 'true'
os.environ['SKIP_STARTUP_TASKS'] = 'true'

"""
Tests for the Genie Spaces client.

Covers:
- create_genie_space via data-rooms API
- delete_genie_space
- Dataset collection from product output ports
- Metadata formatting with truncation
"""

import json
import pytest
from unittest.mock import MagicMock, call
from uuid import uuid4

from src.common.genie_client import (
    collect_datasets_from_products,
    format_metadata_for_genie,
    create_genie_space,
    delete_genie_space,
)


# =========================================================================
# create_genie_space (data-rooms API)
# =========================================================================

class TestCreateGenieSpace:
    """Verify the data-rooms API calls are made correctly."""

    def test_calls_data_rooms_api(self):
        """Should POST to /api/2.0/data-rooms/ with correct payload."""
        mock_ws = MagicMock()
        mock_ws.config.host = "https://workspace.databricks.com"
        mock_ws.api_client.do.return_value = {"space_id": "space-abc-123"}

        result = create_genie_space(
            ws_client=mock_ws,
            name="Test Space",
            datasets=["cat.sch.tbl"],
            warehouse_id="wh-123",
            description="A test space",
        )

        assert result["space_id"] == "space-abc-123"
        assert "genie/rooms/space-abc-123" in result["space_url"]
        assert result["status"] == "active"

        # Verify the POST call to data-rooms
        first_call = mock_ws.api_client.do.call_args_list[0]
        assert first_call[0][0] == 'POST'
        assert first_call[0][1] == '/api/2.0/data-rooms/'
        body = first_call[1]['body']
        assert body["display_name"] == "Test Space"
        assert body["warehouse_id"] == "wh-123"
        assert body["table_identifiers"] == ["cat.sch.tbl"]
        assert body["run_as_type"] == "VIEWER"
        assert body["description"] == "A test space"

    def test_adds_instructions_separately(self):
        """Instructions should be posted to /instructions endpoint after space creation."""
        mock_ws = MagicMock()
        mock_ws.config.host = "https://workspace.databricks.com"
        mock_ws.api_client.do.return_value = {"space_id": "space-abc-123"}

        create_genie_space(
            ws_client=mock_ws,
            name="Test Space",
            datasets=["cat.sch.tbl"],
            warehouse_id="wh-123",
            instructions="Use this for testing",
        )

        # Should have at least 2 calls: create space + add instructions
        assert mock_ws.api_client.do.call_count >= 2

        instructions_call = mock_ws.api_client.do.call_args_list[1]
        assert instructions_call[0][0] == 'POST'
        assert '/instructions' in instructions_call[0][1]
        assert instructions_call[1]['body']['instruction_text'] == "Use this for testing"

    def test_adds_sample_questions(self):
        """Sample questions should be posted to /curated-questions endpoint."""
        mock_ws = MagicMock()
        mock_ws.config.host = "https://workspace.databricks.com"
        mock_ws.api_client.do.return_value = {"space_id": "space-abc-123"}

        questions = ["What is total revenue?", "Show top 10 customers"]
        create_genie_space(
            ws_client=mock_ws,
            name="Test Space",
            datasets=["cat.sch.tbl"],
            warehouse_id="wh-123",
            sample_questions=questions,
        )

        # Should have 3 calls: create space + 2 sample questions
        assert mock_ws.api_client.do.call_count == 3

        for i, q in enumerate(questions):
            sq_call = mock_ws.api_client.do.call_args_list[1 + i]
            assert sq_call[0][0] == 'POST'
            assert '/curated-questions' in sq_call[0][1]
            assert sq_call[1]['body']['question_text'] == q
            assert sq_call[1]['body']['question_type'] == "SAMPLE_QUESTION"

    def test_instructions_truncated_to_5000(self):
        """Instructions exceeding 5000 chars should be truncated."""
        mock_ws = MagicMock()
        mock_ws.config.host = "https://workspace.databricks.com"
        mock_ws.api_client.do.return_value = {"space_id": "space-abc-123"}

        long_text = "x" * 10000
        create_genie_space(
            ws_client=mock_ws,
            name="Test",
            datasets=["cat.sch.tbl"],
            warehouse_id="wh-123",
            instructions=long_text,
        )

        instructions_call = mock_ws.api_client.do.call_args_list[1]
        assert len(instructions_call[1]['body']['instruction_text']) == 5000

    def test_uses_id_fallback_for_space_id(self):
        """Should use 'id' field if 'space_id' is not in response."""
        mock_ws = MagicMock()
        mock_ws.config.host = "https://workspace.databricks.com"
        mock_ws.api_client.do.return_value = {"id": "room-xyz-456"}

        result = create_genie_space(
            ws_client=mock_ws,
            name="Test",
            datasets=["cat.sch.tbl"],
            warehouse_id="wh-123",
        )

        assert result["space_id"] == "room-xyz-456"

    def test_raises_on_empty_datasets(self):
        """Should raise ValueError if no datasets provided."""
        mock_ws = MagicMock()

        with pytest.raises(ValueError, match="(?i)at least one dataset"):
            create_genie_space(
                ws_client=mock_ws,
                name="Empty Space",
                datasets=[],
                warehouse_id="wh-123",
            )

    def test_raises_on_missing_warehouse(self):
        """Should raise ValueError if warehouse_id is empty."""
        mock_ws = MagicMock()

        with pytest.raises(ValueError, match="warehouse_id"):
            create_genie_space(
                ws_client=mock_ws,
                name="No Warehouse",
                datasets=["cat.sch.tbl"],
                warehouse_id="",
            )

    def test_raises_on_no_space_id_returned(self):
        """Should raise ValueError if API returns no space_id or id."""
        mock_ws = MagicMock()
        mock_ws.api_client.do.return_value = {}

        with pytest.raises(ValueError, match="No space_id"):
            create_genie_space(
                ws_client=mock_ws,
                name="Test",
                datasets=["cat.sch.tbl"],
                warehouse_id="wh-123",
            )


# =========================================================================
# delete_genie_space
# =========================================================================

class TestDeleteGenieSpace:
    """Verify Genie Space deletion."""

    def test_calls_delete_api(self):
        """Should call DELETE on the data-rooms API."""
        mock_ws = MagicMock()
        mock_ws.api_client.do.return_value = None

        delete_genie_space(mock_ws, "space-to-delete")

        mock_ws.api_client.do.assert_called_once_with(
            'DELETE', '/api/2.0/data-rooms/space-to-delete'
        )


# =========================================================================
# collect_datasets_from_products
# =========================================================================

class TestCollectDatasetsFromProducts:
    """Verify dataset extraction from product output ports."""

    def test_collects_table_identifiers(self, db_session):
        """Should extract asset_identifier from table/view output ports."""
        from src.db_models.data_products import DataProductDb, OutputPortDb

        product = DataProductDb(
            id=str(uuid4()), name="Test Product", version="1.0", status="active"
        )
        db_session.add(product)
        db_session.flush()

        port = OutputPortDb(
            id=str(uuid4()),
            product_id=product.id,
            name="Main Table",
            asset_type="table",
            asset_identifier="catalog.schema.orders",
            version="1.0",
        )
        db_session.add(port)
        db_session.flush()

        datasets = collect_datasets_from_products([product.id], db_session)

        assert datasets == ["catalog.schema.orders"]

    def test_skips_non_table_ports(self, db_session):
        """Should skip ports that aren't tables or views."""
        from src.db_models.data_products import DataProductDb, OutputPortDb

        product = DataProductDb(
            id=str(uuid4()), name="Test Product", version="1.0", status="active"
        )
        db_session.add(product)
        db_session.flush()

        port = OutputPortDb(
            id=str(uuid4()),
            product_id=product.id,
            name="API Port",
            asset_type="api",
            asset_identifier="https://api.example.com",
            version="1.0",
        )
        db_session.add(port)
        db_session.flush()

        datasets = collect_datasets_from_products([product.id], db_session)

        assert datasets == []

    def test_deduplicates_datasets(self, db_session):
        """Same table referenced by two products should appear once."""
        from src.db_models.data_products import DataProductDb, OutputPortDb

        products = []
        for i in range(2):
            product = DataProductDb(
                id=str(uuid4()), name=f"Product {i}", version="1.0", status="active"
            )
            db_session.add(product)
            db_session.flush()
            products.append(product)

            port = OutputPortDb(
                id=str(uuid4()),
                product_id=product.id,
                name="Shared Table",
                asset_type="table",
                asset_identifier="catalog.schema.shared_table",
                version="1.0",
            )
            db_session.add(port)

        db_session.flush()

        datasets = collect_datasets_from_products([p.id for p in products], db_session)

        assert datasets == ["catalog.schema.shared_table"]

    def test_returns_empty_for_missing_product(self, db_session):
        """Non-existent product ID should not crash."""
        datasets = collect_datasets_from_products(["nonexistent-id"], db_session)

        assert datasets == []

    def test_returns_empty_for_no_products(self, db_session):
        """Empty product list returns empty datasets."""
        datasets = collect_datasets_from_products([], db_session)

        assert datasets == []


# =========================================================================
# format_metadata_for_genie
# =========================================================================

class TestFormatMetadataForGenie:
    """Verify metadata formatting for Genie instructions."""

    def test_includes_product_name(self):
        """Product name should appear in formatted output."""
        product = MagicMock()
        product.id = "p1"
        product.name = "Sales Analytics"
        product.description = "Quarterly sales data"
        product.domain = "Retail"

        result = format_metadata_for_genie({}, [product])

        assert "Sales Analytics" in result
        assert "Quarterly sales data" in result
        assert "Retail" in result

    def test_truncates_at_max_length(self):
        """Output should not exceed max_length."""
        product = MagicMock()
        product.id = "p1"
        product.name = "Product"
        product.description = "x" * 6000
        product.domain = None

        result = format_metadata_for_genie({}, [product], max_length=100)

        assert len(result) <= 100

    def test_handles_empty_products(self):
        """Empty product list returns empty string."""
        result = format_metadata_for_genie({}, [])

        assert result == ""
