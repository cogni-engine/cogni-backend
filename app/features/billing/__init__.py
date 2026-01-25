"""Billing feature module"""

# Import domain and schemas first (they don't cause circular dependencies)
from app.features.billing.domain import SubscriptionPlanType, SubscriptionStatus
from app.features.billing.schemas import (
    UpgradeToBusinessRequest,
    UpgradeToBusinessResponse,
    UpdateSeatsRequest,
    UpdateSeatsResponse,
    PurchasePlanRequest,
    PurchasePlanResponse,
    CreatePortalSessionRequest,
    CreatePortalSessionResponse,
)

# Import models
from app.features.billing.models import (
    Organization,
    OrganizationCreate,
    OrganizationUpdate,
    StripeEvent,
    StripeEventCreate,
    StripeEventUpdate,
)

# Import service and webhook_service
from app.features.billing.service import BillingService, OrganizationMembership, UserRole
from app.features.billing.webhook_service import BillingWebhookService

# Import repositories
from app.features.billing.repositories import OrganizationRepository, StripeEventRepository

# Import services
from app.features.billing.services import OrganizationService

# Import router (circular dependency resolved by moving models to billing feature)
from app.features.billing.api import router

__all__ = [
    "router",
    "BillingService",
    "BillingWebhookService",
    "OrganizationMembership",
    "UserRole",
    "SubscriptionPlanType",
    "SubscriptionStatus",
    "Organization",
    "OrganizationCreate",
    "OrganizationUpdate",
    "StripeEvent",
    "StripeEventCreate",
    "StripeEventUpdate",
    "OrganizationRepository",
    "StripeEventRepository",
    "OrganizationService",
    "UpgradeToBusinessRequest",
    "UpgradeToBusinessResponse",
    "UpdateSeatsRequest",
    "UpdateSeatsResponse",
    "PurchasePlanRequest",
    "PurchasePlanResponse",
    "CreatePortalSessionRequest",
    "CreatePortalSessionResponse",
]
