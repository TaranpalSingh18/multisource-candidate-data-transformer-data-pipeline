from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models.candidate import StoredConfig
from ..projection import ProjectionConfig, validate_config_for_profile


router = APIRouter(prefix="/configs", tags=["configs"])


class ConfigCreateRequest(BaseModel):
    name: str
    config: ProjectionConfig


class ConfigResponse(BaseModel):
    name: str
    config: ProjectionConfig


@router.post("", response_model=ConfigResponse)
def create_or_update_config(request: ConfigCreateRequest, db: Session = Depends(get_db)) -> ConfigResponse:
    try:
        validate_config_for_profile(request.config)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    stored = db.query(StoredConfig).filter(StoredConfig.name == request.name).one_or_none()
    if stored is None:
        stored = StoredConfig(name=request.name, config_json=request.config.model_dump())
        db.add(stored)
    else:
        stored.config_json = request.config.model_dump()

    db.commit()
    db.refresh(stored)
    return ConfigResponse(name=stored.name, config=request.config)


@router.get("", response_model=List[ConfigResponse])
def list_configs(db: Session = Depends(get_db)) -> List[ConfigResponse]:
    rows = db.query(StoredConfig).order_by(StoredConfig.name).all()
    out: List[ConfigResponse] = []
    for row in rows:
        cfg = ProjectionConfig.model_validate(row.config_json)
        out.append(ConfigResponse(name=row.name, config=cfg))
    return out


@router.get("/{name}", response_model=ConfigResponse)
def get_config(name: str, db: Session = Depends(get_db)) -> ConfigResponse:
    stored = db.query(StoredConfig).filter(StoredConfig.name == name).one_or_none()
    if stored is None:
        raise HTTPException(status_code=404, detail="Config not found")
    cfg = ProjectionConfig.model_validate(stored.config_json)
    return ConfigResponse(name=stored.name, config=cfg)

