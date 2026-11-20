import {studies,runs,privacy} from '../api/research.js';
export const store={studies:[],runs:[],studyId:0,runId:0,rows:[],privacy:null,touches:[],releaseId:0};
export async function load(){[store.studies,store.runs]=await Promise.all([studies.list(),runs.list()]);if(!store.studyId)store.studyId=store.studies[0]?.id||0;}
export async function loadRows(){store.rows=store.studyId?await studies.rows(store.studyId):[];}
export async function loadPrivacy(){
  if(!store.studyId)return;
  store.privacy=await privacy.overview(store.studyId);
  const role=localStorage.getItem('research-role');
  store.touches=role==='admin'||role==='analyst'?await privacy.touches(store.studyId):[];
}
