from fastapi import APIRouter,Depends,HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from src.config.database import get_db
from src.middlewares.auth import current_user,writer,admin,publisher,internal_user
from src.schemas.privacy import ChannelInput,TouchInput,ReleaseInput,BudgetInput
from src.controllers import privacy as controller
from src.services import privacy
from src.models.privacy import PrivacyRelease
from src.models.study import Study
router=APIRouter()

# 合作方视角：只看有发布结果的研究及其带噪版本；不暴露原始触达记录与输入哈希。
@router.get('/partner/overview')
def partner_overview(db=Depends(get_db),user=Depends(current_user)):
    if user.role!='partner': raise HTTPException(403,'此入口仅面向合作方')
    studies=[]
    for s in db.scalars(select(Study).order_by(Study.id)):
        releases=privacy.list_releases(db,s.id,user.role)
        if releases: studies.append({'id':s.id,'name':s.name,'releases':releases})
    return {'studies':studies}

@router.get('/studies/{id}/privacy')
def privacy_overview(id:int,db=Depends(get_db),user=Depends(internal_user)):
    return controller.overview(db,id,user)

@router.put('/studies/{id}/privacy/budget')
def set_budget(id:int,data:BudgetInput,db=Depends(get_db),user=Depends(admin)):
    return controller.set_budget(db,id,data,user)

@router.post('/studies/{id}/privacy/channels')
def add_channel(id:int,data:ChannelInput,db=Depends(get_db),user=Depends(writer)):
    return controller.add_channel(db,id,data,user)

@router.delete('/studies/{id}/privacy/channels/{channel_id}')
def delete_channel(id:int,channel_id:int,db=Depends(get_db),user=Depends(writer)):
    return controller.delete_channel(db,id,channel_id,user)

@router.get('/studies/{id}/privacy/touches')
def list_touches(id:int,db=Depends(get_db),user=Depends(writer)):
    return controller.touches(db,id,user)

@router.post('/studies/{id}/privacy/touches')
def save_touch(id:int,data:TouchInput,db=Depends(get_db),user=Depends(writer)):
    return controller.save_touch(db,id,data,user)

@router.delete('/studies/{id}/privacy/touches/{touch_id}')
def delete_touch(id:int,touch_id:int,db=Depends(get_db),user=Depends(writer)):
    return controller.delete_touch(db,id,touch_id,user)

@router.post('/studies/{id}/privacy/releases')
def publish(id:int,data:ReleaseInput,db=Depends(get_db),user=Depends(publisher)):
    return controller.publish(db,id,data,user)

@router.get('/privacy/releases/{release_id}')
def get_release(release_id:int,db=Depends(get_db),user=Depends(current_user)):
    return controller.release(db,release_id,user)

@router.get('/privacy/releases/{release_id}/export')
def export_release(release_id:int,db=Depends(get_db),user=Depends(current_user)):
    rel=db.get(PrivacyRelease,release_id)
    if not rel: raise HTTPException(404,'发布记录不存在')
    name=f'privacy-release-{release_id}-v{rel.version}.csv'
    return Response(content=controller.export(db,release_id,user).encode('utf-8'),media_type='text/csv',
                    headers={'Content-Disposition':f'attachment; filename="{name}"'})
