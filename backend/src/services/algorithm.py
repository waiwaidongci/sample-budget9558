import math
from decimal import Decimal, ROUND_HALF_UP
import numpy as np
from scipy import stats

def finite_rows(snapshot,keys):
    if not snapshot: raise ValueError('空批次无法分析')
    result=[]
    for row in snapshot:
        values=row['values']
        if any(k not in values for k in keys): raise ValueError('观测字段不完整')
        x=[float(values[k]) for k in keys]
        if not all(math.isfinite(v) for v in x): raise ValueError('观测必须为有限数值')
        result.append(x)
    return np.asarray(result,dtype=float)

def required_n(p0,p1,alpha=.05,power=.8):
    if not 0<p0<1 or not 0<p1<1 or p0==p1: raise ValueError('概率必须位于0与1之间且差异非零')
    if not .001<=alpha<=.2 or not .5<=power<=.99: raise ValueError('alpha或power超出范围')
    pooled=(p0+p1)/2;za=float(stats.norm.ppf(1-alpha/2));zb=float(stats.norm.ppf(power))
    return math.ceil((za*math.sqrt(2*pooled*(1-pooled))+zb*math.sqrt(p0*(1-p0)+p1*(1-p1)))**2/(p1-p0)**2)

def simulate_power(p0,p1,n,alpha,B,seed=42):
    rng=np.random.default_rng(seed);a=rng.binomial(n,p0,B);b=rng.binomial(n,p1,B)
    pooled=(a+b)/(2*n);se=np.sqrt(2*pooled*(1-pooled)/n)
    z=np.divide((b-a)/n,se,out=np.zeros(B,dtype=float),where=se>0)
    rejected=np.abs(z)>stats.norm.ppf(1-alpha/2)
    prob=float(np.mean(rejected));return prob,math.sqrt(prob*(1-prob)/B)

def calculate(snapshot,params):
    data=finite_rows(snapshot,['p0','p1','cost_per_contact','budget'])
    alpha=float(params.get('alpha',.05));power=float(params.get('power',.8));B=int(params.get('simulations',10000))
    if not 200<=B<=20000: raise ValueError('模拟次数超出范围')
    rows=[];first=None
    for r,(p0,p1,cost,budget) in zip(snapshot,data):
        if cost<=0 or budget<=0: raise ValueError('成本与预算必须为正')
        n=required_n(p0,p1,alpha,power)
        if n>200000: raise ValueError('近似样本量超过每组200000，请增大MDE或分拆研究')
        sim,se=simulate_power(p0,p1,n,alpha,B);total=n*2;expense=float((Decimal(str(cost))*total).quantize(Decimal('.01'),rounding=ROUND_HALF_UP));affordable=int(Decimal(str(budget))/(Decimal(str(cost))*2))
        if affordable>200000: raise ValueError('预算允许每组超过200000次触达，请缩小预算或提高成本口径')
        budget_power,budget_se=simulate_power(p0,p1,affordable,alpha,B) if affordable>0 else (0.,0.)
        row=[r['source_key'],float(p0),float(p1),n,total,expense,sim,se,affordable,budget_power,'足够' if Decimal(str(budget))>=Decimal(str(expense)) else '不足']
        rows.append(row)
        if first is None: first=row
    return {'metrics':{'情景数':len(rows),'首情景每组样本量':first[3],'首情景总样本量':first[4],'首情景预计成本(元)':first[5],'首情景模拟功效':first[6],'模拟功效Monte Carlo标准误':first[7],'目标功效':power,'双侧显著性α':alpha,'模拟次数':B,'随机种子':42},'interpretation':f"首情景按双侧等样本正态近似，每组需{first[3]}次独立触达，总{first[4]}次；预计成本{first[5]:.2f}元，现有预算{first[10]}。模拟功效{first[6]:.3f}。",'caveat':'使用预设基线与最小可检测差异进行设计，不保证真实业务效应。模拟采用双侧合并比例z检验；低事件数时正态近似可能失真。不同情景独立核算，不自动合并预算。','columns':['情景','基线p0','候选p1','所需每组n','总样本','预计元','模拟功效','MC标准误','预算允许每组n','预算下功效','预算判断'],'rows':rows,'table_title':'样本、费用与模拟功效逐情景核对'}
