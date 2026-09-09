/* Pure presentation calculations, shared by the browser and node:test. */
(function(root,factory){const value=factory();if(typeof module==="object"&&module.exports)module.exports=value;else root.MaintenanceData=value})(typeof globalThis!=="undefined"?globalThis:this,()=>{
const numeric=v=>typeof v==="number"&&Number.isFinite(v);
const arr=v=>Array.isArray(v)?v:[];
const obj=v=>v&&typeof v==="object"&&!Array.isArray(v)?v:{};
const known=v=>v!==null&&v!==undefined&&v!==""&&v!=="unknown";
function duration(v){return !numeric(v)||v<0?"—":v<1000?Number(v.toFixed(2))+" ms":Number((v/1000).toFixed(2))+" s"}
function date(v,full=false){if(!v||Number.isNaN(Date.parse(v)))return "未记录";return new Intl.DateTimeFormat("zh-CN",{timeZone:"Asia/Shanghai",year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",...(full?{second:"2-digit"}:{}),hour12:false}).format(new Date(v))}
function mode(r){if(r.mode==="live")return "真实模型";if(r.mode==="offline"||r.model==="offline-rule-interpreter")return "规则演练";if(r.mode==="deterministic"||r.type)return "确定性操作";return "未记录"}
function status(r){if(r.status==="failed")return "失败";if(r.status==="partial")return "部分完成";if(r.type==="purchase_jump"||r.status==="已跳转")return "已跳转";if(r.status==="success")return r.type==="checkout"?"入口已创建":"执行完成";return known(r.status)?r.status:"未记录"}
function operation(r){if(r.type==="purchase_jump")return "打开购买链接";if(r.type==="checkout")return arr(r.entries).some(x=>x.kind==="local_demo")?"本地结算演练":"结算准备";return r.input||"未记录操作摘要"}
function runStats(rows){const d=rows.map(r=>r.latency_ms).filter(v=>numeric(v)&&v>=0).sort((a,b)=>a-b);return {count:rows.length,failed:rows.filter(r=>r.status==="failed").length,median:d.length?(d[Math.floor((d.length-1)/2)]+d[Math.ceil((d.length-1)/2)])/2:null,timed:d.length}}
function filterRuns(rows,f={}){return arr(rows).filter(r=>(!f.task||r.task_id===f.task)&&(!f.status||status(r)===f.status)&&(!f.mode||mode(r)===f.mode))}
function callInfo(r){
 if(r.model_calls===0)return {calls:"0 次",tokens:"未调用模型",cost:"未调用模型"};
 const reports=arr(r.usage_reports);
 const tokens=reports.length&&reports.every(x=>numeric(x?.total_tokens))?reports.reduce((n,x)=>n+x.total_tokens,0):null;
 return {calls:numeric(r.model_calls)?r.model_calls+" 次":"未记录",tokens:tokens===null?"未记录":tokens+" tokens",
 cost:numeric(r.estimated_cost_cny)?"¥ "+r.estimated_cost_cny.toFixed(6)+"（估算）":numeric(r.estimated_cost_usd)?"US$ "+r.estimated_cost_usd.toFixed(6)+"（估算）":"未记录"};
}
function outcome(r){if(!r||r.skipped===true||["skipped","not_run","未运行"].includes(r.status))return "未运行";return r.passed===true?"通过":r.passed===false?"失败":"未运行"}
function signature(r){return JSON.stringify([r?.mode||null,r?.model||null,r?.catalog_version||null,r?.catalog_sha256||null,r?.test_set_sha256||null,[...new Set(arr(r?.traces).map(t=>t.mode||null))].sort(),[...new Set(arr(r?.traces).map(t=>t.model||null))].sort(),[...new Set(arr(r?.traces).map(t=>t.catalog_version||null))].sort()])}
function compare(report={},cases=[],left="v1",right="v2",split="all"){
 const source=obj(report.rows),a=arr(source[left]),b=arr(source[right]),dataset=new Map(arr(cases).map(c=>[c.id,c]));
 const ids=[...new Set([...a,...b,...arr(cases)].map(r=>r.id).filter(known))].sort();
 const index=rows=>{const m=new Map;for(const r of rows){if(m.has(r.id))m.set(r.id,null);else m.set(r.id,r)}return m};
 const am=index(a),bm=index(b);
 const identity=known(report.test_set)&&known(report.test_set_sha256)&&known(report.catalog_sha256);
 const rows=ids.map(id=>{
  const l=am.get(id),r=bm.get(id),c=dataset.get(id);
  const group=l?.split||r?.split||c?.split||"unknown";
  const ls=outcome(l),rs=outcome(r);
  const comparable=identity&&left!==right&&!!l&&!!r&&known(l.mode)&&known(r.mode)&&known(l.split)&&known(r.split)&&l.split===r.split&&signature(l)===signature(r)&&ls!=="未运行"&&rs!=="未运行";
  const change=!comparable?"不可比较":ls==="失败"&&rs==="通过"?"改善":ls==="通过"&&rs==="失败"?"退步":"未变化";
  return {id,left:l,right:r,case:c,split:group,leftStatus:ls,rightStatus:rs,change,
    reason:!identity?"报告缺少数据集身份":left===right?"请选择不同版本":!l||!r?"案例缺失或 ID 重复":!known(l.mode)||!known(r.mode)?"运行模式未记录":!known(l.split)||!known(r.split)?"数据分组未记录":l.split!==r.split?"数据分组不同":signature(l)!==signature(r)?"执行模式、模型或资料条件不同":ls==="未运行"||rs==="未运行"?"存在未运行结果":""};
 }).filter(r=>split==="all"||r.split===split);
 const tally=key=>({total:rows.length,passed:rows.filter(r=>r[key]==="通过").length,failed:rows.filter(r=>r[key]==="失败").length,notRun:rows.filter(r=>r[key]==="未运行").length});
 const first=tally("leftStatus"),second=tally("rightStatus"),changes={改善:0,退步:0,未变化:0,不可比较:0};
 rows.forEach(r=>changes[r.change]++);
 const comparable=rows.length>0&&changes["不可比较"]===0;
 return {rows,left:first,right:second,changes,comparable,delta:comparable?second.passed-first.passed:null,
 points:comparable?(second.passed/second.total-first.passed/first.total)*100:null};
}
function filterCases(rows,value){return rows.filter(r=>!value||value==="全部"||value==="待处理"?(value!=="待处理"||r.change==="退步"||r.rightStatus==="失败"||r.change==="不可比较"):value==="仍失败"?r.leftStatus==="失败"&&r.rightStatus==="失败":r.change===value)}
function evidence(r){const found=new Map;
 function add(s){if(s?.product&&s?.offer)found.set(s.offer.id||s.product.id,s)}
 arr(r.result?.items).forEach(i=>add(i.snapshot));
 for(const ev of arr(r.events)){add(ev.result);arr(ev.result).forEach(add);arr(ev.result?.items).forEach(i=>add(i.snapshot))}
 return [...found.values()];
}
return {numeric,arr,obj,known,duration,date,mode,status,operation,runStats,filterRuns,callInfo,outcome,compare,filterCases,evidence};
});
