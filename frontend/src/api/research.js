import {request,post} from './client.js';
export const studies={list:()=>request('/studies'),create:x=>post('/studies',x),rows:id=>request(`/studies/${id}/observations`),save:(id,x,row)=>row?request(`/studies/${id}/observations/${row}`,{method:'PUT',body:JSON.stringify(x)}):post(`/studies/${id}/observations`,x),remove:(id,row)=>request(`/studies/${id}/observations/${row}`,{method:'DELETE'})};
export const runs={list:()=>request('/runs'),create:x=>post('/runs',x),get:id=>request(`/runs/${id}`),review:(id,note)=>post(`/runs/${id}/review`,{note}),export:id=>request(`/runs/${id}/export`)};
export const privacy={
 overview:id=>request(`/studies/${id}/privacy`),
 setBudget:(id,total_epsilon)=>request(`/studies/${id}/privacy/budget`,{method:'PUT',body:JSON.stringify({total_epsilon})}),
 addChannel:(id,name)=>post(`/studies/${id}/privacy/channels`,{name}),
 removeChannel:(id,cid)=>request(`/studies/${id}/privacy/channels/${cid}`,{method:'DELETE'}),
 touches:id=>request(`/studies/${id}/privacy/touches`),
 saveTouch:(id,x)=>post(`/studies/${id}/privacy/touches`,x),
 removeTouch:(id,tid)=>request(`/studies/${id}/privacy/touches/${tid}`,{method:'DELETE'}),
 publish:(id,x)=>post(`/studies/${id}/privacy/releases`,x),
 release:id=>request(`/privacy/releases/${id}`),
 export:id=>request(`/privacy/releases/${id}/export`),
 partner:()=>request('/partner/overview'),
};
