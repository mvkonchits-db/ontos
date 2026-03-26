"""
Genie Instruction Generator

Generates rich Genie Space instructions by assembling product metadata,
table schemas, domain context, join hints, and data contract info.

Returns a dict with 'instructions' (text) and 'sample_questions' (list).

Phase 2 of Genie Space PRD — enriching instructions beyond basic rich-text metadata.
"""

from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from src.common.logging import get_logger

logger = get_logger(__name__)


def generate_genie_config(
    product_ids: List[str],
    db: Session,
    ws_client=None,
    max_instruction_length: int = 5000,
) -> Dict:
    """Generate structured Genie Space config from product metadata.

    Assembles domain descriptions, product info, table schemas with column
    details (via Unity Catalog), compact join hints within product sections,
    and linked data contract context.

    Args:
        product_ids: Data Product UUIDs to include.
        db: SQLAlchemy session.
        ws_client: Optional Databricks WorkspaceClient for UC column metadata.
        max_instruction_length: Maximum character length for instructions (default 5000).

    Returns:
        Dict with:
          - 'instructions': Markdown-formatted instruction string
          - 'sample_questions': List of auto-generated sample question strings
        Returns {'instructions': '', 'sample_questions': []} if no products found.
    """
    empty_result = {'instructions': '', 'sample_questions': []}

    if not product_ids:
        return empty_result

    import src.repositories.data_products_repository as _dp_repo_mod
    from src.db_models.data_domains import DataDomain as DataDomainDb
    from src.db_models.data_contracts import DataContractDb

    data_product_repo = _dp_repo_mod.data_product_repo

    # Collect products
    products = []
    for pid in product_ids:
        try:
            product = data_product_repo.get(db, id=pid)
            if product:
                products.append(product)
            else:
                logger.warning(f"Product not found: {pid}")
        except Exception as e:
            logger.error(f"Error loading product {pid}: {e}", exc_info=True)

    if not products:
        return empty_result

    # ── Section builders (ordered by priority for truncation) ──

    # 1. Domain context
    domain_sections = _build_domain_sections(products, db, DataDomainDb)

    # 2. Product + table descriptions (with inline join hints)
    product_sections = []
    all_table_columns: Dict[str, List[Tuple[str, str]]] = {}  # fqn -> [(col, type)]

    for product in products:
        section, table_cols = _build_product_section(product, db, ws_client, DataContractDb)
        product_sections.append(section)
        all_table_columns.update(table_cols)

    # 3. Generate compact join notes per product section
    join_notes = _build_compact_join_notes(all_table_columns)

    # 4. Assemble instructions with priority-based truncation
    instructions = _assemble_and_truncate(
        domain_sections=domain_sections,
        product_sections=product_sections,
        join_notes=join_notes,
        max_length=max_instruction_length,
    )

    # 5. Generate sample questions from product context
    sample_questions = _generate_sample_questions(products)

    return {
        'instructions': instructions,
        'sample_questions': sample_questions,
    }


# Keep backward-compatible alias that returns just the instruction string
def generate_genie_instructions(
    product_ids: List[str],
    db: Session,
    ws_client=None,
    max_length: int = 5000,
) -> str:
    """Generate structured Genie Space instructions from product metadata.

    Backward-compatible wrapper around generate_genie_config that returns
    only the instructions string.

    Args:
        product_ids: Data Product UUIDs to include.
        db: SQLAlchemy session.
        ws_client: Optional Databricks WorkspaceClient for UC column metadata.
        max_length: Maximum character length for the output (default 5000).

    Returns:
        Markdown-formatted instruction string, or empty string if no products found.
    """
    config = generate_genie_config(
        product_ids=product_ids,
        db=db,
        ws_client=ws_client,
        max_instruction_length=max_length,
    )
    return config.get('instructions', '')


