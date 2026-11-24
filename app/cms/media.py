"""Small initial media library persisted in the database, never ephemeral server disk."""
import re
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy import delete, func, select
from app.core.config import settings
from app.db.database import get_db
from .api import staff
from . import service
from .models import MediaAsset, PublishedMedia, Workspace

router = APIRouter(tags=['Content media'])
MEDIA_MODULES = {'film', 'story_video', 'worksheet', 'initiatives'}
MAX_VIDEO = 64 * 1024 * 1024
MAX_IMAGE = 8 * 1024 * 1024


def identify(data):
    if data.startswith(b'\x89PNG\r\n\x1a\n'): return 'image', 'image/png'
    if data.startswith(b'\xff\xd8\xff'): return 'image', 'image/jpeg'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP': return 'image', 'image/webp'
    if len(data) >= 12 and data[4:8] == b'ftyp' and data[8:12] in (b'isom', b'iso2', b'mp41', b'mp42', b'avc1', b'M4V '): return 'video', 'video/mp4'
    if data.startswith(b'\x1a\x45\xdf\xa3') and b'webm' in data[:4096]: return 'video', 'video/webm'
    raise HTTPException(415, 'الملفات المدعومة: PNG، JPEG، WebP، MP4، WebM')


def validate_media(db, workspace_id, module, payload, publishing=False):
    refs = payload.get('media', [])
    if refs and module not in MEDIA_MODULES: raise HTTPException(422, 'الوسائط غير متاحة لهذا القسم')
    ids = [ref['asset_id'] for ref in refs]
    if len(ids) != len(set(ids)): raise HTTPException(422, 'لا تكرر نفس الملف داخل المادة')
    for ref in refs:
        asset = db.get(MediaAsset, ref['asset_id'])
        if not asset or (asset.workspace_id, asset.module, asset.kind) != (workspace_id, module, ref['kind']):
            raise HTTPException(422, 'الملف غير موجود أو لا ينتمي إلى لوحة وقسم المادة')
        if publishing and asset.kind == 'image' and not ref['alt'].strip():
            raise HTTPException(422, 'أضف وصفًا بديلًا لكل صورة قبل النشر')


@router.post('/api/cms/media', status_code=201)
async def upload(request: Request, workspace_id: int, module: str, filename: str = Query(max_length=180), user=Depends(staff), db=Depends(get_db)):
    service.workspace_access(db, user, workspace_id, module)
    if module not in MEDIA_MODULES: raise HTTPException(422, 'القسم لا يدعم رفع الوسائط')
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > MAX_VIDEO: raise HTTPException(413, 'الحد الأقصى للفيديو 64 ميغابايت والصورة 8 ميغابايت')
        content.extend(chunk)
    kind, mime = identify(content)
    if module in ('worksheet',) and kind != 'image': raise HTTPException(422, 'أوراق العمل تدعم الصور فقط')
    if module == 'film' and kind != 'video': raise HTTPException(422, 'اختر ملف فيديو لقسم الأفلام')
    if kind == 'image' and len(content) > MAX_IMAGE: raise HTTPException(413, 'الحد الأقصى للصورة 8 ميغابايت')
    # Serialize quota checks per workspace; uploaded files remain private until publication.
    db.scalar(select(Workspace).where(Workspace.id == workspace_id).with_for_update())
    used = db.scalar(select(func.coalesce(func.sum(MediaAsset.size), 0)).where(MediaAsset.workspace_id == workspace_id))
    if used + len(content) > settings.CMS_MEDIA_WORKSPACE_MB * 1024 * 1024:
        raise HTTPException(413, 'مساحة ملفات هذه اللوحة ممتلئة. تواصل مع الأدمن.')
    asset = MediaAsset(id=str(uuid4()), workspace_id=workspace_id, module=module, author_id=user.id,
                       filename=filename.replace('\\', '/').split('/')[-1], kind=kind, mime=mime, size=len(content), data=bytes(content))
    db.add(asset)
    service.audit(db, user, 'media.upload', asset.id)
    db.commit()
    return {'asset_id': asset.id, 'kind': kind, 'filename': asset.filename, 'size': asset.size, 'alt': '', 'caption': ''}


def media_response(asset, request):
    size = asset.size
    start, end, status = 0, size - 1, 200
    headers = {'Accept-Ranges': 'bytes', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Content-Security-Policy': "default-src 'none'"}
    range_value = request.headers.get('range')
    if range_value:
        match = re.fullmatch(r'bytes=(\d*)-(\d*)', range_value)
        if not match or not any(match.groups()): return Response(status_code=416, headers={**headers, 'Content-Range': f'bytes */{size}'})
        left, right = match.groups()
        if left: start, end = int(left), min(int(right), size - 1) if right else size - 1
        else: start = max(0, size - int(right))
        if start > end or start >= size or (not left and int(right) == 0): return Response(status_code=416, headers={**headers, 'Content-Range': f'bytes */{size}'})
        status = 206
        headers['Content-Range'] = f'bytes {start}-{end}/{size}'
    headers['Content-Length'] = str(end - start + 1)
    return Response(content=asset.data[start:end + 1], status_code=status, media_type=asset.mime, headers=headers)


@router.get('/api/cms/media/{asset_id}')
def private_media(asset_id: str, request: Request, user=Depends(staff), db=Depends(get_db)):
    asset = db.get(MediaAsset, asset_id)
    if not asset: raise HTTPException(404, 'الملف غير موجود')
    service.workspace_access(db, user, asset.workspace_id, asset.module)
    return media_response(asset, request)


@router.get('/api/media/{asset_id}')
def public_media(asset_id: str, request: Request, db=Depends(get_db)):
    if not db.scalar(select(PublishedMedia.asset_id).where(PublishedMedia.asset_id == asset_id).limit(1)):
        raise HTTPException(404, 'الملف غير منشور')
    asset = db.get(MediaAsset, asset_id)
    if not asset: raise HTTPException(404, 'الملف غير موجود')
    return media_response(asset, request)


def publish_media(db, row):
    db.execute(delete(PublishedMedia).where(PublishedMedia.content_id == row.id))
    for ref in row.payload.get('media', []): db.add(PublishedMedia(content_id=row.id, asset_id=ref['asset_id']))
