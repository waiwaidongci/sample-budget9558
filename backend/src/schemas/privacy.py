from pydantic import BaseModel,Field
from typing import Optional

class ChannelInput(BaseModel):
    name:str=Field(min_length=1,max_length=80)

class TouchInput(BaseModel):
    audience_key:str=Field(min_length=1,max_length=120)
    channel:str=Field(min_length=1,max_length=80)
    group:str=Field(min_length=1,max_length=1)
    reached:bool=False
    clicked:bool=False

class ReleaseInput(BaseModel):
    epsilon:float=Field(gt=0,le=10)
    idempotency_key:str=Field(min_length=8,max_length=160)
    corrects_release_id:Optional[int]=Field(default=None,gt=0)

class BudgetInput(BaseModel):
    total_epsilon:float=Field(gt=0,le=100)
