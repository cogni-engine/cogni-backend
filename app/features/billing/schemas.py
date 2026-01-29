"""Request and response schemas for Billing feature"""

from pydantic import BaseModel, Field, ConfigDict


class UpgradeToBusinessRequest(BaseModel):
    """Request model for Business plan upgrade"""
    model_config = ConfigDict(populate_by_name=True)
    
    organization_id: int = Field(..., alias="organizationId")
    seat_count: int = Field(..., alias="seatCount", ge=1)  # Required: user must specify seat count


class UpgradeToBusinessResponse(BaseModel):
    """Response model for Business plan upgrade"""
    success: bool
    message: str
    new_plan: str
    seat_count: int


class UpdateSeatsRequest(BaseModel):
    """Request model for manual seat update"""
    model_config = ConfigDict(populate_by_name=True)
    
    organization_id: int = Field(..., alias="organizationId")
    seat_count: int = Field(..., alias="seatCount", ge=1)


class UpdateSeatsResponse(BaseModel):
    """Response model for manual seat update"""
    success: bool
    message: str
    old_seat_count: int
    new_seat_count: int


class PurchasePlanRequest(BaseModel):
    """Request model for universal plan purchase (Pro or Business)"""
    model_config = ConfigDict(populate_by_name=True)
    
    plan_id: str = Field(..., alias="planId")  # "pro" or "business"
    organization_id: int = Field(..., alias="organizationId")  # Required: user's organization
    seat_count: int | None = Field(None, alias="seatCount", ge=1)  # Optional: for business plan


class PurchasePlanResponse(BaseModel):
    """Response model for plan purchase"""
    client_secret: str
    session_id: str
    organization_id: int


class CreatePortalSessionRequest(BaseModel):
    """Request model for Stripe Customer Portal session"""
    model_config = ConfigDict(populate_by_name=True)
    
    organization_id: int = Field(..., alias="organizationId")
    return_url: str | None = Field(None, alias="returnUrl")


class CreatePortalSessionResponse(BaseModel):
    """Response model for portal session"""
    url: str
