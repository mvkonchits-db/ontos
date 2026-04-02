"""
Genie Space API Routes

List and inspect Genie Spaces created from Data Products.
Creation is handled via POST /api/data-products/genie-space.
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import List

from src.common.dependencies import CurrentUserDep, DBSessionDep
from src.common.authorization import PermissionChecker
from src.common.features import FeatureAccessLevel
from src.repositories.genie_spaces_repository import genie_space_repo
from src.models.genie_spaces import GenieSpace
from src.common.logging import get_logger

logger = get_logger(__name__)

# Feature ID — reuse data products since Genie Spaces are created from them
DATA_PRODUCTS_FEATURE_ID = "data_products"

router = APIRouter(prefix="/api/genie-spaces", tags=["Genie Spaces"])


@router.get("", response_model=List[GenieSpace])
async def list_genie_spaces(
    db: DBSessionDep,
    current_user: CurrentUserDep,
    limit: int = 100,
):
    """List all Genie Spaces visible to the current user."""
    try:
        spaces = genie_space_repo.get_active_spaces(db, limit=limit)
        return [_to_response(s) for s in spaces]
    except Exception as e:
        logger.exception(f"Error listing Genie Spaces: {e}")
        raise HTTPException(status_code=500, detail="Failed to list Genie Spaces")


@router.get("/my", response_model=List[GenieSpace])
async def list_my_genie_spaces(
    db: DBSessionDep,
    current_user: CurrentUserDep,
    limit: int = 100,
):
    """List Genie Spaces created by the current user."""
    try:
        spaces = genie_space_repo.get_by_created_by(db, user_email=current_user.email, limit=limit)
        return [_to_response(s) for s in spaces]
    except Exception as e:
        logger.exception(f"Error listing user Genie Spaces: {e}")
        raise HTTPException(status_code=500, detail="Failed to list Genie Spaces")


@router.get("/{space_id}", response_model=GenieSpace)
async def get_genie_space(
    space_id: str,
    db: DBSessionDep,
    current_user: CurrentUserDep,
):
    """Get a Genie Space by its Databricks space ID."""
    try:
        space = genie_space_repo.get_by_space_id(db, space_id=space_id)
        if not space:
            raise HTTPException(status_code=404, detail=f"Genie Space '{space_id}' not found")
        return _to_response(space)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error fetching Genie Space {space_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch Genie Space")


@router.delete("/{space_id}")
async def delete_genie_space_endpoint(
    space_id: str,
    db: DBSessionDep,
    current_user: CurrentUserDep,
):
    """Delete a Genie Space by its Databricks space ID."""
    from src.common import genie_client
    from src.common.workspace_client import get_workspace_client

    try:
        # Verify the space exists in the local DB
        space = genie_space_repo.get_by_space_id(db, space_id=space_id)
        if not space:
            raise HTTPException(status_code=404, detail=f"Genie Space '{space_id}' not found")

        # Delete from Databricks
        try:
            ws = get_workspace_client()
            genie_client.delete_genie_space(ws, space_id)
        except Exception as e:
            logger.warning(f"Failed to delete Genie Space from Databricks (may already be deleted): {e}")

        # Delete from local DB
        genie_space_repo.delete_by_space_id(db, space_id)
        db.commit()

        logger.info(f"Deleted Genie Space {space_id} by {current_user.email}")
        return {"detail": "Genie Space deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error deleting Genie Space {space_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete Genie Space")


def register_routes(app):
    app.include_router(router)


def _to_response(db_obj) -> GenieSpace:
    """Convert GenieSpaceDb to GenieSpace response model."""
    return GenieSpace(
        id=str(db_obj.id),
        space_id=db_obj.space_id,
        space_name=db_obj.space_name,
        space_url=db_obj.space_url,
        status=db_obj.status,
        datasets=db_obj.datasets,
        product_ids=db_obj.product_ids,
        instructions=db_obj.instructions,
        created_by=db_obj.created_by,
        error_message=db_obj.error_message,
        created_at=db_obj.created_at,
        updated_at=db_obj.updated_at,
    )
