"""
Genie Spaces Client

Provides functions for creating Databricks Genie Spaces from Data Products.
Uses the ``/api/2.0/data-rooms/`` REST API with separate calls for
instructions and sample questions.
"""

from typing import List, Dict, Optional, Any
from databricks.sdk import WorkspaceClient
from sqlalchemy.orm import Session

from src.common.logging import get_logger

logger = get_logger(__name__)


def create_genie_space(
    ws_client: WorkspaceClient,
    name: str,
    datasets: List[str],
    warehouse_id: str,
    description: Optional[str] = None,
    instructions: Optional[str] = None,
    sample_questions: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Create a Genie Space using the data-rooms REST API.

    Steps:
      1. POST /api/2.0/data-rooms/ with table_identifiers
      2. POST instructions (if provided)
      3. POST sample questions (if provided)

    Args:
        ws_client: Databricks workspace client
        name: Space display name
        datasets: List of catalog.schema.table identifiers
        warehouse_id: SQL warehouse ID for the space
        description: Optional space description
        instructions: Optional context/instructions text
        sample_questions: Optional list of sample question strings

    Returns:
        Dict with space_id, space_url, status

    Raises:
        ValueError: If no datasets provided or warehouse_id missing
        Exception: On API failure
    """
    if not datasets:
        raise ValueError("At least one dataset is required to create a Genie Space")
    if not warehouse_id:
        raise ValueError("warehouse_id is required to create a Genie Space")

    logger.info(f"Creating Genie Space '{name}' with {len(datasets)} datasets on warehouse {warehouse_id}")

    # Step 1: Create space via data-rooms API
    payload = {
        "display_name": name,
        "warehouse_id": warehouse_id,
        "table_identifiers": datasets,
        "run_as_type": "VIEWER",
    }
    if description:
        payload["description"] = description

    try:
        result = ws_client.api_client.do('POST', '/api/2.0/data-rooms/', body=payload)
        space_id = result.get('space_id') or result.get('id')

        if not space_id:
            raise ValueError("No space_id returned from Genie API")

        logger.info(f"Created Genie Space: {space_id}")

        # Step 2: Add instructions (if provided)
        if instructions:
            try:
                ws_client.api_client.do(
                    'POST',
                    f'/api/2.0/data-rooms/{space_id}/instructions',
                    body={
                        "title": "Product Context",
                        "content": instructions[:5000],
                        "instruction_type": "TEXT_INSTRUCTION",
                    },
                )
                logger.info(f"Added instructions to Genie Space {space_id}")
            except Exception as e:
                logger.warning(f"Failed to add instructions to space {space_id}: {e}")

        # Step 3: Add sample questions (if provided)
        if sample_questions:
            added = 0
            for q in sample_questions:
                try:
                    ws_client.api_client.do(
                        'POST',
                        f'/api/2.0/data-rooms/{space_id}/curated-questions',
                        body={
                            "curated_question": {
                                "question_text": q,
                                "question_type": "SAMPLE_QUESTION",
                            }
                        },
                    )
                    added += 1
                except Exception as e:
                    logger.warning(f"Failed to add sample question to space {space_id}: {e}")
            logger.info(f"Added {added}/{len(sample_questions)} sample questions to Genie Space {space_id}")

        workspace_url = ws_client.config.host.rstrip('/')
        space_url = f"{workspace_url}/genie/rooms/{space_id}"

        logger.info(f"Genie Space URL: {space_url}")

        return {
            'space_id': space_id,
            'space_url': space_url,
            'status': 'active',
        }

    except Exception as e:
        logger.error(f"Failed to create Genie Space: {e}", exc_info=True)
        raise


def delete_genie_space(ws_client: WorkspaceClient, space_id: str) -> None:
    """Delete a Genie Space from Databricks.

    Args:
        ws_client: Databricks workspace client
        space_id: The Genie space ID to delete
    """
    logger.info(f"Deleting Genie Space: {space_id}")
    ws_client.api_client.do('DELETE', f'/api/2.0/data-rooms/{space_id}')
    logger.info(f"Deleted Genie Space: {space_id}")


def update_genie_space_instructions(
    ws_client: WorkspaceClient, space_id: str, instructions: str
) -> None:
    """Replace all instructions on a Genie Space.

    Deletes existing instructions then adds the new one.

    Args:
        ws_client: Databricks workspace client
        space_id: The Genie space ID
        instructions: New instruction text
    """
    # Delete existing instructions
    try:
        existing = ws_client.api_client.do(
            'GET', f'/api/2.0/data-rooms/{space_id}/instructions'
        )
        for instr in existing.get('instructions', []):
            ws_client.api_client.do(
                'DELETE',
                f'/api/2.0/data-rooms/{space_id}/instructions/{instr["id"]}',
            )
    except Exception:
        pass

    # Add new instructions
    ws_client.api_client.do(
        'POST',
        f'/api/2.0/data-rooms/{space_id}/instructions',
        body={"instruction_text": instructions[:5000]},
    )
    logger.info(f"Updated instructions for Genie Space {space_id}")


def collect_datasets_from_products(product_ids: List[str], db: Session) -> List[str]:
    """
    Collect all dataset identifiers from Data Product output ports.

    Args:
        product_ids: List of Data Product UUIDs
        db: Database session

    Returns:
        List of catalog.schema.table identifiers (deduplicated)
    """
    from src.repositories.data_products_repository import data_product_repo

    datasets = []
    logger.info(f"Collecting datasets from {len(product_ids)} products")

    for product_id in product_ids:
        try:
            product_db = data_product_repo.get(db, id=product_id)
            if not product_db:
                logger.warning(f"Product not found: {product_id}")
                continue

            logger.debug(f"Processing product: {product_db.name} ({product_id})")

            for port in product_db.output_ports:
                if port.asset_type in ['table', 'view'] and port.asset_identifier:
                    datasets.append(port.asset_identifier)
                    logger.debug(f"Added dataset: {port.asset_identifier} from port {port.name}")
                else:
                    logger.debug(f"Skipping port {port.name}: type={port.asset_type}, identifier={port.asset_identifier}")

        except Exception as e:
            logger.error(f"Error collecting datasets from product {product_id}: {e}", exc_info=True)

    # Deduplicate while preserving order
    unique_datasets = list(dict.fromkeys(datasets))
    logger.info(f"Collected {len(unique_datasets)} unique datasets from {len(datasets)} total")

    return unique_datasets


def collect_rich_text_metadata(product_ids: List[str], db: Session) -> Dict[str, List]:
    """
    Collect RichTextMetadataDb entries for products and their linked contracts.

    Args:
        product_ids: List of Data Product UUIDs
        db: Database session

    Returns:
        Dict mapping entity_id to list of metadata entries
    """
    from src.repositories.data_products_repository import data_product_repo
    from src.db_models.metadata import RichTextMetadataDb

    metadata_map = {}
    logger.info(f"Collecting rich text metadata for {len(product_ids)} products")

    for product_id in product_ids:
        try:
            # Get product-level metadata
            product_metadata = db.query(RichTextMetadataDb).filter(
                RichTextMetadataDb.entity_type == 'data_product',
                RichTextMetadataDb.entity_id == product_id
            ).all()

            if product_metadata:
                metadata_map[product_id] = product_metadata
                logger.debug(f"Found {len(product_metadata)} metadata entries for product {product_id}")

            # Get contract metadata from output ports
            product_db = data_product_repo.get(db, id=product_id)
            if product_db:
                for port in product_db.output_ports:
                    if port.contract_id:
                        contract_metadata = db.query(RichTextMetadataDb).filter(
                            RichTextMetadataDb.entity_type == 'data_contract',
                            RichTextMetadataDb.entity_id == port.contract_id
                        ).all()

                        if contract_metadata:
                            metadata_map[port.contract_id] = contract_metadata
                            logger.debug(f"Found {len(contract_metadata)} metadata entries for contract {port.contract_id}")

        except Exception as e:
            logger.error(f"Error collecting metadata for product {product_id}: {e}", exc_info=True)

    logger.info(f"Collected metadata for {len(metadata_map)} entities")
    return metadata_map


def format_metadata_for_genie(
    metadata_map: Dict[str, List],
    products: List,
    max_length: int = 5000
) -> str:
    """
    Format collected metadata as markdown instructions for Genie.

    Args:
        metadata_map: Dict of entity_id -> metadata entries
        products: List of DataProductDb objects
        max_length: Maximum character length (default 5000)

    Returns:
        Formatted markdown string
    """
    sections = []
    logger.info(f"Formatting metadata for {len(products)} products")

    for product in products:
        section_parts = [f"## Data Product: {product.name}\n"]

        if hasattr(product, 'description') and product.description:
            section_parts.append(f"**Description**: {product.description}\n")

        if hasattr(product, 'domain') and product.domain:
            section_parts.append(f"**Domain**: {product.domain}\n")

        section_parts.append("\n")

        # Add rich text metadata for this product
        if product.id in metadata_map:
            for meta in metadata_map[product.id]:
                section_parts.append(f"### {meta.title}\n\n")

                if meta.short_description:
                    section_parts.append(f"{meta.short_description}\n\n")

                if meta.content_markdown:
                    content = meta.content_markdown
                    if len(content) > 1000:
                        content = content[:997] + "..."
                    section_parts.append(f"{content}\n\n")

        sections.append("".join(section_parts))

    formatted = "\n".join(sections)

    if len(formatted) > max_length:
        formatted = formatted[:max_length - 3] + "..."
        logger.warning(f"Metadata truncated to {max_length} characters")

    logger.info(f"Formatted metadata: {len(formatted)} characters")
    return formatted
