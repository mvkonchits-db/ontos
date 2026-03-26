# Set test environment variables BEFORE any app imports
import os
os.environ['TESTING'] = 'true'
os.environ['SKIP_STARTUP_TASKS'] = 'true'

"""
Tests for the Genie Instruction Generator.

Covers:
- generate_genie_config returns dict with 'instructions' and 'sample_questions'
- generate_genie_instructions backward compat returns string
- Products with output ports -> structured instructions
- Products with domain -> domain section included
- Truncation at max_length
- No products -> empty result
- Join detection between tables sharing column names
- Sample question generation
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock


# =========================================================================
# Helpers to build mock DB objects
# =========================================================================

def _make_description(purpose=None):
    desc = MagicMock()
    desc.purpose = purpose
    return desc


def _make_output_port(name, asset_type="table", asset_identifier=None, description=None, contract_id=None):
    port = MagicMock()
    port.name = name
    port.asset_type = asset_type
    port.asset_identifier = asset_identifier
    port.description = description
    port.contract_id = contract_id
    return port


def _make_product(pid, name, domain=None, purpose=None, output_ports=None):
    product = MagicMock()
    product.id = pid
    product.name = name
    product.domain = domain
    product.description = _make_description(purpose)
    product.output_ports = output_ports or []
    return product


def _make_domain(name, description=None):
    domain = MagicMock()
    domain.name = name
    domain.description = description
    return domain


def _make_contract(cid, name, description_purpose=None):
    contract = MagicMock()
    contract.id = cid
    contract.name = name
    contract.description_purpose = description_purpose
    return contract


def _make_column(name, type_name):
    col = MagicMock()
    col.name = name
    col.type_name = type_name
    return col


def _make_table_info(columns):
    info = MagicMock()
    info.columns = columns
    return info


# =========================================================================
# Tests for generate_genie_config (new dict return)
# =========================================================================

class TestGenerateGenieConfig:
    """Test the main generate_genie_config function."""

    def test_empty_product_ids_returns_empty_dict(self):
        """No product IDs -> empty instructions and sample_questions."""
        from src.common.genie_instruction_generator import generate_genie_config

        result = generate_genie_config(product_ids=[], db=MagicMock())
        assert isinstance(result, dict)
        assert result['instructions'] == ''
        assert result['sample_questions'] == []

    @patch("src.repositories.data_products_repository.data_product_repo")
    def test_no_products_found_returns_empty_dict(self, mock_repo):
        """All product IDs resolve to None -> empty dict."""
        from src.common.genie_instruction_generator import generate_genie_config

        mock_repo.get.return_value = None
        result = generate_genie_config(product_ids=["p1", "p2"], db=MagicMock())
        assert result['instructions'] == ''
        assert result['sample_questions'] == []

    @patch("src.repositories.data_products_repository.data_product_repo")
    def test_returns_instructions_and_sample_questions(self, mock_repo):
        """Should return both instructions string and sample questions list."""
        from src.common.genie_instruction_generator import generate_genie_config

        product = _make_product(
            "p1", "Asset Health Analytics",
            purpose="360-degree view of asset health",
            output_ports=[
                _make_output_port("gold_health", asset_identifier="cat.sch.gold_asset_health", description="Aggregated health"),
            ]
        )
        mock_repo.get.return_value = product

        result = generate_genie_config(product_ids=["p1"], db=MagicMock())

        assert isinstance(result, dict)
        assert 'instructions' in result
        assert 'sample_questions' in result
        assert isinstance(result['instructions'], str)
        assert isinstance(result['sample_questions'], list)
        assert len(result['instructions']) > 0
        assert len(result['sample_questions']) > 0

    @patch("src.repositories.data_products_repository.data_product_repo")
    def test_sample_questions_include_table_names(self, mock_repo):
        """Sample questions should reference actual table names."""
        from src.common.genie_instruction_generator import generate_genie_config

        product = _make_product(
            "p1", "Asset Analytics",
            output_ports=[
                _make_output_port("gold", asset_identifier="cat.sch.gold_health"),
                _make_output_port("silver", asset_identifier="cat.sch.silver_assets"),
            ]
        )
        mock_repo.get.return_value = product

        result = generate_genie_config(product_ids=["p1"], db=MagicMock())
        questions_text = " ".join(result['sample_questions'])

        assert "gold_health" in questions_text

    @patch("src.repositories.data_products_repository.data_product_repo")
    def test_sample_questions_capped_at_five(self, mock_repo):
        """Should not return more than 5 sample questions."""
        from src.common.genie_instruction_generator import generate_genie_config

        # Create product with many ports to trigger many questions
        ports = [
            _make_output_port(f"tbl_{i}", asset_identifier=f"cat.sch.table_{i}")
            for i in range(20)
        ]
        product = _make_product("p1", "Big Product", output_ports=ports)
        mock_repo.get.return_value = product

        result = generate_genie_config(product_ids=["p1"], db=MagicMock())

        assert len(result['sample_questions']) <= 5


# =========================================================================
# Tests for generate_genie_instructions (backward compat)
# =========================================================================

class TestGenerateGenieInstructions:
    """Test the backward-compatible generate_genie_instructions function."""

    def test_empty_product_ids_returns_empty(self):
        """No product IDs -> empty string."""
        from src.common.genie_instruction_generator import generate_genie_instructions

        result = generate_genie_instructions(product_ids=[], db=MagicMock())
        assert result == ""

    @patch("src.repositories.data_products_repository.data_product_repo")
    def test_no_products_found_returns_empty(self, mock_repo):
        """All product IDs resolve to None -> empty string."""
        from src.common.genie_instruction_generator import generate_genie_instructions

        mock_repo.get.return_value = None
        result = generate_genie_instructions(product_ids=["p1", "p2"], db=MagicMock())
        assert result == ""

    @patch("src.repositories.data_products_repository.data_product_repo")
    def test_product_with_output_ports_generates_tables(self, mock_repo):
        """Products with output ports produce a Tables section."""
        from src.common.genie_instruction_generator import generate_genie_instructions

        product = _make_product(
            "p1", "Asset Health Analytics",
            purpose="360-degree view of asset health",
            output_ports=[
                _make_output_port("gold_health", asset_identifier="cat.sch.gold_asset_health", description="Aggregated health"),
                _make_output_port("silver_assets", asset_identifier="cat.sch.silver_assets", description="Master registry"),
            ]
        )
        mock_repo.get.return_value = product

        result = generate_genie_instructions(product_ids=["p1"], db=MagicMock())

        assert "## Data Product: Asset Health Analytics" in result
        assert "360-degree view of asset health" in result
        assert "### Tables" in result
        assert "gold_asset_health" in result
        assert "silver_assets" in result

    @patch("src.repositories.data_products_repository.data_product_repo")
    def test_domain_section_included(self, mock_repo):
        """Products with a domain generate a Domain header."""
        from src.common.genie_instruction_generator import generate_genie_instructions

        product = _make_product(
            "p1", "Energy Product",
            domain="Energy Operations",
            output_ports=[
                _make_output_port("tbl", asset_identifier="cat.sch.energy_data"),
            ]
        )
        mock_repo.get.return_value = product

        mock_db = MagicMock()
        mock_domain = _make_domain("Energy Operations", "Solar and wind energy management")
        # Mock the domain query
        mock_db.query.return_value.filter.return_value.first.return_value = mock_domain

        result = generate_genie_instructions(product_ids=["p1"], db=mock_db)

        assert "# Domain: Energy Operations" in result
        assert "Solar and wind energy management" in result

    @patch("src.repositories.data_products_repository.data_product_repo")
    def test_truncation_at_max_length(self, mock_repo):
        """Output must not exceed max_length."""
        from src.common.genie_instruction_generator import generate_genie_instructions

        # Create a product with many ports to generate long output
        ports = [
            _make_output_port(f"table_{i}", asset_identifier=f"cat.sch.table_{i}", description="A" * 100)
            for i in range(50)
        ]
        product = _make_product("p1", "Big Product", purpose="X" * 200, output_ports=ports)
        mock_repo.get.return_value = product

        result = generate_genie_instructions(product_ids=["p1"], db=MagicMock(), max_length=500)

        assert len(result) <= 500
        assert result.endswith("...")

    @patch("src.repositories.data_products_repository.data_product_repo")
    def test_join_detection_shared_columns(self, mock_repo):
        """Tables sharing column names produce join hints in instructions."""
        from src.common.genie_instruction_generator import generate_genie_instructions

        product = _make_product(
            "p1", "Asset Analytics",
            output_ports=[
                _make_output_port("gold", asset_identifier="cat.sch.gold_health"),
                _make_output_port("silver", asset_identifier="cat.sch.silver_assets"),
            ]
        )
        mock_repo.get.return_value = product

        # Mock ws_client to return columns with shared asset_id
        ws_client = MagicMock()

        def mock_tables_get(full_name):
            if "gold_health" in full_name:
                return _make_table_info([
                    _make_column("asset_id", "string"),
                    _make_column("health_score", "double"),
                ])
            elif "silver_assets" in full_name:
                return _make_table_info([
                    _make_column("asset_id", "string"),
                    _make_column("asset_name", "string"),
                ])
            return _make_table_info([])

        ws_client.tables.get.side_effect = mock_tables_get

        result = generate_genie_instructions(
            product_ids=["p1"], db=MagicMock(), ws_client=ws_client
        )

        # Join hints should mention asset_id and the table names
        assert "asset_id" in result
        assert "gold_health" in result
        assert "silver_assets" in result

    @patch("src.repositories.data_products_repository.data_product_repo")
    def test_column_details_with_ws_client(self, mock_repo):
        """When ws_client is available, column count and names appear."""
        from src.common.genie_instruction_generator import generate_genie_instructions

        product = _make_product(
            "p1", "Product A",
            output_ports=[
                _make_output_port("tbl", asset_identifier="cat.sch.my_table"),
            ]
        )
        mock_repo.get.return_value = product

        ws_client = MagicMock()
        ws_client.tables.get.return_value = _make_table_info([
            _make_column("col_a", "string"),
            _make_column("col_b", "int"),
            _make_column("col_c", "double"),
        ])

        result = generate_genie_instructions(
            product_ids=["p1"], db=MagicMock(), ws_client=ws_client
        )

        assert "3 columns" in result
        assert "col_a" in result
        assert "col_b" in result

    @patch("src.repositories.data_products_repository.data_product_repo")
    def test_no_ws_client_skips_columns(self, mock_repo):
        """Without ws_client, tables are listed without column details."""
        from src.common.genie_instruction_generator import generate_genie_instructions

        product = _make_product(
            "p1", "Product A",
            output_ports=[
                _make_output_port("tbl", asset_identifier="cat.sch.my_table", description="Some table"),
            ]
        )
        mock_repo.get.return_value = product

        result = generate_genie_instructions(
            product_ids=["p1"], db=MagicMock(), ws_client=None
        )

        assert "my_table" in result
        assert "Some table" in result
        # No column count since ws_client is None
        assert "columns" not in result

    @patch("src.repositories.data_products_repository.data_product_repo")
    def test_contract_info_included(self, mock_repo):
        """Output ports with contract_id produce contract section."""
        from src.common.genie_instruction_generator import generate_genie_instructions

        product = _make_product(
            "p1", "Product A",
            output_ports=[
                _make_output_port(
                    "tbl", asset_identifier="cat.sch.tbl",
                    contract_id="contract-1"
                ),
            ]
        )
        mock_repo.get.return_value = product

        mock_db = MagicMock()
        mock_contract = _make_contract("contract-1", "Asset Health Contract", "Schema expectations")

        # The DB will be queried for domain (returns None) and for contract
        def side_effect_query(model):
            query_mock = MagicMock()
            if model.__name__ == "DataDomain":
                query_mock.filter.return_value.first.return_value = None
            else:
                query_mock.filter.return_value.first.return_value = mock_contract
            return query_mock

        mock_db.query.side_effect = side_effect_query

        result = generate_genie_instructions(product_ids=["p1"], db=mock_db)

        assert "### Data Contract: Asset Health Contract" in result
        assert "Schema expectations" in result


class TestJoinDetection:
    """Focused tests for the _build_join_section helper (backward compat)."""

    def test_single_table_no_joins(self):
        from src.common.genie_instruction_generator import _build_join_section

        result = _build_join_section({
            "cat.sch.tbl1": [("col_a", "string")],
        })
        assert result == ""

    def test_no_shared_columns_no_joins(self):
        from src.common.genie_instruction_generator import _build_join_section

        result = _build_join_section({
            "cat.sch.tbl1": [("col_a", "string")],
            "cat.sch.tbl2": [("col_b", "string")],
        })
        assert result == ""

    def test_shared_column_produces_hint(self):
        from src.common.genie_instruction_generator import _build_join_section

        result = _build_join_section({
            "cat.sch.tbl1": [("asset_id", "string"), ("name", "string")],
            "cat.sch.tbl2": [("asset_id", "string"), ("score", "double")],
        })
        assert "asset_id" in result
        assert "tbl1" in result
        assert "tbl2" in result

    def test_generic_columns_skipped(self):
        """Columns like 'id', 'created_at' should be skipped for join hints."""
        from src.common.genie_instruction_generator import _build_join_section

        result = _build_join_section({
            "cat.sch.tbl1": [("id", "string"), ("created_at", "timestamp")],
            "cat.sch.tbl2": [("id", "string"), ("created_at", "timestamp")],
        })
        assert result == ""

    def test_multiple_shared_columns(self):
        from src.common.genie_instruction_generator import _build_join_section

        result = _build_join_section({
            "cat.sch.tbl1": [("asset_id", "string"), ("region", "string")],
            "cat.sch.tbl2": [("asset_id", "string"), ("region", "string")],
        })
        assert "asset_id" in result
        assert "region" in result
