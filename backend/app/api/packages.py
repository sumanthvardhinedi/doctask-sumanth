from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.schemas import PackageCreateRequest, PackageResponse
from app.db.database import get_db
from app.models.filing import FilingPackage
from app.validator.rules import get_rules_for_authority


router = APIRouter(
    prefix="/api/v1/packages",
    tags=["packages"],
)


@router.post(
    "",
    response_model=PackageResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_package(
    request: PackageCreateRequest,
    db: Session = Depends(get_db),
) -> PackageResponse:
    try:
        get_rules_for_authority(request.authority_code)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    package = FilingPackage(
        authority_code=request.authority_code,
        name=request.name,
    )

    db.add(package)
    db.commit()
    db.refresh(package)

    return PackageResponse(
        id=package.id,
        authority_code=package.authority_code,
        name=package.name,
        status=package.status,
        document_count=0,
    )