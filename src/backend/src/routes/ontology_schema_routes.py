"""API routes for the ontology-driven schema manager.

Exposes entity type definitions, field schemas, relationship rules,
and hierarchy information derived from the ontos-ontology.ttl RDF graph.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from src.models.ontology_schema import (
    AssetTypeSyncResult,
    EntityHierarchyNode,
    EntityRelationships,
    EntityTypeDefinition,
    EntityTypeSchema,
)
from src.controller.ontology_schema_manager import OntologySchemaManager
from src.common.authorization import PermissionChecker
from src.common.features import FeatureAccessLevel
from src.common.dependencies import (
    DBSessionDep,
    AuditManagerDep,
    AuditCurrentUserDep,
)
from src.common.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/ontology", tags=["Ontology Schema"])
FEATURE_ID = "ontology"


def get_ontology_schema_manager(request: Request) -> OntologySchemaManager:
    mgr = getattr(request.app.state, "ontology_schema_manager", None)
    if not mgr:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ontology Schema manager not configured.",
        )
    return mgr


# ===================== Entity Types =====================


@router.get(
    "/entity-types",
    response_model=List[EntityTypeDefinition],
    summary="List all entity types defined in the ontology",
)
def list_entity_types(
    request: Request,
    tier: Optional[str] = Query(None, description="Filter by model tier: 'dedicated' or 'asset'"),
    category: Optional[str] = Query(None, description="Filter by UI category: data, governance, analytics, integration, system"),
    persona: Optional[str] = Query(None, description="Filter by persona visibility: admin, steward, producer, consumer"),
    db: DBSessionDep = None,
    audit_manager: AuditManagerDep = None,
    current_user: AuditCurrentUserDep = None,
    manager: OntologySchemaManager = Depends(get_ontology_schema_manager),
):
    """Return all entity types that have an ontos:modelTier annotation."""
    success = False
    details = {"params": {"tier": tier, "category": category, "persona": persona}}
    try:
        result = manager.get_entity_types(tier=tier, category=category, persona=persona)
        success = True
        details["count"] = len(result)
        return result
    except Exception as e:
        logger.exception("Failed to list entity types")
        details["exception"] = {"type": type(e).__name__, "message": str(e)}
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to list entity types")
    finally:
        audit_manager.log_action(
            db=db, username=current_user.username,
            ip_address=request.client.host if request.client else None,
            feature=FEATURE_ID, action="LIST_ENTITY_TYPES", success=success, details=details,
        )


# ---------- Query-parameter variants (proxy-safe) ----------
# Reverse proxies (e.g. Databricks Apps) can mangle IRIs embedded in
# URL paths by collapsing "//".  These endpoints accept the IRI as a
# query parameter instead, which is never subject to path normalisation.


@router.get(
    "/entity-types/schema",
    response_model=EntityTypeSchema,
    summary="Get field schema for an entity type (query-param variant)",
)
def get_entity_type_schema_q(
    request: Request,
    type_iri: str = Query(..., description="Full IRI of the entity type"),
    db: DBSessionDep = None,
    audit_manager: AuditManagerDep = None,
    current_user: AuditCurrentUserDep = None,
    manager: OntologySchemaManager = Depends(get_ontology_schema_manager),
):
    return _handle_schema(request, type_iri, db, audit_manager, current_user, manager)


@router.get(
    "/entity-types/relationships",
    response_model=EntityRelationships,
    summary="Get relationships for an entity type (query-param variant)",
)
def get_entity_type_relationships_q(
    request: Request,
    type_iri: str = Query(..., description="Full IRI of the entity type"),
    db: DBSessionDep = None,
    audit_manager: AuditManagerDep = None,
    current_user: AuditCurrentUserDep = None,
    manager: OntologySchemaManager = Depends(get_ontology_schema_manager),
):
    return _handle_relationships(request, type_iri, db, audit_manager, current_user, manager)


@router.get(
    "/entity-types/hierarchy-for",
    response_model=List[EntityHierarchyNode],
    summary="Get class hierarchy for an entity type (query-param variant)",
)
def get_entity_type_hierarchy_q(
    request: Request,
    type_iri: str = Query(..., description="Full IRI of the entity type"),
    db: DBSessionDep = None,
    audit_manager: AuditManagerDep = None,
    current_user: AuditCurrentUserDep = None,
    manager: OntologySchemaManager = Depends(get_ontology_schema_manager),
):
    return _handle_hierarchy(request, type_iri, db, audit_manager, current_user, manager)


# ---------- Path-parameter variants (legacy, with IRI normalisation) ----------


@router.get(
    "/entity-types/{type_iri:path}/schema",
    response_model=EntityTypeSchema,
    summary="Get field schema for an entity type",
)
def get_entity_type_schema(
    request: Request,
    type_iri: str,
    db: DBSessionDep = None,
    audit_manager: AuditManagerDep = None,
    current_user: AuditCurrentUserDep = None,
    manager: OntologySchemaManager = Depends(get_ontology_schema_manager),
):
    return _handle_schema(request, type_iri, db, audit_manager, current_user, manager)


@router.get(
    "/entity-types/{type_iri:path}/relationships",
    response_model=EntityRelationships,
    summary="Get relationships for an entity type",
)
def get_entity_type_relationships(
    request: Request,
    type_iri: str,
    db: DBSessionDep = None,
    audit_manager: AuditManagerDep = None,
    current_user: AuditCurrentUserDep = None,
    manager: OntologySchemaManager = Depends(get_ontology_schema_manager),
):
    return _handle_relationships(request, type_iri, db, audit_manager, current_user, manager)


@router.get(
    "/entity-types/{type_iri:path}/hierarchy",
    response_model=List[EntityHierarchyNode],
    summary="Get class hierarchy for an entity type",
)
def get_entity_type_hierarchy(
    request: Request,
    type_iri: str,
    db: DBSessionDep = None,
    audit_manager: AuditManagerDep = None,
    current_user: AuditCurrentUserDep = None,
    manager: OntologySchemaManager = Depends(get_ontology_schema_manager),
):
    return _handle_hierarchy(request, type_iri, db, audit_manager, current_user, manager)


# ---------- Shared handler implementations ----------


def _handle_schema(request, type_iri, db, audit_manager, current_user, manager):
    """Return the field schema (data properties) for a specific entity type."""
    success = False
    details = {"params": {"type_iri": type_iri}}
    try:
        schema = manager.get_entity_type_schema(type_iri)
        if not schema:
            details["exception"] = {"type": "NotFound", "message": f"Entity type not found: {type_iri}"}
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Entity type not found: {type_iri}",
            )
        success = True
        details["field_count"] = len(schema.fields)
        return schema
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get entity type schema for '%s'", type_iri)
        details["exception"] = {"type": type(e).__name__, "message": str(e)}
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to get entity type schema")
    finally:
        audit_manager.log_action(
            db=db, username=current_user.username,
            ip_address=request.client.host if request.client else None,
            feature=FEATURE_ID, action="GET_ENTITY_TYPE_SCHEMA", success=success, details=details,
        )


def _handle_relationships(request, type_iri, db, audit_manager, current_user, manager):
    """Return all outgoing and incoming relationships for an entity type."""
    success = False
    details = {"params": {"type_iri": type_iri}}
    try:
        result = manager.get_relationships(type_iri)
        success = True
        details["outgoing_count"] = len(result.outgoing)
        details["incoming_count"] = len(result.incoming)
        return result
    except Exception as e:
        logger.exception("Failed to get relationships for '%s'", type_iri)
        details["exception"] = {"type": type(e).__name__, "message": str(e)}
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to get relationships")
    finally:
        audit_manager.log_action(
            db=db, username=current_user.username,
            ip_address=request.client.host if request.client else None,
            feature=FEATURE_ID, action="GET_ENTITY_TYPE_RELATIONSHIPS", success=success, details=details,
        )


def _handle_hierarchy(request, type_iri, db, audit_manager, current_user, manager):
    """Return the class hierarchy subtree rooted at the given entity type."""
    success = False
    details = {"params": {"type_iri": type_iri}}
    try:
        result = manager.get_hierarchy(root_iri=type_iri)
        success = True
        return result
    except Exception as e:
        logger.exception("Failed to get hierarchy for '%s'", type_iri)
        details["exception"] = {"type": type(e).__name__, "message": str(e)}
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to get hierarchy")
    finally:
        audit_manager.log_action(
            db=db, username=current_user.username,
            ip_address=request.client.host if request.client else None,
            feature=FEATURE_ID, action="GET_ENTITY_TYPE_HIERARCHY", success=success, details=details,
        )


# ===================== Full Hierarchy =====================


@router.get(
    "/hierarchy",
    response_model=List[EntityHierarchyNode],
    summary="Get full entity class hierarchy",
)
def get_full_hierarchy(
    request: Request,
    db: DBSessionDep = None,
    audit_manager: AuditManagerDep = None,
    current_user: AuditCurrentUserDep = None,
    manager: OntologySchemaManager = Depends(get_ontology_schema_manager),
):
    """Return the complete class hierarchy from ontos:Entity downward."""
    success = False
    details = {}
    try:
        result = manager.get_hierarchy()
        success = True
        return result
    except Exception as e:
        logger.exception("Failed to get full hierarchy")
        details["exception"] = {"type": type(e).__name__, "message": str(e)}
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to get hierarchy")
    finally:
        audit_manager.log_action(
            db=db, username=current_user.username,
            ip_address=request.client.host if request.client else None,
            feature=FEATURE_ID, action="GET_FULL_HIERARCHY", success=success, details=details,
        )


# ===================== Asset Type Sync =====================


@router.post(
    "/sync-asset-types",
    response_model=AssetTypeSyncResult,
    summary="Sync ontology asset types to the database",
    dependencies=[Depends(PermissionChecker(FEATURE_ID, FeatureAccessLevel.READ_WRITE))],
)
def sync_asset_types(
    request: Request,
    db: DBSessionDep,
    audit_manager: AuditManagerDep,
    current_user: AuditCurrentUserDep,
    manager: OntologySchemaManager = Depends(get_ontology_schema_manager),
):
    """Force a sync of ontology-defined asset types to AssetTypeDb.

    Normally runs automatically on startup. This endpoint allows manual re-sync.
    """
    success = False
    details = {}
    try:
        result = manager.sync_asset_types(db)
        success = True
        details["created"] = result.created
        details["updated"] = result.updated
        details["errors"] = result.errors
        return result
    except Exception as e:
        logger.exception("Failed to sync asset types")
        details["exception"] = {"type": type(e).__name__, "message": str(e)}
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to sync asset types")
    finally:
        audit_manager.log_action(
            db=db, username=current_user.username,
            ip_address=request.client.host if request.client else None,
            feature=FEATURE_ID, action="SYNC_ASSET_TYPES", success=success, details=details,
        )


# ===================== Registration =====================


def register_routes(app):
    app.include_router(router)
    logger.info("Ontology schema routes registered with prefix /api/ontology")