def _build_domain_sections(products, db: Session, DataDomainDb) -> str:
    """Build domain header section from products that have a domain set."""
    seen_domains: Set[str] = set()
    parts = []

    for product in products:
        if not product.domain or product.domain in seen_domains:
            continue
        seen_domains.add(product.domain)
        try:
            domain = db.query(DataDomainDb).filter(DataDomainDb.name == product.domain).first()
            if domain:
                parts.append(f"# Domain: {domain.name}")
                if domain.description:
                    parts.append(domain.description)
                parts.append("")
        except Exception as e:
            logger.warning(f"Could not load domain '{product.domain}': {e}")

    return "\n".join(parts)


def _build_product_section(
    product, db: Session, ws_client, DataContractDb
) -> Tuple[str, Dict[str, List[Tuple[str, str]]]]:
    """Build a single product section with tables and optional contract info.

    Returns:
        (section_text, table_columns_map) where table_columns_map maps
        FQN -> list of (column_name, type_name) tuples.
    """
    lines = [f"## Data Product: {product.name}"]

    # Product description (via the relationship)
    if product.description and product.description.purpose:
        lines.append(f"Purpose: {product.description.purpose}")

    # Tables from output ports
    table_columns: Dict[str, List[Tuple[str, str]]] = {}
    table_lines = []
    contract_ids: Set[str] = set()

    for port in (product.output_ports or []):
        if port.asset_type not in ("table", "view") or not port.asset_identifier:
            continue

        fqn = port.asset_identifier
        short_name = fqn.rsplit(".", 1)[-1] if "." in fqn else fqn
        cols = _get_table_columns(fqn, ws_client)
        table_columns[fqn] = cols

        if cols:
            col_preview = ", ".join(f"{c}" for c, _ in cols[:6])
            if len(cols) > 6:
                col_preview += ", ..."
            desc = port.description or ""
            desc_part = f" {desc}" if desc else ""
            table_lines.append(
                f"- {short_name}:{desc_part} ({len(cols)} columns: {col_preview})"
            )
        else:
            desc = port.description or ""
            desc_part = f" {desc}" if desc else ""
            table_lines.append(f"- {short_name}:{desc_part}")

        if port.contract_id:
            contract_ids.add(port.contract_id)

    if table_lines:
        lines.append("")
        lines.append("### Tables")
        lines.extend(table_lines)

    # Contract info
    contract_section = _build_contract_section(contract_ids, db, DataContractDb)
    if contract_section:
        lines.append("")
        lines.append(contract_section)

    lines.append("")
    return "\n".join(lines), table_columns


def _get_table_columns(fqn: str, ws_client) -> List[Tuple[str, str]]:
    """Fetch column names and types from Unity Catalog via ws_client.tables.get().

    Returns empty list if ws_client is unavailable or the call fails.
    """
    if not ws_client:
        return []
    try:
        table_info = ws_client.tables.get(full_name=fqn)
        if table_info and table_info.columns:
            return [
                (col.name, col.type_name or "unknown")
                for col in table_info.columns
            ]
    except Exception as e:
        logger.debug(f"Could not fetch columns for {fqn}: {e}")
    return []


def _build_contract_section(contract_ids: Set[str], db: Session, DataContractDb) -> str:
    """Build contract context lines for linked contracts."""
    if not contract_ids:
        return ""

    parts = []
    for cid in contract_ids:
        try:
            contract = db.query(DataContractDb).filter(DataContractDb.id == cid).first()
            if contract:
                line = f"### Data Contract: {contract.name}"
                if contract.description_purpose:
                    line += f"\n{contract.description_purpose}"
                parts.append(line)
        except Exception as e:
            logger.debug(f"Could not load contract {cid}: {e}")

    return "\n".join(parts)


