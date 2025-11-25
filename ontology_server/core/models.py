#!/usr/bin/env python3
"""
Pydantic models for API request/response validation
"""

from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any


class IndividualData(BaseModel):
    """Model for individual data."""
    id: str = Field(..., description="Unique identifier for the individual")
    class_name: str = Field(..., alias="class", description="OWL class name")
    data_properties: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Data property values")
    object_properties: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Object property values (target individual IDs)")

    class Config:
        populate_by_name = True


class IndividualUpdate(BaseModel):
    """Model for updating individual data."""
    data_properties: Optional[Dict[str, Any]] = Field(default=None, description="Data property values to update")
    object_properties: Optional[Dict[str, Any]] = Field(default=None, description="Object property values to update")


class StatusResponse(BaseModel):
    """Model for status response."""
    status: str
    ontology: Optional[str] = None
    individuals_count: Optional[int] = None
    classes_count: Optional[int] = None
    individuals: Optional[List[str]] = None
    message: Optional[str] = None


class OperationResponse(BaseModel):
    """Model for operation response."""
    status: str
    id: Optional[str] = None
    message: Optional[str] = None
    individuals: Optional[int] = None
    relationships: Optional[int] = None
    added: Optional[int] = None
    failed: Optional[int] = None


class BatchIndividualsData(BaseModel):
    """Model for batch individual data."""
    individuals: List[IndividualData] = Field(..., description="List of individuals to add")
