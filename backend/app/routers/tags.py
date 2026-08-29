from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.video import Tag
from app.services.ingest.tagmap import AUTO_TAG_NAMES

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("")
async def list_all_tags(
    custom: bool = Query(
        False,
        description=(
            "Drop the automatic category/format tags and return only names the "
            "user typed. The auto ones duplicate the library's kind filter."
        ),
    ),
    db: AsyncSession = Depends(get_db),
) -> list[str]:
    result = await db.execute(select(distinct(Tag.name)).order_by(Tag.name))
    names = [row[0] for row in result.all()]
    if custom:
        names = [n for n in names if n not in AUTO_TAG_NAMES]
    return names
