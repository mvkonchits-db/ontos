# Set test environment variables BEFORE any app imports
import os
os.environ['TESTING'] = 'true'
os.environ['SKIP_STARTUP_TASKS'] = 'true'

"""
Tests for the Genie Spaces client and routes.

Covers:
- Serialized space payload construction
- Dataset collection from product output ports
- Metadata formatting with truncation
- Genie Space API route responses
"""

import json
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4

from src.common.genie_client import (
    _build_serialized_space,
    collect_datasets_from_products,
    format_metadata_for_genie,
    create_genie_space,
)


# =========================================================================
# _build_serialized_space
# =========================================================================

class TestBuildSerializedSpace:
    """Verify the Genie API payload format is correct."""

    def test_basic_payload_structure(self):
        """Payload must have version, data_sources.tables, and config."""
        result = json.loads(_build_serialized_space(["cat.sch.tbl1"]))

        assert result["version"] == 2
        assert "data_sources" in result
        assert "tables" in result["data_sources"]
        assert result["data_sources"]["tables"] == [{"identifier": "cat.sch.tbl1"}]

    def test_tables_sorted_alphabetically(self):
        """Tables must be sorted by identifier for deterministic API calls."""
        result = json.loads(_build_serialized_space(["z.z.z", "a.a.a", "m.m.m"]))

        identifiers = [t["identifier"] for t in result["data_sources"]["tables"]]
        assert identifiers == ["a.a.a", "m.m.m", "z.z.z"]

    def test_instructions_included_when_provided(self):
        """Instructions should appear in text_instructions with a valid hex ID."""
        result = json.loads(_build_serialized_space(
            ["cat.sch.tbl"],
            instructions="Use this table for sales analytics."
        ))

        assert "instructions" in result
        text_instructions = result["instructions"]["text_instructions"]
        assert len(text_instructions) == 1
        assert text_instructions[0]["content"] == ["Use this table for sales analytics."]
        # ID should be 32-char hex
        assert len(text_instructions[0]["id"]) == 32

    def test_instructions_truncated_to_5000_chars(self):
        """Instructions exceeding 5000 chars should be truncated."""
        long_text = "x" * 10000
        result = json.loads(_build_serialized_space(["cat.sch.tbl"], instructions=long_text))

        content = result["instructions"]["text_instructions"][0]["content"][0]
        assert len(content) == 5000

    def test_no_instructions_when_none(self):
        """No instructions key when instructions is None."""
        result = json.loads(_build_serialized_space(["cat.sch.tbl"]))

        assert "instructions" not in result

    def test_multiple_tables(self):
        """Multiple datasets produce multiple table entries."""
        datasets = [f"cat.sch.tbl{i}" for i in range(5)]
        result = json.loads(_build_serialized_space(datasets))

        assert len(result["data_sources"]["tables"]) == 5


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


# =========================================================================
# create_genie_space (mocked SDK)
# =========================================================================

class TestCreateGenieSpace:
    """Verify the SDK call is made correctly."""

    def test_calls_sdk_create_space(self):
        """Should call ws.genie.create_space with correct args."""
        mock_ws = MagicMock(spec=['genie', 'config'])
        mock_ws.config.host = "https://workspace.databricks.com"

        mock_response = MagicMock()
        mock_response.space_id = "space-abc-123"
        mock_ws.genie.create_space.return_value = mock_response

        result = create_genie_space(
            ws_client=mock_ws,
            name="Test Space",
            datasets=["cat.sch.tbl"],
            warehouse_id="wh-123",
            description="A test space",
            instructions="Use this for testing",
        )

        assert result["space_id"] == "space-abc-123"
        assert "genie/rooms/space-abc-123" in result["space_url"]
        assert result["status"] == "active"

        # Verify SDK was called with correct args
        call_kwargs = mock_ws.genie.create_space.call_args.kwargs
        assert call_kwargs["warehouse_id"] == "wh-123"
        assert call_kwargs["title"] == "Test Space"
        assert call_kwargs["description"] == "A test space"
        # Verify serialized_space is valid JSON
        serialized = json.loads(call_kwargs["serialized_space"])
        assert serialized["version"] == 2
        assert serialized["data_sources"]["tables"] == [{"identifier": "cat.sch.tbl"}]

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
