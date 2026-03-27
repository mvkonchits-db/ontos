"""Debug test to verify actual genie config output."""
import os
os.environ['TESTING'] = 'true'
os.environ['SKIP_STARTUP_TASKS'] = 'true'

from unittest.mock import MagicMock, patch


def test_full_genie_config_output(capsys):
    """Print the full output of generate_genie_config for inspection."""
    from src.common.genie_instruction_generator import generate_genie_config

    # Build realistic product
    product = MagicMock()
    product.name = "Asset Health Analytics"
    product.domain = None
    product.description.purpose = "A 360 view of energy asset health."
    product.id = "test-id"

    ports = []
    for name, fqn, desc in [
        ("Health", "cat.sch.gold_health", "Health metrics"),
        ("KPI", "cat.sch.gold_kpi", "KPIs per asset"),
        ("Assets", "cat.sch.silver_assets", "Asset registry"),
        ("Cost", "cat.sch.silver_cost", "Cost records"),
    ]:
        p = MagicMock()
        p.name = name
        p.asset_type = "table"
        p.asset_identifier = fqn
        p.description = desc
        p.contract_id = None
        ports.append(p)
    product.output_ports = ports

    # Mock ws_client with column data
    ws = MagicMock()
    col_data = {
        "cat.sch.gold_health": [
            ("asset_id", "STRING"), ("region", "STRING"),
            ("avg_temperature_c", "DOUBLE"), ("total_anomalies", "LONG"),
        ],
        "cat.sch.gold_kpi": [
            ("asset_id", "STRING"), ("total_work_orders", "LONG"),
            ("corrective_ratio", "DOUBLE"),
        ],
        "cat.sch.silver_assets": [
            ("asset_id", "STRING"), ("asset_type", "STRING"), ("status", "STRING"),
        ],
        "cat.sch.silver_cost": [
            ("cost_id", "STRING"), ("asset_id", "STRING"),
            ("work_order_id", "STRING"), ("category", "STRING"),
            ("amount_eur", "DOUBLE"),
        ],
    }

    def get_table(full_name):
        r = MagicMock()
        cols = col_data.get(full_name, [])
        mock_cols = []
        for c, t in cols:
            mc = MagicMock()
            mc.name = c
            mc.type_name = t
            mock_cols.append(mc)
        r.columns = mock_cols
        return r

    ws.tables.get = get_table

    with patch("src.repositories.data_products_repository.data_product_repo") as mock_repo:
        mock_repo.get.return_value = product

        config = generate_genie_config(["test-id"], MagicMock(), ws_client=ws)

    print("\n" + "=" * 60)
    print("INSTRUCTIONS:")
    print("=" * 60)
    print(config["instructions"])
    print("\n" + "=" * 60)
    print(f"SAMPLE QUESTIONS ({len(config['sample_questions'])}):")
    print("=" * 60)
    for i, q in enumerate(config["sample_questions"]):
        print(f"\n--- Question {i+1} ---")
        if isinstance(q, dict):
            print(f"  question: {q.get('question', 'MISSING')}")
            print(f"  sql:      {q.get('sql', 'NONE')}")
        else:
            print(f"  (string): {q}")
    print("\n" + "=" * 60)

    print("\n" + "=" * 60)
    print(f"JOIN SQLS ({len(config.get('join_sqls', []))}):")
    print("=" * 60)
    for j in config.get("join_sqls", []):
        print(f"  Title: {j.get('title')}")
        print(f"  SQL:   {j.get('sql')}")
    print()

    # Assertions to ensure it works
    assert config["instructions"], "Instructions should not be empty"
    assert len(config["sample_questions"]) > 0, "Should have at least one sample question"
    assert all(isinstance(q, dict) for q in config["sample_questions"]), "All questions should be dicts"
    assert all("question" in q for q in config["sample_questions"]), "All questions need 'question' key"
    assert len(config.get("join_sqls", [])) > 0, "Should have at least one join SQL"
