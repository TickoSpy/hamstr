from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.video import Playlist, PlaylistItem, Video
from app.schemas.video import (
    PlaylistAddItemRequest,
    PlaylistCreateRequest,
    PlaylistSchema,
    PlaylistSummary,
)

router = APIRouter(prefix="/playlists", tags=["playlists"])


async def _get_playlist(playlist_id: int, db: AsyncSession) -> Playlist:
    result = await db.execute(
        select(Playlist)
        .options(selectinload(Playlist.items).selectinload(PlaylistItem.video))
        .where(Playlist.id == playlist_id)
    )
    pl = result.scalar_one_or_none()
    if not pl:
        raise HTTPException(status_code=404, detail="Playlist not found")
    # An item whose video is gone can no longer be created (FKs cascade now, and
    # the delete paths clear these rows), but one stale row used to fail the
    # whole response and leave the playlist stuck on "Loading…". Drop them here;
    # delete-orphan means the rows go for good on the next commit through this
    # session, and a read-only GET simply never flushes.
    pl.items = [item for item in pl.items if item.video is not None]
    return pl


@router.get("", response_model=list[PlaylistSummary])
async def list_playlists(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(
            Playlist.id,
            Playlist.name,
            Playlist.created_at,
            func.count(Video.id).label("item_count"),
        )
        # Join through to videos so an orphaned row isn't counted in the size
        # shown next to the playlist name.
        .outerjoin(PlaylistItem, PlaylistItem.playlist_id == Playlist.id)
        .outerjoin(Video, Video.id == PlaylistItem.video_id)
        .group_by(Playlist.id)
        .order_by(Playlist.created_at.desc())
    )
    rows = result.all()
    return [
        PlaylistSummary(
            id=r.id, name=r.name, created_at=r.created_at, item_count=r.item_count
        )
        for r in rows
    ]


@router.post("", status_code=201, response_model=PlaylistSummary)
async def create_playlist(
    body: PlaylistCreateRequest, db: AsyncSession = Depends(get_db)
):
    pl = Playlist(name=body.name.strip())
    db.add(pl)
    await db.commit()
    await db.refresh(pl)
    return PlaylistSummary(
        id=pl.id, name=pl.name, created_at=pl.created_at, item_count=0
    )


@router.get("/{playlist_id}", response_model=PlaylistSchema)
async def get_playlist(playlist_id: int, db: AsyncSession = Depends(get_db)):
    return await _get_playlist(playlist_id, db)


@router.delete("/{playlist_id}", status_code=204)
async def delete_playlist(playlist_id: int, db: AsyncSession = Depends(get_db)):
    pl = await _get_playlist(playlist_id, db)
    await db.delete(pl)
    await db.commit()


@router.patch("/{playlist_id}", response_model=PlaylistSummary)
async def rename_playlist(
    playlist_id: int, body: PlaylistCreateRequest, db: AsyncSession = Depends(get_db)
):
    pl = await _get_playlist(playlist_id, db)
    pl.name = body.name.strip()
    await db.commit()
    item_count = len(pl.items)
    return PlaylistSummary(
        id=pl.id, name=pl.name, created_at=pl.created_at, item_count=item_count
    )


@router.post("/{playlist_id}/items", status_code=201, response_model=PlaylistSchema)
async def add_item(
    playlist_id: int, body: PlaylistAddItemRequest, db: AsyncSession = Depends(get_db)
):
    pl = await _get_playlist(playlist_id, db)
    video = await db.get(Video, body.video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    position = len(pl.items)
    item = PlaylistItem(
        playlist_id=playlist_id, video_id=body.video_id, position=position
    )
    db.add(item)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Video already in playlist")
    return await _get_playlist(playlist_id, db)


@router.delete("/{playlist_id}/items/{video_id}", status_code=204)
async def remove_item(
    playlist_id: int, video_id: str, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(PlaylistItem).where(
            PlaylistItem.playlist_id == playlist_id,
            PlaylistItem.video_id == video_id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    await db.delete(item)
    await db.commit()