def _build_compact_join_notes(
    all_table_columns: Dict[str, List[Tuple[str, str]]]
) -> str:
    """Detect shared column names across tables and generate compact join notes.

    Instead of a separate "### Join Relationships" section, produces a concise
    note suitable for appending after the Tables listing.
    """
    if len(all_table_columns) < 2:
        return ""

    # Build reverse index: column_name -> set of FQNs
    col_to_tables: Dict[str, Set[str]] = defaultdict(set)
    for fqn, cols in all_table_columns.items():
        for col_name, _ in cols:
            col_to_tables[col_name].add(fqn)

    # Find columns present in 2+ tables (skip generic ones like "id")
    skip_cols = {"id", "created_at", "updated_at", "created_by", "updated_by"}
    join_hints = []

    for col_name, fqns in sorted(col_to_tables.items()):
        if col_name in skip_cols or len(fqns) < 2:
            continue
        short_names = sorted(fqn.rsplit(".", 1)[-1] for fqn in fqns)
        join_hints.append(f"- {' & '.join(short_names)}: join on {col_name}")

    if not join_hints:
        return ""

    # Deduplicate pairs that might appear from multiple shared columns
    unique_hints = list(dict.fromkeys(join_hints))
    lines = ["Join hints:"]
    lines.extend(unique_hints)
    return "\n".join(lines)


# Keep the old function name for backward compatibility in tests
def _build_join_section(
    all_table_columns: Dict[str, List[Tuple[str, str]]]
) -> str:
    """Detect shared column names across tables and generate join hints.

    Backward-compatible wrapper that produces the old "### Join Relationships"
    format used by existing tests.
    """
    if len(all_table_columns) < 2:
        return ""

    col_to_tables: Dict[str, Set[str]] = defaultdict(set)
    for fqn, cols in all_table_columns.items():
        for col_name, _ in cols:
            col_to_tables[col_name].add(fqn)

    skip_cols = {"id", "created_at", "updated_at", "created_by", "updated_by"}
    join_hints = []

    for col_name, fqns in sorted(col_to_tables.items()):
        if col_name in skip_cols or len(fqns) < 2:
            continue
        sorted_fqns = sorted(fqns)
        for i in range(len(sorted_fqns)):
            for j in range(i + 1, len(sorted_fqns)):
                t1 = sorted_fqns[i].rsplit(".", 1)[-1]
                t2 = sorted_fqns[j].rsplit(".", 1)[-1]
                join_hints.append(f"- {t1} <> {t2}: join on {col_name}")

    if not join_hints:
        return ""

    lines = ["### Join Relationships"]
    lines.extend(join_hints)
    return "\n".join(lines)


def _generate_sample_questions(products) -> List[str]:
    """Generate 3-5 sample questions from product context.

    Creates relevant natural-language questions based on product names,
    table names, and domain context.
    """
    questions = []

    for product in products:
        product_label = product.name.lower()

        # Get table short names from output ports
        table_names = []
        for port in (product.output_ports or []):
            if port.asset_type in ("table", "view") and port.asset_identifier:
                short = port.asset_identifier.rsplit(".", 1)[-1] if "." in port.asset_identifier else port.asset_identifier
                table_names.append(short)

        if table_names:
            first_table = table_names[0]
            questions.append(f"Show me the top 10 records from {first_table}")
            if len(table_names) > 1:
                questions.append(f"How many records are in each of the {product_label} tables?")

        questions.append(f"What are the key trends in {product_label}?")

    # Cap at 5 questions
    return questions[:5]


def _assemble_and_truncate(
    domain_sections: str,
    product_sections: List[str],
    join_notes: str,
    max_length: int,
) -> str:
    """Assemble all sections and truncate with priority.

    Priority (keep first, trim last):
    1. Domain context
    2. Product + table descriptions
    3. Join notes
    """
    parts = []
    if domain_sections:
        parts.append(domain_sections)
    parts.extend(product_sections)
    if join_notes:
        parts.append(join_notes)

    result = "\n".join(parts).strip()

    if len(result) <= max_length:
        return result

    # Truncate: drop join notes first, then trim product sections
    parts_no_joins = []
    if domain_sections:
        parts_no_joins.append(domain_sections)
    parts_no_joins.extend(product_sections)
    result = "\n".join(parts_no_joins).strip()

    if len(result) <= max_length:
        return result

    # Hard truncate with ellipsis
    result = result[: max_length - 3] + "..."
    logger.warning(f"Genie instructions truncated to {max_length} characters")
    return result
