/* Maintenance views. Raw artifacts are downloaded through explicit server routes. */
window.MaintenanceUI=(()=>{
const D=MaintenanceData;
let runs=[],bundle={},rf={task:"",status:"",mode:""},rp=1,split="holdout",cf="待处理",cp=1,lv="",rv="";
const labels={budget:"预算约束",no_confirmation:"未发起购买确认",count:"商品数量",categories:"商品品类",exclusions:"排除物品",quantity:"数量一致",clarify:"必要澄清",unknown:"未知费用披露",compatibility:"兼容性限制",expected_error:"预期故障",
min:"最少条目",max:"最多条目",forbid_categories:"排除品类",owned:"已有物品",required_offer:"必须保留报价",optional:"可选报价",scenario:"执行场景",test:"关联测试",fault:"注入故障",error:"失败环节",scope:"资料范围",
revision:"修订",budget_minor:"预算（分）",recipient:"购买对象",excluded:"排除物品",constraints:"其他约束",category:"品类",query:"关键词",offer_id:"报价",required:"必要项",reason:"选择理由"};
const names={get_task:"读取任务",get_preferences:"读取偏好",update_item:"修改已有条目",update_constraints:"更新约束",search_products:"搜索商品",read_evidence:"读取依据",set_plan:"更新方案",check_plan:"计算预算与检查兼容性"};
const group=s=>s==="development"?"开发集":s==="holdout"?"保留验证集":"未记录分组";
const safeUrl=s=>{try{const u=new URL(s);return u.protocol==="https:"&&!u.username&&!u.password?esc(u.href):""}catch{return ""}};
const text=v=>v===null||v===undefined?"未记录":typeof v==="boolean"?(v?"是":"否"):Array.isArray(v)?(v.length?v.map(text).join("、"):"无"):typeof v==="object"?Object.entries(v).map(([k,x])=>(labels[k]||k)+"："+text(x)).join("；"):String(v);
const tag=(s)=>'<span class="state '+(["失败","退步","仍失败","回归退步"].includes(s)?"bad":["通过","改善","执行完成","入口已创建","已修复"].includes(s)?"good":s==="已跳转"?"pink":"neutral")+'">'+esc(s)+'</span>';
const kv=(rows)=>'<dl class="kv">'+rows.map(([k,v])=>'<div><dt>'+esc(k)+'</dt><dd>'+esc(text(v))+'</dd></div>').join("")+'</dl>';
const long=v=>{const t=text(v);return t.length>240?'<p class="long-text">'+esc(t.slice(0,240))+'…</p><details class="read-more"><summary>展开全文</summary><p class="long-text">'+esc(t)+'</p></details>':'<p class="long-text">'+esc(t)+'</p>'};
function links(items){return '<footer class="artifact-links">'+items.map(([name,key])=>'<a href="/files/'+key+'">'+esc(name)+' ↧</a>').join("")+'</footer>'}
function page(title,content,top=""){return '<div class="maintenance-page"><div class="maint-title"><h1>'+esc(title)+'</h1>'+top+'</div>'+content+'</div>'}
function fmtmoney(v,currency="CNY"){return D.numeric(v)?new Intl.NumberFormat("zh-CN",{style:"currency",currency}).format(v/100):"未记录"}
function runOptions(key,display){return [...new Set(runs.map(r=>display?display(r):r[key]).filter(Boolean))].map(v=>'<option value="'+esc(v)+'">'+esc(v)+'</option>').join("")}
function select(id,label,options,value){return '<label class="filter-label">'+esc(label)+'<select id="'+id+'">'+options.map(([v,t])=>'<option value="'+esc(v)+'" '+(v===value?"selected":"")+'>'+esc(t)+'</option>').join("")+'</select></label>'}
function pager(current,count,prefix){const total=Math.max(1,Math.ceil(count/10));return '<div class="pagination"><small>'+count+' 条 · 第 '+current+' / '+total+' 页</small><div><button data-maint="'+prefix+'-page" data-page="'+(current-1)+'" '+(current<=1?"disabled":"")+'>上一页</button><button data-maint="'+prefix+'-page" data-page="'+(current+1)+'" '+(current>=total?"disabled":"")+'>下一页</button></div></div>'}
function renderRuns(){
 const rows=D.filterRuns(runs,rf),stats=D.runStats(rows),tasks=new Map(boot.tasks.map(t=>[t.id,t.title]));
 for(const r of runs)if(r.task_id&&!tasks.has(r.task_id))tasks.set(r.task_id,"任务 "+r.task_id.slice(0,8));
 rp=Math.min(rp,Math.max(1,Math.ceil(rows.length/10)));
 const dates=rows.map(r=>r.created).filter(v=>v&&!isNaN(Date.parse(v))).sort();
 const time=dates.length?D.date(dates[0])+" — "+D.date(dates.at(-1)):"无记录";
 const filters='<div class="filters"><span class="scope-label">范围：当前会话 · 最近最多 100 条记录</span>'+
 select("run-task","任务",[["","全部任务"],...tasks],rf.task)+select("run-status","状态",[["","全部状态"],...new Set(runs.map(D.status))].map(x=>typeof x==="string"?[x,x]:x),rf.status)+
 select("run-mode","模式",[["","全部模式"],...new Set(runs.map(D.mode))].map(x=>typeof x==="string"?[x,x]:x),rf.mode)+'</div>';
 const summary='<div class="metrics compact"><article><span>记录数</span><strong>'+stats.count+'</strong><small>按运行 / 操作计数</small></article><article><span>失败记录</span><strong>'+stats.failed+'</strong><small>随筛选更新</small></article><article><span>耗时中位数</span><strong>'+D.duration(stats.median)+'</strong><small>'+stats.timed+' 条有计时</small></article></div><p class="range-note">Asia/Shanghai · '+esc(time)+'</p>';
 const table='<div class="table-wrap"><table class="records"><thead><tr><th>时间</th><th>任务 / 操作</th><th>模式</th><th>状态</th><th>耗时</th><th>策略</th><th></th></tr></thead><tbody>'+rows.slice((rp-1)*10,rp*10).map(r=>'<tr><td data-label="时间" title="'+esc(r.created||"未记录")+'">'+D.date(r.created)+'</td><td data-label="任务 / 操作" class="summary-cell"><strong>'+esc(D.operation(r))+'</strong><small>'+esc(tasks.get(r.task_id)||"关联任务未记录")+'</small></td><td data-label="模式">'+D.mode(r)+'</td><td data-label="状态">'+tag(D.status(r))+'</td><td data-label="耗时" title="'+(D.numeric(r.latency_ms)?"实际记录":"未记录")+'">'+D.duration(r.latency_ms)+'</td><td data-label="策略">'+esc(r.strategy?.version||"—")+'</td><td><a href="/runs/'+esc(r.id)+'" data-nav="/runs/'+esc(r.id)+'" aria-label="查看 '+esc(D.operation(r))+' 详情">查看详情 →</a></td></tr>').join("")+'</tbody></table></div>';
 $("#main").innerHTML=page("运行记录",filters+summary+'<section class="surface">'+(rows.length?table:'<div class="empty-state"><h2>暂无记录</h2><p>'+(runs.length?"当前筛选没有匹配记录。":"发起采购后，记录会显示在这里。")+'</p></div>')+pager(rp,rows.length,"runs")+'</section>');
}
function stepResult(ev){
 const r=ev.result;if(ev.error)return ev.error;
 if(Array.isArray(r))return "返回 "+r.length+" 个候选";
 if(r?.product)return r.product.name+" · "+(r.variant?.spec||"规格未记录");
 if(r?.items)return "方案 "+r.items.length+" 项"+(r.totals?" · 已知小计 "+fmtmoney(r.totals.known_total_minor,r.totals.currency):"");
 if(r?.totals)return "已知小计 "+fmtmoney(r.totals.known_total_minor,r.totals.currency);
 if(r?.budget_minor!==undefined)return "预算 "+fmtmoney(r.budget_minor)+" · 移除 "+D.arr(r.removed).length+" 项";
 return r===undefined?"结果未记录":text(r);
}
function output(r){
 if(!r)return '<p class="muted">未运行或未记录</p>';
 if(Array.isArray(r.kept))return '<ul class="plain-list">'+r.kept.map(id=>'<li>'+esc(offerName(id))+' <small>'+esc(id)+'</small></li>').join("")+'</ul>'+(r.kept.length?"":'<p>没有保留条目</p>');
 if(r.result){
 const t=r.result;return '<p>'+esc(t.status||"任务状态未记录")+(t.totals?' · 已知小计 '+fmtmoney(t.totals.known_total_minor,t.totals.currency):"")+'</p>'+
 (Array.isArray(t.items)?'<ul class="plain-list">'+t.items.map(i=>'<li>'+esc(i.snapshot?.product?.name||i.offer_id||"名称未记录")+' × '+esc(i.quantity??"未记录")+' <small>'+esc(i.snapshot?.variant?.spec||"")+'</small></li>').join("")+'</ul>':"")+
 (Array.isArray(t.items)&&!t.items.length?'<p class="muted">方案未包含商品；不能据此推断任务已完成。</p>':"")+
 (D.arr(t.messages).filter(m=>m.role==="assistant").length?long(t.messages.filter(m=>m.role==="assistant").at(-1).content):"");
 }
 if(r.error)return long(typeof r.error==="object"?r.error.message:r.error);
 return '<p class="muted">未保存实际输出</p>';
}
function offerName(id){if(!bundle.metadata?.catalog_match)return id;for(const list of Object.values(catalog))for(const s of list)if(s.offer.id===id)return s.product.name;return id}
async function runDetail(id){
 const r=await api("/api/run/"+encodeURIComponent(id)),info=D.callInfo(r),evs=D.arr(r.events),evidence=D.evidence(r);
 const result=r.type==="checkout"?'<p>'+esc(D.status(r))+' · '+esc(D.operation(r))+'</p><ul class="plain-list">'+D.arr(r.entries).map(e=>'<li>'+esc(e.merchant)+' · '+esc({local_demo:"本地结算演练",shopify_test:"测试店铺结算",external:"外部购买入口",reference:"仅资料"}[e.kind]||"类型未记录")+'</li>').join("")+'</ul>':r.type==="purchase_jump"?'<p>已跳转 · '+esc(r.merchant||"商家未记录")+'</p><p>'+esc(r.payment||"支付状态未记录")+'</p>':output(r);
 const content='<div class="detail-meta">'+tag(D.status(r))+'<span>'+D.mode(r)+'</span><span>'+D.date(r.created,true)+' · Asia/Shanghai</span><span>'+D.duration(r.latency_ms)+'</span></div>'+
 '<div class="detail-grid"><section class="surface detail-section"><h2>请求与结果</h2><h3>输入 / 操作</h3>'+long(D.operation(r))+'<h3>结果摘要</h3>'+result+'</section>'+
 '<section class="surface detail-section"><h2>运行配置</h2>'+kv([["模型",r.model==="offline-rule-interpreter"?"规则解释器":r.model||"未记录"],["策略",r.strategy?.version||"未记录"],["Prompt",r.prompt_version||"未记录"],["商品数据",r.catalog_version||"未记录"],["commit",D.known(r.commit)?r.commit:"未记录"],["开始时间",r.started_at||"未记录"],["结束时间",r.ended_at||"未记录"],["供应商",r.provider||"未记录"],["实际保存修订",Object.hasOwn(r,"committed_revision")?(r.committed_revision??"未提交"):"未记录"],["Prompt SHA",r.prompt_sha256||"未记录"],["数据 SHA",r.catalog_sha256||"未记录"],["关联任务",r.task_id||"未记录"]])+'</section></div>'+
 '<section class="surface detail-section"><h2>执行步骤 <small>'+evs.length+' 个已记录步骤</small></h2>'+(evs.length?'<ol class="timeline">'+evs.map((e,i)=>'<li class="'+(e.error?"failed-step":"")+'"><span class="step-number">'+(i+1)+'</span><div><div class="step-head"><h3>'+esc(names[e.tool]||"未识别步骤")+'</h3>'+tag(e.error?"失败":e.result!==undefined?"执行完成":"未记录")+'<small>'+D.duration(e.ms)+'</small></div><p>'+esc(stepResult(e))+'</p><details><summary>输入参数</summary>'+long(e.input)+'</details></div></li>').join("")+'</ol>':'<p class="muted">没有步骤数据</p>')+'</section>'+
 (r.status==="failed"||r.error?'<section class="surface detail-section exception"><h2>异常</h2>'+kv([["失败环节",r.category||evs.find(e=>e.error)?.category||"未记录"],["错误",typeof r.error==="object"?r.error.message:r.error||"未记录"],["重试",r.retries??"未记录"],["降级",Object.hasOwn(r,"fallback")?(r.fallback??"无"):"未记录"]])+'</section>':"")+
 '<section class="surface detail-section"><h2>商品依据</h2>'+(evidence.length?'<div class="evidence-grid">'+evidence.map(s=>'<article><h3>'+esc(s.product.name)+'</h3><p>'+esc(s.variant?.spec||"规格未记录")+'</p><p>'+esc(Object.values(D.obj(s.product.attributes)).join(" · "))+'</p><small>采集：'+D.date(s.offer.captured_at,true)+'</small>'+D.arr(s.product.evidence).map(e=>'<p>'+esc(e.excerpt||"摘录未记录")+' '+(safeUrl(e.url)?'<a href="'+safeUrl(e.url)+'" target="_blank" rel="noopener">来源 ↗</a>':'<span class="muted">无来源链接</span>')+'</p>').join("")+'</article>').join("")+'</div>':'<p class="muted">未记录商品依据</p>')+'</section>'+
 '<section class="surface detail-section"><h2>调用与费用</h2>'+kv([["模型调用",info.calls],["Token",info.tokens],["估算费用",info.cost],["工具调用",r.tool_calls??"未记录"],["费率来源",r.cost_source||"未记录"],["费率日期",r.cost_date||"未记录"]])+'</section>'+
 '<footer class="artifact-links"><a href="/downloads/run/'+esc(id)+'">下载原始记录 ↧</a><a href="/files/agent">查看关联实现 ↧</a></footer>';
 $("#main").innerHTML=page("运行详情",content,'<a href="/runs" data-nav="/runs">← 返回运行记录</a>');
}
function bar(label,c,scale){const w=600,p=scale?c.passed/scale*w:0,f=scale?c.failed/scale*w:0,u=scale?c.notRun/scale*w:0;return '<div class="bar-row"><strong>'+esc(label)+'</strong><svg preserveAspectRatio="none" viewBox="0 0 600 24" role="img" aria-label="'+esc(label)+'：通过 '+c.passed+'，失败 '+c.failed+'，未运行 '+c.notRun+'"><rect width="600" height="24" rx="4" class="bar-bg"/><rect width="'+p+'" height="24" class="bar-pass"/><rect x="'+p+'" width="'+f+'" height="24" class="bar-fail"/><rect x="'+(p+f)+'" width="'+u+'" height="24" class="bar-unrun"/></svg><span>'+c.passed+' / '+c.total+'</span></div>'}
let badFilter="优先";
const badRows=()=>D.arr(bundle.badcases?.cases);
const badOrder=r=>r.status==="回归退步"?0:r.status==="仍失败"?1:r.status==="待处理"?2:3;
function badcasePanel(){
 const all=badRows();if(!all.length)return "";
 const rows=all.filter(r=>badFilter==="全部"||(badFilter==="优先"?["仍失败","回归退步"].includes(r.status):r.status===badFilter)).sort((a,b)=>badOrder(a)-badOrder(b));
 return '<section class="surface detail-section"><div class="section-head"><h2>Bad case 概览</h2>'+select("badcase-filter","复盘筛选",[["优先","优先：仍失败 / 回归退步"],["全部","全部"],["待处理","待处理"],["已修复","已修复"],["仍失败","仍失败"],["回归退步","回归退步"]],badFilter)+'</div><div class="change-counts">'+["待处理","已修复","仍失败","回归退步"].map(s=>'<span>'+tag(s)+' <b>'+all.filter(r=>r.status===s).length+'</b></span>').join("")+'</div><p class="range-note">'+esc(bundle.badcases.status_note)+'</p><div class="table-wrap"><table class="records badcase-table"><thead><tr><th>ID / 现象</th><th>失败层级</th><th>根因与置信度</th><th>版本变化</th><th>状态</th><th></th></tr></thead><tbody>'+rows.map(r=>'<tr><td data-label="ID / 现象" class="summary-cell">'+esc(r.id)+'<strong>'+esc(r.phenomenon)+'</strong></td><td data-label="失败层级">'+esc(r.layer)+'</td><td data-label="根因" class="summary-cell">'+esc(r.root_cause)+'<small>'+esc(r.confidence)+'</small></td><td data-label="版本变化" class="summary-cell">'+esc(r.versions)+'</td><td data-label="状态">'+tag(r.status)+'</td><td><a data-nav="/evaluation/badcase/'+esc(r.id)+'" href="/evaluation/badcase/'+esc(r.id)+'">查看复盘 →</a></td></tr>').join("")+'</tbody></table></div><p class="range-note"><a href="/files/badcase-notes">复盘文档 ↧</a> · <a href="/files/badcases">原始结构化记录 ↧</a> · 本轮新模型请求 0；代码验证不等于模型修复。</p></section>';
}
function badcaseDetail(id){
 const c=badRows().find(r=>r.id===id);
 if(!c){$("#main").innerHTML=page("复盘不存在","<p>当前复盘数据没有此 ID。</p>");return}
 const fields=[["用户输入与必要上下文","input"],["预期行为","expected"],["实际行为","actual"],["用户影响","impact"],["失败链路","layer"],["根因","root_cause"],["置信度","confidence"],["根因 / 诱因 / 现象","cause_vs_trigger"],["修复方案","fix"],["修改层级","fix_layer"],["为什么选这一层","why"],["复测结果","verification"],["相关回归","regression"],["遗留风险","risk"]];
 $("#main").innerHTML=page(c.id+" · "+c.phenomenon,'<div class="detail-meta">'+tag(c.status)+'<span>'+esc(c.versions)+'</span></div><section class="surface detail-section"><h2>直接证据</h2><ul class="plain-list">'+c.evidence.map(x=>'<li>'+esc(x)+'</li>').join("")+'</ul>'+c.refs.map(r=>'<p class="range-note">'+esc(r.started_at||"时间未记录")+' · '+esc(r.mode)+' · '+esc(r.prompt_version)+'<br>运行 '+esc(r.run_id)+' · <a href="/files/'+encodeURIComponent(r.artifact)+'">原始记录 ↧</a></p>').join("")+'</section>'+fields.map(([label,key])=>'<section class="surface detail-section"><h2>'+esc(label)+'</h2>'+long(c[key])+'</section>').join(""),'<a href="/evaluation" data-nav="/evaluation">← 返回评测与迭代</a>');
}
function liveReports(){
 const rs=D.arr(bundle.live_reports),cases=new Map();
 for(const report of rs)for(const [version,rows] of Object.entries(report.rows||{}))for(const row of rows){if(!cases.has(row.id))cases.set(row.id,[]);cases.get(row.id).push({report,version,row})}
 if(!cases.size)return '<section class="surface detail-section"><h2>真实模型评测</h2><p>未运行</p></section>';
 return '<section class="surface detail-section"><h2>真实模型评测 · 按案例查看</h2><p>同一版本的重复运行逐条保留，不选择最好一次，也不汇总为整体提升。固定夹具、资源条件变化与未运行单独标注。</p>'+[...cases].sort(([a],[b])=>a.localeCompare(b)).map(([id,attempts])=>{
 const name=attempts.find(x=>x.row.name)?.row.name||id;
 const versions=[...new Set(attempts.map(x=>x.version))];
 return '<details class="read-more"><summary>'+esc(id)+' · '+esc(name)+' · '+attempts.length+' 条记录</summary>'+versions.map(v=>'<h3>'+esc(v)+'</h3>'+attempts.filter(x=>x.version===v).map(({row:r,report:b},i)=>{
 const resource=r.resource_limited||(id==="L05"&&b.id==="live-eval-1788879902459415200");
 const calls=D.arr(r.traces).reduce((n,t)=>n+(t.model_calls||0),0);
 return '<details class="read-more"><summary>'+tag(D.outcome(r))+' · 第 '+(i+1)+' 条 · '+group(r.split)+' · '+D.date(b.created,true)+(resource?' · 资源不足 / 不可比较':'')+'</summary><p>模型 '+esc(b.model)+' · '+calls+' 次请求 · '+D.duration(r.latency_ms)+'</p><p>'+esc(resource?'此记录的资源条件不足，不能当同条件模型失败比较。':b.execution||"执行条件未记录")+'</p>'+output(r)+assertions(r)+'<ol class="plain-list">'+D.arr(r.traces).map(t=>'<li>运行 '+esc(t.id)+' · '+D.callInfo(t).calls+' · '+D.callInfo(t).cost+'<ul>'+D.arr(t.events).map(e=>'<li>'+esc(names[e.tool]||e.tool)+' · '+esc(stepResult(e))+'</li>').join("")+'</ul></li>').join("")+'</ol><p class="range-note">批次 '+esc(b.id)+' · <a href="/files/'+esc(b.id)+'">原始 JSON ↧</a><br>数据 SHA '+esc(b.catalog_sha256)+' · Prompt SHA '+esc(b.prompt_sha256)+'</p></details>';
 }).join("")).join("")+'</details>';
 }).join("")+'</section>';
}
function renderEval(){
 const r=bundle.report;if(!r){$("#main").innerHTML=page("评测与迭代",'<section class="surface empty-state"><h2>暂无可用报告</h2><p>报告尚未生成或无法读取。</p></section>');return}
 const versions=Object.keys(D.obj(r.rows));if(!versions.includes(lv))lv=versions[0]||"";if(!versions.includes(rv))rv=versions.at(-1)||"";
 const cmp=D.compare(r,bundle.cases,lv,rv,split),full=D.compare(r,bundle.cases,lv,rv,"all");
 const current=full.right,system=r.system||{},live=r.live_status||"未记录";
 const modeSet=new Set(Object.values(D.obj(r.rows)).flat().map(D.mode));
 const modeText=[...modeSet].join(" / ")||"未记录";
 const meta='<h2>历史离线规则回归</h2><div class="report-meta"><span>报告时间：'+D.date(r.created,true)+'</span><span>Asia/Shanghai</span><span>数据集：'+esc(r.test_set||"未记录")+'</span><span>'+esc(modeText)+'</span></div>'+
 '<p class="range-note">历史报告 · commit '+esc(D.known(r.commit)?r.commit:"未记录")+' · 系统测试独立生成时间未记录；不代表当前代码已通过验证。</p>';
 const metrics='<div class="metrics"><article><span>系统测试 · 报告快照</span><strong>'+esc(system.passed??"—")+' <small>/ '+esc(system.total??"—")+'</small></strong><small>失败 '+(D.numeric(system.total)&&D.numeric(system.passed)?system.total-system.passed:"未记录")+' 项</small></article>'+
 '<article><span>'+(modeSet.has("真实模型")?"模型案例评测":modeSet.has("未记录")?"案例回归":"离线策略回归")+' · '+esc(rv||"未记录版本")+'</span><strong>'+current.passed+' <small>/ '+current.total+'</small></strong><small>全部分组 · ' +esc(modeText)+'</small></article><article><span>历史快照中的模型评测</span><strong class="word-value">'+esc(live)+'</strong><small>'+(boot.integrations.model_configured?"模型已配置 · 结果以报告为准":"未配置模型")+'</small></article></div>';
 const controls='<div class="section-head"><h2>版本对比</h2><span class="state neutral">规则策略调整</span></div><div class="filters">'+select("eval-split","数据分组",[["holdout","保留验证集"],["development","开发集"],["all","全部（混合分组）"]],split)+(versions.length>1?select("eval-left","基线版本",versions.map(x=>[x,x]),lv)+select("eval-right","对比版本",versions.map(x=>[x,x]),rv):'<span>只有一个版本，无法对比</span>')+'</div>';
 const graph=bar(lv,cmp.left,Math.max(cmp.left.total,cmp.right.total))+bar(rv,cmp.right,Math.max(cmp.left.total,cmp.right.total))+
 '<div class="legend"><span class="legend-pass">通过</span><span class="legend-fail">失败</span><span class="legend-unrun">未运行 / 未记录</span></div>'+
 '<p class="comparison-note">'+(cmp.comparable?esc(rv)+' 比 '+esc(lv)+(cmp.delta>=0?' 增加 ':' 减少 ')+Math.abs(cmp.delta)+' 个通过案例 · '+(cmp.points>=0?"提高 ":"降低 ")+Math.abs(cmp.points).toFixed(2)+' 个百分点':'不可计算总体差异：存在未运行、缺失案例或不同执行条件。')+'</p>'+
 '<div class="change-counts">'+Object.entries(cmp.changes).map(([k,v])=>'<span>'+tag(k)+' <b>'+v+'</b></span>').join("")+'</div><p class="range-note">分母为此分组的案例 ID 并集（含未运行）；实际已运行 '+cmp.left.passed+' + '+cmp.left.failed+' / '+cmp.right.passed+' + '+cmp.right.failed+'。'+(split==="all"?"此处混合开发与保留集。":"")+'</p>';
 const rows=D.filterCases(cmp.rows,cf);cp=Math.min(cp,Math.max(1,Math.ceil(rows.length/10)));
 const table='<div class="section-head"><h2>案例明细 <small>'+rows.length+' 项</small></h2>'+select("case-filter","筛选",[["待处理","待处理"],["退步","退步"],["仍失败","仍失败"],["改善","改善"],["全部","全部"]],cf)+'</div>'+
 (rows.length?'<div class="table-wrap"><table class="records case-table"><thead><tr><th>案例</th><th>场景</th><th>分组</th><th>'+esc(lv)+'</th><th>'+esc(rv)+'</th><th>变化</th><th>失败类别</th><th></th></tr></thead><tbody>'+rows.slice((cp-1)*10,cp*10).map(x=>'<tr><td data-label="案例">'+esc(x.id)+'</td><td data-label="场景" class="summary-cell">'+esc(x.case?.name||"场景未记录")+'</td><td data-label="分组">'+group(x.split)+'</td><td data-label="'+esc(lv)+'">'+tag(x.leftStatus)+'</td><td data-label="'+esc(rv)+'">'+tag(x.rightStatus)+'</td><td data-label="变化">'+tag(x.change)+'</td><td data-label="失败类别">'+esc(x.right?.category||x.right?.error?.category||x.left?.category||x.left?.error?.category||"—")+'</td><td><a href="/evaluation/'+encodeURIComponent(x.id)+'" data-nav="/evaluation/'+encodeURIComponent(x.id)+'">查看详情 →</a></td></tr>').join("")+'</tbody></table></div>':'<div class="empty-state small"><p>此筛选下没有案例。</p></div>')+pager(cp,rows.length,"cases");
 const verified=bundle.verification;
 const integration='<section class="integration-strip"><h2>集成状态</h2><span>模型：'+(boot.integrations.model_configured?"已配置；真实调用见上方报告":"未配置")+'</span><span>本地结算演练</span><span>托管结算：'+(boot.integrations.shopify_configured?"已配置，需另行验证":"未接入")+'</span><span>订单回传：未接入</span></section>';
 const evidence=r.iteration?.evidence||{};
 const iteration='<section class="surface detail-section"><div class="section-head"><h2>迭代记录</h2><span class="state neutral">规则策略调整</span></div>'+kv([
 ["问题",r.iteration?.description?.split("；")[0]||"未记录"],
 ["改动",r.iteration?.description?.split("；")[1]?.split("。")[0]||"未记录"],
 ["验证",full.comparable?(evidence[rv]?.map(x=>x.id).join("、")||"未记录关联案例")+" · 改善 "+full.changes["改善"]+" / 退步 "+full.changes["退步"]+" / 未变化 "+full.changes["未变化"]:"条件不足，不可整体比较"],
 ["遗留问题",r.live_status==="未运行"?"真实模型未运行；人工评分未记录":r.metrics?.plan_validity||"未记录"]])+'</section>';
 const currentVerify=bundle.current_verification;
 const currentValidation=currentVerify?'<section class="surface detail-section"><h2>当前版本验证</h2><p>'+D.date(currentVerify.ended_at,true)+' · 系统 '+esc(currentVerify.system?.passed??"—")+'/'+esc(currentVerify.system?.total??"—")+' · 呈现 '+esc(currentVerify.presentation?.passed??"—")+'/'+esc(currentVerify.presentation?.total??"—")+'</p><p>'+esc(currentVerify.limitations||"")+'</p></section>':"";
 const validation=verified?'<section class="surface detail-section"><h2>历史界面验证</h2><p>'+D.date(verified.created,true)+' · 系统 '+esc(verified.system?.passed??"—")+'/'+esc(verified.system?.total??"—")+' · 呈现计算 '+esc(verified.presentation?.passed??"—")+'/'+esc(verified.presentation?.total??"—")+'</p><small>独立于上方历史策略报告</small></section>':"";
 const footer=links([["原始评测报告","report"],["案例数据","cases"],["v1 策略","strategy-v1"],["v2 策略","strategy-v2"],["相关实现","implementation"],["评测实现","evaluation-code"],["验收说明","acceptance"],...(verified?[["本次界面验证","ui-verification"]]:[])]);
 $("#main").innerHTML=page("评测与迭代",badcasePanel()+liveReports()+meta+metrics+'<section class="surface detail-section">'+controls+graph+'</section><section class="surface detail-section">'+table+'</section>'+iteration+integration+currentValidation+validation+footer);
}
function assertions(r){
 if(!r)return '<p>未运行</p>';
 const pairs=Object.entries(D.obj(r.assertions));
 if(pairs.length)return '<ul class="assertions">'+pairs.map(([k,v])=>'<li>'+tag(v===true?"通过":v===false?"失败":"未记录")+' '+esc(labels[k]||k)+'</li>').join("")+'</ul>';
 if(r.test)return '<p>关联测试：'+esc(r.test)+'</p><p>'+tag(D.outcome(r))+'</p>'+long(D.arr(r.errors).length?r.errors:"逐项断言未记录");
 return '<p>'+tag(D.outcome(r))+' · 仅保存案例级判定，逐项断言未记录</p>';
}
function caseDetail(id){
 const r=bundle.report||{},x=D.compare(r,bundle.cases,lv,rv,"all").rows.find(x=>x.id===id);
 if(!x){$("#main").innerHTML=page("案例详情",'<p>当前报告没有此案例。</p>','<a href="/evaluation" data-nav="/evaluation">返回评测</a>');return}
 const e=x.case?.expected;
 $("#main").innerHTML=page("案例 "+x.id+' · '+(x.case?.name||"场景未记录"),
 '<div class="detail-meta">'+tag(x.change)+'<span>'+group(x.split)+'</span><span>'+D.mode(x.right||x.left||{})+'</span></div>'+
 '<section class="surface detail-section"><h2>输入与上下文</h2>'+long(x.right?.input||x.left?.input||x.case?.messages||"未记录")+
 (e?'<h3>预期约束 · 匹配的数据集文件</h3>'+kv(Object.entries(e).map(([k,v])=>[labels[k]||k,v])):'<p>预期约束未记录，或当前案例文件与报告不匹配。</p>')+
 (x.left?.before?'<h3>变更前条目</h3>'+long(x.left.before.map(offerName)):"")+'</section>'+
 '<div class="detail-grid">'+[[lv,x.left],[rv,x.right]].map(([v,row])=>'<section class="surface detail-section"><div class="section-head"><h2>'+esc(v)+'</h2>'+tag(D.outcome(row))+'</div><h3>实际输出</h3>'+output(row)+'<h3>断言与证据</h3>'+assertions(row)+
 (row?.traces?'<h3>已记录步骤</h3><ul class="plain-list">'+row.traces.flatMap(t=>D.arr(t.events)).map(ev=>'<li>'+tag(ev.error?"失败":"执行完成")+' '+esc(names[ev.tool]||ev.tool)+' · '+esc(stepResult(ev))+'</li>').join("")+'</ul>':"")+'</section>').join("")+'</div>'+
 '<section class="surface detail-section"><h2>关联改动</h2>'+long(Object.values(r.iteration?.evidence||{}).some(rows=>D.arr(rows).some(t=>t.id===id))?r.iteration.description:"未记录此案例的策略改动关联")+'<p>'+esc(x.reason||"按相同案例 ID 与记录条件比较")+'</p></section>'+
 links([["原始报告","report"],["案例数据","cases"],["v1 策略","strategy-v1"],["v2 策略","strategy-v2"],["相关实现","implementation"]]),
 '<a href="/evaluation" data-nav="/evaluation">← 返回评测与迭代</a>');
}
async function routePage(path){
 if(path==="/runs"){runs=await api("/api/runs");renderRuns()}
 else if(path.startsWith("/runs/")){await runDetail(path.split("/")[2])}
 else{bundle=await api("/api/maintenance");if(path==="/evaluation")renderEval();else if(path.startsWith("/evaluation/badcase/"))badcaseDetail(decodeURIComponent(path.split("/")[3]));else{const vs=Object.keys(bundle.report?.rows||{});lv=lv||vs[0];rv=rv||vs.at(-1);caseDetail(decodeURIComponent(path.split("/")[2]))}}
}
document.addEventListener("change",e=>{
 if(e.target.id==="badcase-filter"){badFilter=e.target.value;renderEval()}
 if(["run-task","run-status","run-mode"].includes(e.target.id)){rf[e.target.id.slice(4)]=e.target.value;rp=1;renderRuns()}
 if(["eval-split","eval-left","eval-right","case-filter"].includes(e.target.id)){
 if(e.target.id==="eval-split")split=e.target.value;if(e.target.id==="eval-left")lv=e.target.value;if(e.target.id==="eval-right")rv=e.target.value;if(e.target.id==="case-filter")cf=e.target.value;cp=1;renderEval()}
});
document.addEventListener("click",e=>{const el=e.target.closest("[data-maint]");if(!el||el.disabled)return;
 if(el.dataset.maint==="runs-page"){rp=Number(el.dataset.page);renderRuns()}if(el.dataset.maint==="cases-page"){cp=Number(el.dataset.page);renderEval()}});
return {route:routePage};
})();
