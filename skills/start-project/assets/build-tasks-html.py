#!/usr/bin/env python3
"""把任务数据源构建成**单文件、离线可双击**的 HTML 看板。

源（唯一事实源，勿手改 HTML）：
  - `docs/tasks.yaml` —— 轨 → 模块 → 任务 三级 + 状态/面向/类型/负责人/依赖

输出：`docs/tasks-html/index.html`（内联 CSS/JS，无外链；双击即看）
     三视图：看板（按状态列）/ 树（轨→模块→任务）/ 矩阵（模块 × 状态）
     筛选：轨 / 模块 / 状态 / 面向 / 类型 / 负责人 + 关键字搜索

用法（在仓库根目录）：`python scripts/build-tasks-html.py`
数据或样式变更后重跑本脚本；**不要手改生成的 HTML**。
"""

from __future__ import annotations

import html
import json
import math
import re
import sys
from datetime import date, timedelta
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    print("ERROR: PyYAML not found. Install with: python -m pip install pyyaml")
    sys.exit(1)

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE = REPO_ROOT / "docs" / "tasks.yaml"
OUT_DIR = REPO_ROOT / "docs" / "tasks-html"
OUT_FILE = OUT_DIR / "index.html"

STATUS_ORDER = ["done", "doing", "blocked", "todo"]
STATUS_LABEL = {
    "done": "已完成",
    "doing": "进行中",
    "blocked": "被阻塞",
    "todo": "未开始",
}
STATUS_HINT = {
    "done": "已交付",
    "doing": "正在做",
    "blocked": "等外部 / 他人",
    "todo": "还没开始",
}

CSS = """
*{box-sizing:border-box}
:root{
  --bg:#f4f6fa; --card:#fff; --ink:#111827; --ink-2:#374151; --muted:#6b7280;
  --line:#e5e7eb; --line-2:#eef1f5;
  --brand:#2563eb; --brand-soft:#eff4ff;
  --done:#15803d; --done-soft:#ecfdf3; --done-deep:#bbf7d0;
  --doing:#2563eb; --doing-soft:#eff4ff; --doing-deep:#bfdbfe;
  --blocked:#b91c1c; --blocked-soft:#fef2f2; --blocked-deep:#fecaca;
  --todo:#6b7280; --todo-soft:#f3f4f6; --todo-deep:#e5e7eb;
  --warn:#b45309; --warn-soft:#fffbeb;
  --radius:10px;
}
html,body{margin:0;padding:0}
body{
  background:var(--bg); color:var(--ink-2);
  font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",Roboto,"Helvetica Neue",Arial,sans-serif;
}
a{color:var(--brand);text-decoration:none}
code{background:#f3f4f6;border:1px solid var(--line);border-radius:5px;padding:0 4px;font-size:12.5px}
.wrap{width:100%;padding:0 22px 40px}

/* ---------- header ---------- */
.topbar{
  background:linear-gradient(90deg,#1e3a8a,#2563eb); color:#fff;
  padding:18px 22px 16px; margin-bottom:16px;
  display:flex;flex-wrap:wrap;align-items:baseline;gap:10px 18px;
}
.topbar h1{font-size:20px;margin:0;font-weight:650;letter-spacing:.2px}
.topbar .meta{font-size:12.5px;opacity:.92}
.topbar .meta b{font-weight:600}

/* ---------- KPI ---------- */
.kpis{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px;margin-bottom:14px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);padding:12px 14px}
.kpi .k-label{font-size:12.5px;color:var(--muted);display:flex;align-items:center;gap:6px}
.kpi .k-num{font-size:26px;font-weight:680;line-height:1.15;margin-top:2px;font-variant-numeric:tabular-nums}
.kpi .k-sub{font-size:12px;color:var(--muted)}
.kpi[data-s="done"] .k-num{color:var(--done)}
.kpi[data-s="doing"] .k-num{color:var(--doing)}
.kpi[data-s="blocked"] .k-num{color:var(--blocked)}
.kpi[data-s="todo"] .k-num{color:var(--todo)}
.kpi[data-s="total"] .k-num{color:var(--ink)}
.dot{width:9px;height:9px;border-radius:50%;display:inline-block;flex:0 0 auto}
.dot.done{background:var(--done)} .dot.doing{background:var(--doing)}
.dot.blocked{background:var(--blocked)} .dot.todo{background:var(--todo)}
.progress{height:8px;background:#e9edf3;border-radius:99px;overflow:hidden;margin-top:9px;display:flex}
.progress i{display:block;height:100%}
.progress i.done{background:var(--done)}
.progress i.doing{background:var(--doing)}
.progress i.blocked{background:var(--blocked)}

/* ---------- milestones ---------- */
.milestones{display:grid;grid-template-columns:repeat(auto-fit,minmax(228px,1fr));gap:10px;margin-bottom:14px}
.ms{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--todo);border-radius:var(--radius);padding:9px 12px}
.ms[data-s="done"]{border-left-color:var(--done)}
.ms[data-s="doing"]{border-left-color:var(--doing)}
.ms[data-s="blocked"]{border-left-color:var(--blocked)}
.ms .ms-name{font-weight:600;color:var(--ink);font-size:13.5px;display:flex;gap:6px;align-items:flex-start}
.ms .ms-meta{font-size:12px;color:var(--muted);margin-top:4px}
.ms .ms-gate{font-size:11.5px;color:var(--muted);margin-top:2px}
@media (max-width:1180px){ .milestones{grid-template-columns:repeat(2,minmax(0,1fr))} }
@media (max-width:720px){ .milestones{grid-template-columns:1fr} }

/* ---------- toolbar ---------- */
.toolbar{
  background:var(--card);border:1px solid var(--line);border-radius:var(--radius);
  padding:11px 13px;margin-bottom:14px;
  display:flex;flex-wrap:wrap;gap:10px;align-items:center;
  position:sticky;top:0;z-index:20;box-shadow:0 1px 0 rgba(17,24,39,.03);
}
.tabs{display:flex;gap:4px;background:#f1f4f9;border-radius:8px;padding:3px}
.tabs button{
  border:0;background:transparent;color:var(--ink-2);font:inherit;font-weight:560;
  padding:6px 14px;border-radius:6px;cursor:pointer;
}
.tabs button[aria-selected="true"]{background:var(--card);color:var(--brand);box-shadow:0 1px 3px rgba(17,24,39,.10)}
.filters{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-left:auto}
.filters select,.filters input[type=search]{
  font:inherit;color:var(--ink-2);background:var(--card);
  border:1px solid var(--line);border-radius:7px;padding:6px 9px;
}
.filters input[type=search]{min-width:210px}
.filters .clear{border:1px solid var(--line);background:var(--card);border-radius:7px;padding:6px 11px;cursor:pointer;font:inherit}
.filters .clear:hover{border-color:var(--brand);color:var(--brand)}
.filters .chk{display:inline-flex;align-items:center;gap:5px;font-size:12.5px;color:var(--muted);cursor:pointer;border:1px solid var(--line);border-radius:7px;padding:6px 10px;background:var(--card)}
.filters .chk input{margin:0;cursor:pointer}

/* ---------- shared card ---------- */
.task{
  background:linear-gradient(90deg,#fff 50%,var(--todo-deep) 100%);
  border:1px solid var(--line);border-left:3px solid var(--todo);
  border-radius:8px;padding:8px 10px;
}
.task[data-status="done"]{border-left-color:var(--done);background:linear-gradient(90deg,#fff 50%,var(--done-deep) 100%)}
.task[data-status="doing"]{border-left-color:var(--doing);background:linear-gradient(90deg,#fff 50%,var(--doing-deep) 100%)}
.task[data-status="blocked"]{border-left-color:var(--blocked);background:linear-gradient(90deg,#fff 50%,var(--blocked-deep) 100%)}
.task .t-head{display:flex;gap:7px;align-items:flex-start}
.task .t-id{font:600 11.5px/1.7 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;color:var(--muted);background:#f3f4f6;border-radius:5px;padding:0 5px;flex:0 0 auto}
.task .t-title{font-weight:560;color:var(--ink)}
.task .t-foot{display:flex;flex-wrap:wrap;gap:5px;margin-top:6px;align-items:center}
.chip{
  font-size:11.5px;border-radius:99px;padding:1px 8px;border:1px solid var(--line);color:var(--muted);background:#fafbfd;
}
.chip.face{background:var(--brand-soft);color:var(--brand);border-color:#dbe6fe}
.chip.type{background:#f5f3ff;color:#6d28d9;border-color:#ede9fe}
.chip.track{font-weight:600}
.chip.track[data-track="backend"]{background:#eff4ff;color:#1d4ed8;border-color:#dbe6fe}
.chip.track[data-track="admin"]{background:#f5f3ff;color:#6d28d9;border-color:#ede9fe}
.chip.track[data-track="h5"]{background:#ecfdf5;color:#047857;border-color:#d1fae5}
.chip.track[data-track="cross"]{background:#fff7ed;color:#c2410c;border-color:#fed7aa}
.chip.dep{background:var(--blocked-soft);color:var(--blocked);border-color:#fee2e2}
.chip.owner{background:#f0fdfa;color:#0f766e;border-color:#ccfbf1}
.chip.date{background:#f8fafc}
.warn{color:var(--warn);cursor:help;font-weight:700}
.note{margin-top:6px;font-size:12.5px;color:var(--muted)}
.hide{display:none !important}

/* ---------- kanban ---------- */
.kanban{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;align-items:start}
.kan-col{background:#eef1f6;border:1px solid var(--line);border-radius:var(--radius);padding:10px}
.kan-col h3{margin:0 0 9px;font-size:13.5px;display:flex;align-items:center;gap:7px;color:var(--ink)}
.kan-col h3 .n{color:var(--muted);font-weight:600}
.kan-list{display:grid;gap:8px;max-height:calc(100vh - 330px);overflow-y:auto;padding-right:3px;scrollbar-width:thin}
.kan-list::-webkit-scrollbar{width:8px}
.kan-list::-webkit-scrollbar-thumb{background:#cbd5e1;border-radius:99px}
.kan-empty{color:var(--muted);font-size:12.5px;padding:8px 2px}
@media (max-width:1180px){ .kanban{grid-template-columns:repeat(2,minmax(0,1fr))} }
@media (max-width:720px){ .kanban{grid-template-columns:1fr} .kpis{grid-template-columns:repeat(2,minmax(0,1fr))} }

/* ---------- tree ---------- */
.tree{display:grid;gap:10px}
.track{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);overflow:hidden}
.track>summary{
  list-style:none;cursor:pointer;padding:11px 14px;display:flex;align-items:center;gap:10px;
  background:#fbfcfe;border-bottom:1px solid var(--line-2);
}
.track>summary::-webkit-details-marker{display:none}
.track>summary::before{content:"▾";color:var(--muted);font-size:12px}
.track:not([open])>summary::before{content:"▸"}
.track .tr-name{font-weight:640;color:var(--ink);font-size:15px}
.track .tr-kind{font-size:12.5px;color:var(--muted)}
.track .tr-stat{margin-left:auto;display:flex;gap:8px;flex-wrap:wrap;font-size:12px}
.mod{padding:6px 14px 12px 14px}
.mod+.mod{border-top:1px dashed var(--line-2)}
.mod-h{display:flex;align-items:center;gap:9px;margin:9px 0 7px;font-weight:600;color:var(--ink)}
.mod-h .m-id{font:600 11.5px/1.7 ui-monospace,Menlo,Consolas,monospace;color:var(--muted)}
.mod-h .m-n{color:var(--muted);font-weight:500;font-size:12.5px}
.mod-list{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:8px}

/* ---------- matrix ---------- */
.matrix{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);padding:12px 14px}
.mrow{display:grid;grid-template-columns:230px repeat(4,minmax(0,1fr)) 92px;gap:6px;align-items:center}
.mrow.head{padding-bottom:7px;margin-bottom:4px;border-bottom:1px solid var(--line)}
.mrow.head .mh{font-size:12.5px;color:var(--muted);display:flex;align-items:center;gap:6px}
.mrow+.mrow{margin-top:5px}
.mname{font-size:13px;color:var(--ink);padding-right:6px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.mname .mt{color:var(--muted);font-size:11.5px}
.mcell{
  border-radius:7px;text-align:center;padding:6px 0;font-weight:620;font-variant-numeric:tabular-nums;
  border:1px solid var(--line);background:#fafbfd;color:var(--muted);
}
.mcell.has[data-status="done"]{background:var(--done-soft);color:var(--done);border-color:#bbf7d0}
.mcell.has[data-status="doing"]{background:var(--doing-soft);color:var(--doing);border-color:#dbe6fe}
.mcell.has[data-status="blocked"]{background:var(--blocked-soft);color:var(--blocked);border-color:#fee2e2}
.mcell.has[data-status="todo"]{background:#f8fafc;color:var(--ink-2)}
.mbar{height:8px;border-radius:99px;background:#e9edf3;overflow:hidden}
.mbar i{display:block;height:100%;background:var(--done)}
.empty{padding:26px;text-align:center;color:var(--muted);background:var(--card);border:1px dashed var(--line);border-radius:var(--radius)}
.legend{margin-top:12px;font-size:12.5px;color:var(--muted)}
footer{padding:16px 22px 30px;color:var(--muted);font-size:12.5px}

/* ---------- overview ---------- */
.ov-grid{display:grid;grid-template-columns:minmax(300px,5fr) minmax(0,7fr);gap:14px;margin-bottom:14px}
.ov-card{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);padding:14px 16px}
.ov-card h3{margin:0 0 12px;font-size:14px;color:var(--ink);font-weight:640}
.ov-donuts{display:flex;flex-wrap:wrap;gap:18px;justify-content:space-around}
.ov-donut{text-align:center}
.ov-donut svg{display:block;margin:0 auto}
.ov-donut .dl{font-size:12.5px;color:var(--muted);margin-top:6px}
.ov-legend{display:flex;flex-wrap:wrap;gap:4px 12px;justify-content:center;margin-top:6px;font-size:11.5px;color:var(--muted)}
.ov-legend i{width:8px;height:8px;border-radius:2px;display:inline-block;margin-right:4px}
.ov-meta{margin-top:14px;padding-top:11px;border-top:1px dashed var(--line-2);display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px 14px;font-size:12.5px;color:var(--muted)}
.ov-meta b{color:var(--ink-2);font-weight:600}
.ov-chart{width:100%;height:auto;display:block}
.ov-ms{width:100%;border-collapse:collapse;font-size:13px}
.ov-ms th{font-size:12px;color:var(--muted);font-weight:560;text-align:left;padding:7px 10px;border-bottom:1px solid var(--line)}
.ov-ms td{padding:8px 10px;border-bottom:1px solid var(--line-2);color:var(--ink-2);vertical-align:middle}
.ov-ms tr:last-child td{border-bottom:0}
.ov-ms .msbar{width:120px;height:8px;border-radius:99px;background:#e9edf3;overflow:hidden;display:inline-block;vertical-align:middle;margin-right:7px}
.ov-ms .msbar i{display:block;height:100%;background:var(--done)}
.ov-tag{display:inline-block;border-radius:99px;padding:1px 9px;font-size:11.5px;font-weight:600}
.ov-tag.done{background:var(--done-soft);color:var(--done)}
.ov-tag.doing{background:var(--doing-soft);color:var(--doing)}
.ov-tag.blocked{background:var(--blocked-soft);color:var(--blocked)}
.ov-tag.todo{background:var(--todo-soft);color:var(--todo)}
@media (max-width:1180px){ .ov-grid{grid-template-columns:1fr} }

/* ---------- task detail modal ---------- */
.task{cursor:pointer}
.modal-mask{position:fixed;inset:0;background:rgba(17,24,39,.45);display:flex;align-items:center;justify-content:center;z-index:60;padding:20px}
.modal{background:var(--card);border-radius:12px;width:100%;max-width:560px;max-height:84vh;overflow:auto;padding:18px 20px;box-shadow:0 14px 44px rgba(17,24,39,.28)}
.modal .m-head{display:flex;gap:8px;align-items:flex-start;margin-bottom:12px}
.modal .m-title{font-size:15.5px;font-weight:640;color:var(--ink)}
.modal .m-close{margin-left:auto;border:0;background:#f3f4f6;border-radius:7px;width:26px;height:26px;cursor:pointer;font-size:13px;color:var(--muted);flex:0 0 auto}
.modal .m-close:hover{background:#e5e7eb;color:var(--ink)}
.modal .m-grid{display:grid;grid-template-columns:88px 1fr;gap:7px 12px;font-size:13px;margin:0}
.modal .m-grid dt{color:var(--muted)}
.modal .m-grid dd{margin:0;color:var(--ink-2)}
.modal .m-note{margin-top:12px;padding:9px 11px;background:#f8fafc;border:1px solid var(--line-2);border-radius:8px;font-size:13px;color:var(--ink-2)}
.modal .m-note::before{content:"备注 · ";color:var(--muted)}
.modal .m-desc{margin:-4px 0 12px;padding:9px 11px;background:var(--brand-soft);border:1px solid #dbe6fe;border-radius:8px;font-size:13px;color:var(--ink-2)}
.modal .m-status{display:inline-block;border-radius:99px;padding:1px 10px;font-size:12px;font-weight:600;color:#fff}
.modal .m-status.done{background:var(--done)} .modal .m-status.doing{background:var(--doing)}
.modal .m-status.blocked{background:var(--blocked)} .modal .m-status.todo{background:var(--todo)}
"""

JS = """
(function(){
  var DATA = window.__TASKS__;
  var tasks = DATA.tasks;
  var F = {track:"", module:"", status:"", face:"", type:"", owner:"", q:"", inf:false};

  function el(id){return document.getElementById(id);}
  function matches(t){
    if(F.inf && !t.inferred) return false;
    if(F.track && t.track!==F.track) return false;
    if(F.module && t.module!==F.module) return false;
    if(F.status && t.status!==F.status) return false;
    if(F.face && t.face!==F.face) return false;
    if(F.type && t.type!==F.type) return false;
    if(F.owner && t.owner!==F.owner) return false;
    if(F.q){
      var hay=(t.id+" "+t.title+" "+t.trackName+" "+t.moduleName+" "+(t.owner||"")+" "+(t.note||"")).toLowerCase();
      if(hay.indexOf(F.q)<0) return false;
    }
    return true;
  }
  function counts(list){
    var c={total:list.length,done:0,doing:0,blocked:0,todo:0};
    list.forEach(function(t){c[t.status]=(c[t.status]||0)+1;});
    return c;
  }
  function pct(n,d){return d?Math.round(n*100/d):0;}

  function apply(){
    var vis=tasks.filter(matches), ids={};
    vis.forEach(function(t){ids[t.id]=1;});
    document.querySelectorAll("[data-id]").forEach(function(n){
      n.classList.toggle("hide", !ids[n.getAttribute("data-id")]);
    });
    // 空列提示
    document.querySelectorAll(".kan-col").forEach(function(col){
      var s=col.getAttribute("data-col"), any=false;
      col.querySelectorAll(".task").forEach(function(n){ if(!n.classList.contains("hide")) any=true; });
      var e=col.querySelector(".kan-empty"); if(e) e.classList.toggle("hide", any);
    });
    // KPI
    var c=counts(vis);
    ["done","doing","blocked","todo","total"].forEach(function(k){
      var n=el("kpi-"+k); if(n) n.textContent=c[k]||0;
    });
    var p=el("kpi-pct"); if(p) p.textContent=pct(c.done,c.total)+"%";
    var bar=el("progress"); if(bar){
      bar.querySelector(".done").style.width=pct(c.done,c.total)+"%";
      bar.querySelector(".doing").style.width=pct(c.doing,c.total)+"%";
      bar.querySelector(".blocked").style.width=pct(c.blocked,c.total)+"%";
    }
    // 看板列头计数
    document.querySelectorAll(".kan-col").forEach(function(col){
      var s=col.getAttribute("data-col");
      var n=col.querySelector("h3 .n");
      if(n) n.textContent="("+(c[s]||0)+")";
    });
    // 矩阵单元计数 + 模块行显隐 + 进度条
    document.querySelectorAll(".mrow[data-track]").forEach(function(row){
      var mod=row.getAttribute("data-module"), track=row.getAttribute("data-track");
      var sub=vis.filter(function(t){return t.track===track && t.module===mod;});
      var sc=counts(sub), shown=false;
      row.querySelectorAll(".mcell").forEach(function(cell){
        var st=cell.getAttribute("data-status"), v=sc[st]||0;
        cell.textContent=v;
        cell.classList.toggle("has", v>0);
        if(v>0) shown=true;
      });
      var bar=row.querySelector(".mbar i"); if(bar) bar.style.width=pct(sc.done,sc.total)+"%";
      row.classList.toggle("hide", !shown);
    });
    // 整轨无可见任务时隐藏轨道块（树视图）
    document.querySelectorAll("details.track").forEach(function(d){
      var any=false;
      d.querySelectorAll(".task").forEach(function(n){ if(!n.classList.contains("hide")) any=true; });
      d.classList.toggle("hide", !any);
    });
    // 矩阵里整轨分节标题
    document.querySelectorAll("[data-track-head]").forEach(function(h){
      var tk=h.getAttribute("data-track-head"), any=false;
      document.querySelectorAll('.mrow[data-track="'+tk+'"]').forEach(function(r){ if(!r.classList.contains("hide")) any=true; });
      h.classList.toggle("hide", !any);
    });
    var tot=el("vis-count"); if(tot) tot.textContent="显示 "+vis.length+" / "+tasks.length+" 条";
    var none=el("matrix-none");
    if(none){
      var anyRows=false;
      document.querySelectorAll(".mrow[data-track]").forEach(function(r){ if(!r.classList.contains("hide")) anyRows=true; });
      none.classList.toggle("hide", anyRows);
    }
  }

  function setView(v){
    document.querySelectorAll(".tabs button").forEach(function(b){
      b.setAttribute("aria-selected", b.getAttribute("data-view")===v ? "true":"false");
    });
    ["overview","kanban","tree","matrix"].forEach(function(k){
      el("view-"+k).classList.toggle("hide", k!==v);
    });
    try{ localStorage.setItem("taskboard.view", v); }catch(e){}
  }

  document.querySelectorAll(".tabs button").forEach(function(b){
    b.addEventListener("click", function(){ setView(b.getAttribute("data-view")); });
  });
  ["track","module","status","face","type","owner"].forEach(function(k){
    var s=el("f-"+k);
    if(s) s.addEventListener("change", function(){ F[k]=s.value; apply(); });
  });
  var q=el("f-q");
  if(q) q.addEventListener("input", function(){ F.q=q.value.trim().toLowerCase(); apply(); });
  var inf=el("f-inf");
  if(inf) inf.addEventListener("change", function(){ F.inf=inf.checked; apply(); });
  var cl=el("f-clear");
  if(cl) cl.addEventListener("click", function(){
    F={track:"",module:"",status:"",face:"",type:"",owner:"",q:"",inf:false};
    ["track","module","status","face","type","owner","q"].forEach(function(k){ var s=el("f-"+k); if(s) s.value=""; });
    if(inf) inf.checked=false;
    apply();
  });
  document.querySelectorAll("details.track").forEach(function(d,i){
    try{ var k="taskboard.track."+i; if(localStorage.getItem(k)==="0") d.removeAttribute("open"); }catch(e){}
    d.addEventListener("toggle", function(){ try{ localStorage.setItem("taskboard.track."+i, d.open?"1":"0"); }catch(e){} });
  });

  var saved="overview";
  try{ saved=localStorage.getItem("taskboard.view")||"overview"; }catch(e){}
  setView(document.querySelector('.tabs button[data-view="'+saved+'"]') ? saved : "overview");

  // ---- 任务详情弹窗 ----
  var SL={done:"已完成",doing:"进行中",blocked:"被阻塞",todo:"未开始"};
  var byId={};
  tasks.forEach(function(t){byId[t.id]=t;});
  var mask=el("modal-mask");
  function escHtml(s){return String(s==null?"":s).replace(/[&<>"']/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];});}
  function mrow(k,v){return v?("<dt>"+k+"</dt><dd>"+v+"</dd>"):"";}
  function openTask(id){
    var t=byId[id]; if(!t||!mask) return;
    mask.querySelector(".modal").innerHTML=
      '<div class="m-head"><span class="t-id">'+escHtml(t.id)+'</span>'
      +'<span class="m-title">'+(t.inferred?'<span class="warn" title="由现有资料反向推断，尚未经确认">⚠</span> ':'')+escHtml(t.title)+'</span>'
      +'<button class="m-close" type="button" aria-label="关闭">✕</button></div>'
      +(t.desc?'<div class="m-desc">'+escHtml(t.desc)+'</div>':"")
      +'<dl class="m-grid">'
      +mrow("状态",'<span class="m-status '+t.status+'">'+(SL[t.status]||t.status)+'</span>')
      +mrow("轨道 / 模块",escHtml(t.trackName||t.track)+" / "+escHtml(t.moduleName||t.module))
      +mrow("面向",escHtml(t.face))
      +mrow("类型",escHtml(t.type))
      +mrow("负责人",escHtml(t.owner))
      +mrow("创建时间",escHtml(t.created))
      +mrow("完成时间",escHtml(t.date))
      +mrow("被阻塞于",(t.dep&&t.dep.length)?t.dep.map(escHtml).join("、"):"")
      +mrow("旧编号",escHtml(t.legacy))
      +'</dl>'
      +(t.note?'<div class="m-note">'+escHtml(t.note)+'</div>':"");
    mask.classList.remove("hide");
  }
  function closeTask(){ if(mask) mask.classList.add("hide"); }
  document.addEventListener("click",function(e){
    var n=e.target.closest?e.target.closest(".task"):null;
    if(n){ openTask(n.getAttribute("data-id")); return; }
    if(e.target===mask || (e.target.closest&&e.target.closest(".m-close"))) closeTask();
  });
  document.addEventListener("keydown",function(e){ if(e.key==="Escape") closeTask(); });

  apply();
})();
"""


def esc(s: str) -> str:
    return html.escape(str(s), quote=True)


def rich(s: str) -> str:
    """极小 Markdown：**粗体** → <strong>；其余转义。"""
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc(s))


def _parse_day(s: str) -> date | None:
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def donut(segments: list[tuple[int, str, str]], center_top: str, center_bottom: str) -> str:
    """segments = [(数量, 颜色, 图例标签)]；纯 SVG 环形图，中心两行文字。"""
    total = sum(v for v, _, _ in segments)
    r, cx, cy, sw = 52.0, 70.0, 70.0, 20.0
    circ = 2 * math.pi * r
    parts, offset, legend = [], 0.0, []
    for value, color, label in segments:
        if value <= 0:
            continue
        frac = value / total if total else 0
        dash = frac * circ
        parts.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{color}" stroke-width="{sw}"'
            f' stroke-dasharray="{dash:.2f} {circ - dash:.2f}" stroke-dashoffset="{-offset:.2f}"'
            f' transform="rotate(-90 {cx} {cy})"><title>{esc(label)} {value}</title></circle>'
        )
        legend.append(f'<span><i style="background:{color}"></i>{esc(label)} {value}</span>')
        offset += dash
    if not parts:
        parts.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#e5e7eb" stroke-width="{sw}"/>'
        )
    svg = (
        f'<svg width="140" height="140" viewBox="0 0 140 140">{"".join(parts)}'
        f'<text x="{cx}" y="{cy - 2}" text-anchor="middle" font-size="22" font-weight="680" fill="#111827">{esc(center_top)}</text>'
        f'<text x="{cx}" y="{cy + 18}" text-anchor="middle" font-size="11.5" fill="#6b7280">{esc(center_bottom)}</text></svg>'
    )
    return f'{svg}<div class="ov-legend">{"".join(legend)}</div>'


def burndown(tasks: list[dict]) -> str:
    """按 created/date 推导：灰虚线=总量(scope)，蓝线=剩余，红柱=当日新增。"""
    created = [d for d in (_parse_day(t["created"]) for t in tasks) if d]
    if not created:
        return '<div class="empty">任务缺少创建日期，无法绘制燃尽图</div>'
    start, end = min(created), max(date.today(), max(created))
    done_days = [d for d in (_parse_day(t["date"]) for t in tasks if t["status"] == "done") if d]
    days, cur = [], start
    while cur <= end:
        days.append(cur)
        cur += timedelta(days=1)
    scope = [sum(1 for d in created if d <= day) for day in days]
    remain = [sc - sum(1 for d in done_days if d <= day) for sc, day in zip(scope, days)]
    added = [sum(1 for d in created if d == day) for day in days]

    W, H, pl, pr, pt, pb = 920.0, 300.0, 38.0, 14.0, 16.0, 30.0
    ymax = max(max(scope), 1)
    n = len(days)
    step = (W - pl - pr) / max(n - 1, 1)

    def xy(i: int, v: float) -> tuple[float, float]:
        return pl + i * step, pt + (H - pt - pb) * (1 - v / ymax)

    grid = []
    for frac, lbl in ((0, "0"), (0.5, str(math.ceil(ymax / 2))), (1, str(ymax))):
        y = pt + (H - pt - pb) * (1 - frac)
        grid.append(
            f'<line x1="{pl}" y1="{y:.1f}" x2="{W - pr}" y2="{y:.1f}" stroke="#eef1f5"/>'
            f'<text x="{pl - 6}" y="{y + 4:.1f}" text-anchor="end" font-size="10.5" fill="#9ca3af">{lbl}</text>'
        )
    bw = min(step * 0.55, 14.0)
    bars = []
    for i, a in enumerate(added):
        if a <= 0:
            continue
        x, y = xy(i, a)
        bars.append(
            f'<rect x="{x - bw / 2:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{H - pb - y:.1f}"'
            f' rx="1.5" fill="#f87171"><title>{days[i].isoformat()} 新增 {a}</title></rect>'
        )
    scope_pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (xy(i, v) for i, v in enumerate(scope)))
    remain_pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (xy(i, v) for i, v in enumerate(remain)))
    xlabels = []
    for i in sorted({0, n // 2, n - 1}):
        x, _ = xy(i, 0)
        xlabels.append(
            f'<text x="{x:.1f}" y="{H - 8:.1f}" text-anchor="middle" font-size="10.5" fill="#9ca3af">{days[i].strftime("%m-%d")}</text>'
        )
    return (
        f'<svg class="ov-chart" viewBox="0 0 {W:.0f} {H:.0f}" preserveAspectRatio="xMidYMid meet">'
        + "".join(grid)
        + "".join(bars)
        + f'<polyline points="{scope_pts}" fill="none" stroke="#9ca3af" stroke-width="1.6" stroke-dasharray="5 4"/>'
        + f'<polyline points="{remain_pts}" fill="none" stroke="#2563eb" stroke-width="2.2"/>'
        + "".join(xlabels)
        + "</svg>"
        + '<div class="ov-legend"><span><i style="background:#2563eb"></i>剩余任务</span>'
        + '<span><i style="background:#9ca3af"></i>任务总量</span>'
        + '<span><i style="background:#f87171"></i>当日新增</span></div>'
    )


TRACK_COLORS = {"backend": "#1d4ed8", "admin": "#6d28d9", "h5": "#047857", "cross": "#c2410c"}
TYPE_COLORS = {"开发": "#2563eb", "文档": "#0f766e", "联调": "#c2410c", "运维": "#b45309"}
MS_COLORS = {"done": "#15803d", "doing": "#2563eb", "blocked": "#b91c1c", "todo": "#6b7280"}


def overview(data: dict, tasks: list[dict]) -> str:
    tracks = data["tracks"]
    c = {"done": 0, "doing": 0, "blocked": 0, "todo": 0}
    for t in tasks:
        c[t["status"]] += 1
    total = len(tasks)
    done_pct = round(c["done"] * 100 / total) if total else 0

    d_rate = donut(
        [(c["done"], "#15803d", "已完成"), (total - c["done"], "#e5e7eb", "未完成")],
        f"{done_pct}%",
        "完成率",
    )
    d_track = donut(
        [
            (sum(1 for t in tasks if t["track"] == tr["id"]), TRACK_COLORS.get(tr["id"], "#6b7280"), tr.get("short") or tr["name"])
            for tr in tracks
        ],
        str(total),
        "按轨分布",
    )
    types = []
    for ty, color in TYPE_COLORS.items():
        n = sum(1 for t in tasks if t["type"] == ty)
        if n:
            types.append((n, color, ty))
    d_type = donut(types, str(total), "按类型")

    track_owner = " / ".join(f'{tr.get("short") or tr["name"]}·{tr.get("owner", "—")}' for tr in tracks)
    info = f"""
<div class="ov-card">
  <h3>项目信息</h3>
  <div class="ov-donuts">
    <div class="ov-donut">{d_rate}</div>
    <div class="ov-donut">{d_track}</div>
    <div class="ov-donut">{d_type}</div>
  </div>
  <div class="ov-meta">
    <span>迭代 <b>{esc(data['iteration'])}</b></span>
    <span>更新 <b>{esc(data['updated'])}</b></span>
    <span>任务总数 <b>{total}</b>（阻塞 {c['blocked']}）</span>
    <span>各轨负责 <b>{esc(track_owner)}</b></span>
  </div>
</div>"""

    chart = f"""
<div class="ov-card">
  <h3>燃尽图（按任务创建 / 完成日期推导）</h3>
  {burndown(tasks)}
</div>"""

    track_stat = {
        tr["id"]: (
            sum(1 for t in tasks if t["track"] == tr["id"] and t["status"] == "done"),
            sum(1 for t in tasks if t["track"] == tr["id"]),
        )
        for tr in tracks
    }
    rows = []
    for ms in data.get("milestones", []) or []:
        st = ms.get("status", "todo")
        tk = ms.get("track", "")
        dn, tt = (c["done"], total) if tk == "cross" else track_stat.get(tk, (0, 0))
        # 已完成里程碑进度恒为 100%（轨内后续新增任务不追溯旧里程碑）；未完成按轨任务完成率估算
        pctv = 100 if st == "done" else (round(dn * 100 / tt) if tt else 0)
        rows.append(
            f"<tr><td><b>{rich(ms['name'])}</b></td>"
            f"<td>{esc(next((tr.get('short') or tr['name'] for tr in tracks if tr['id'] == tk), tk or '—'))}</td>"
            f'<td><span class="ov-tag {esc(st)}">{STATUS_LABEL[st]}</span></td>'
            f"<td>{esc(str(ms.get('date', '') or '—'))}</td>"
            f"<td>{rich(ms.get('gate', '—'))}</td>"
            f'<td><span class="msbar"><i style="width:{pctv}%"></i></span>{pctv}%</td></tr>'
        )
    milestone_table = f"""
<div class="ov-card">
  <h3>里程碑</h3>
  <table class="ov-ms">
    <thead><tr><th>标题</th><th>轨</th><th>状态</th><th>完成日期</th><th>门禁</th><th>进度（未完成的按轨任务估算）</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</div>"""

    return (
        '<section id="view-overview" class="view hide">'
        f'<div class="ov-grid">{info}{chart}</div>{milestone_table}</section>'
    )


def load() -> dict:
    with SOURCE.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def flatten(data: dict) -> list[dict]:
    out = []
    for tr in data["tracks"]:
        for mod in tr["modules"]:
            for t in mod["tasks"]:
                out.append(
                    {
                        "id": t["id"],
                        "title": t["title"],
                        "status": t["status"],
                        "face": t.get("face", ""),
                        "type": t.get("type", ""),
                        "owner": t.get("owner", ""),
                        "created": str(t.get("created", "") or ""),
                        "date": str(t.get("date", "") or ""),
                        "dep": t.get("dep", []) or [],
                        "legacy": t.get("legacy", ""),
                        "inferred": bool(t.get("inferred")),
                        "desc": t.get("desc", ""),
                        "note": t.get("note", ""),
                        "track": tr["id"],
                        "trackName": tr["name"],
                        "trackShort": tr.get("short") or tr["name"],
                        "module": mod["id"],
                        "moduleName": mod["name"],
                    }
                )
    return out


def task_card(t: dict, show_track: bool = False) -> str:
    chips = []
    if show_track:
        chips.append(
            f'<span class="chip track" data-track="{esc(t["track"])}">轨·{esc(t["trackShort"])}</span>'
        )
    if t["face"]:
        chips.append(f'<span class="chip face">面向·{esc(t["face"])}</span>')
    if t["type"]:
        chips.append(f'<span class="chip type">{esc(t["type"])}</span>')
    if t["owner"]:
        chips.append(f'<span class="chip owner">{esc(t["owner"])}</span>')
    if t["date"]:
        chips.append(f'<span class="chip date">{esc(t["date"])}</span>')
    for d in t["dep"]:
        chips.append(f'<span class="chip dep">挡：{esc(d)}</span>')
    warn = (
        '<span class="warn" title="由现有资料反向推断，尚未经确认">⚠</span>'
        if t["inferred"]
        else ""
    )
    note = f'<div class="note">{rich(t["note"])}</div>' if t["note"] else ""
    legacy = f' <span class="chip date">旧号 {esc(t["legacy"])}</span>' if t["legacy"] else ""
    return (
        f'<div class="task" data-id="{esc(t["id"])}" data-status="{esc(t["status"])}"'
        f' data-track="{esc(t["track"])}" data-module="{esc(t["module"])}">'
        f'<div class="t-head"><span class="t-id">{esc(t["id"])}</span>'
        f'<span class="t-title">{warn} {rich(t["title"])}</span></div>'
        f'<div class="t-foot">{"".join(chips)}{legacy}</div>{note}</div>'
    )


def render(data: dict) -> str:
    tasks = flatten(data)
    tracks = data["tracks"]

    def uniq(key):
        seen, out = set(), []
        for t in tasks:
            v = t.get(key)
            if v and v not in seen:
                seen.add(v)
                out.append(v)
        return out

    # ---- KPI ----
    c = {"total": len(tasks), "done": 0, "doing": 0, "blocked": 0, "todo": 0}
    for t in tasks:
        c[t["status"]] = c.get(t["status"], 0) + 1
    pct = lambda n, d: round(n * 100 / d) if d else 0

    kpis = f"""
<section class="kpis">
  <div class="kpi" data-s="total"><div class="k-label">全部任务</div>
    <div class="k-num" id="kpi-total">{c['total']}</div>
    <div class="k-sub">完成率 <b id="kpi-pct">{pct(c['done'], c['total'])}%</b>
      <div class="progress" id="progress"><i class="done" style="width:{pct(c['done'], c['total'])}%"></i><i class="doing" style="width:{pct(c['doing'], c['total'])}%"></i><i class="blocked" style="width:{pct(c['blocked'], c['total'])}%"></i></div>
    </div>
  </div>
  <div class="kpi" data-s="done"><div class="k-label"><i class="dot done"></i>已完成</div><div class="k-num" id="kpi-done">{c['done']}</div><div class="k-sub">已交付并通过门禁</div></div>
  <div class="kpi" data-s="doing"><div class="k-label"><i class="dot doing"></i>进行中</div><div class="k-num" id="kpi-doing">{c['doing']}</div><div class="k-sub">正在做</div></div>
  <div class="kpi" data-s="blocked"><div class="k-label"><i class="dot blocked"></i>被阻塞</div><div class="k-num" id="kpi-blocked">{c['blocked']}</div><div class="k-sub">等外部 / 他人</div></div>
  <div class="kpi" data-s="todo"><div class="k-label"><i class="dot todo"></i>未开始</div><div class="k-num" id="kpi-todo">{c['todo']}</div><div class="k-sub">已排期未动手</div></div>
</section>"""

    # ---- milestones ----
    track_short = {tr["id"]: (tr.get("short") or tr["name"]) for tr in tracks}
    ms_cards = []
    for ms in data.get("milestones", []) or []:
        st = ms.get("status", "todo")
        meta = " · ".join(
            x for x in [track_short.get(ms.get("track", ""), ms.get("track", "")), str(ms.get("date", "") or "")] if x
        )
        dep = f' · 挡：{", ".join(ms["dep"])}' if ms.get("dep") else ""
        ms_cards.append(
            f'<div class="ms" data-s="{esc(st)}"><div class="ms-name">'
            f'<i class="dot {esc(st)}"></i>{rich(ms["name"])}</div>'
            f'<div class="ms-meta">{STATUS_LABEL[st]}{" · " + esc(meta) if meta else ""}{esc(dep)}</div>'
            f'<div class="ms-gate">门禁：{rich(ms.get("gate", "—"))}</div></div>'
        )
    milestones = f'<section class="milestones">{"".join(ms_cards)}</section>' if ms_cards else ""

    # ---- toolbar ----
    def options(key, ph):
        return "".join(f'<option value="{esc(v)}">{esc(v)}</option>' for v in uniq(key))

    track_opts = "".join(
        f'<option value="{esc(tr["id"])}">{esc(tr.get("short") or tr["name"])}</option>'
        for tr in tracks
    )

    mod_opts = "".join(
        f'<option value="{esc(m["id"])}">{esc(tr["name"] + " › " + m["name"])}</option>'
        for tr in tracks
        for m in tr["modules"]
    )
    toolbar = f"""
<section class="toolbar">
  <div class="tabs" role="tablist">
    <button data-view="overview" aria-selected="false">概览</button>
    <button data-view="kanban" aria-selected="true">看板</button>
    <button data-view="tree" aria-selected="false">树</button>
    <button data-view="matrix" aria-selected="false">矩阵</button>
  </div>
  <div class="filters">
    <select id="f-track"><option value="">全部轨</option>{track_opts}</select>
    <select id="f-module"><option value="">全部模块</option>{mod_opts}</select>
    <select id="f-status"><option value="">全部状态</option>{"".join(f'<option value="{s}">{STATUS_LABEL[s]}</option>' for s in STATUS_ORDER)}</select>
    <select id="f-face"><option value="">全部面向</option>{options('face','')}</select>
    <select id="f-type"><option value="">全部类型</option>{options('type','')}</select>
    <select id="f-owner"><option value="">全部负责人</option>{options('owner','')}</select>
    <input type="search" id="f-q" placeholder="搜索 ID / 标题 / 模块 / 负责人 / 备注">
    <label class="chk" title="只看由现有资料反向推断、尚未确认的任务"><input type="checkbox" id="f-inf">仅看 ⚠ 推断项</label>
    <button class="clear" id="f-clear">清空</button>
    <span class="chip date" id="vis-count"></span>
  </div>
</section>"""

    # ---- kanban ----
    cols = []
    for s in STATUS_ORDER:
        cards = "".join(task_card(t, show_track=True) for t in tasks if t["status"] == s)
        cols.append(
            f'<div class="kan-col" data-col="{s}"><h3><i class="dot {s}"></i>{STATUS_LABEL[s]}'
            f' <span class="chip date">{STATUS_HINT[s]}</span> <span class="n">({c.get(s,0)})</span></h3>'
            f'<div class="kan-list">{cards}</div>'
            f'<div class="kan-empty hide">此列无匹配任务</div></div>'
        )
    kanban = f'<section id="view-kanban" class="view"><div class="kanban">{"".join(cols)}</div></section>'

    # ---- tree ----
    blocks = []
    for tr in tracks:
        sub = [t for t in tasks if t["track"] == tr["id"]]
        sc = {"done": 0, "doing": 0, "blocked": 0, "todo": 0}
        for t in sub:
            sc[t["status"]] += 1
        mods = []
        for m in tr["modules"]:
            mts = [t for t in sub if t["module"] == m["id"]]
            mc = {"done": 0, "doing": 0, "blocked": 0, "todo": 0}
            for t in mts:
                mc[t["status"]] += 1
            mods.append(
                f'<div class="mod"><div class="mod-h"><span class="m-id">{esc(m["id"])}</span>'
                f'{esc(m["name"])}<span class="m-n">{len(mts)} 项 · 完成 {mc["done"]}</span></div>'
                f'<div class="mod-list">{"".join(task_card(t) for t in mts)}</div></div>'
            )
        blocks.append(
            f'<details class="track" open><summary><span class="tr-name">{esc(tr["name"])}</span>'
            f'<span class="tr-kind">{esc(tr.get("kind",""))} · <code>{esc(tr["dir"])}</code> · 负责 {esc(tr.get("owner","—"))}</span>'
            f'<span class="tr-stat">'
            f'<span class="chip" style="color:var(--done)">完成 {sc["done"]}</span>'
            f'<span class="chip" style="color:var(--doing)">进行 {sc["doing"]}</span>'
            f'<span class="chip" style="color:var(--blocked)">阻塞 {sc["blocked"]}</span>'
            f'<span class="chip">未开始 {sc["todo"]}</span>'
            f'</span></summary>{"".join(mods)}</details>'
        )
    tree = f'<section id="view-tree" class="view hide"><div class="tree">{"".join(blocks)}</div></section>'

    # ---- matrix ----
    head = ['<div class="mrow head"><div class="mh">模块（轨 › 模块）</div>']
    for s in STATUS_ORDER:
        head.append(f'<div class="mh" style="justify-content:center"><i class="dot {s}"></i>{STATUS_LABEL[s]}</div>')
    head.append('<div class="mh" style="justify-content:center">完成度</div></div>')
    rows = []
    for tr in tracks:
        rows.append(
            f'<div class="mrow" data-track-head="{esc(tr["id"])}" style="margin-top:10px">'
            f'<div class="mname" style="font-weight:640">{esc(tr["name"])}'
            f'<span class="mt"> · {esc(tr.get("owner","—"))}</span></div>'
            f'<div style="grid-column:span 5;border-bottom:1px solid var(--line)"></div></div>'
        )
        for m in tr["modules"]:
            cells = "".join(
                f'<div class="mcell" data-status="{s}" data-track="{esc(tr["id"])}" data-module="{esc(m["id"])}">0</div>'
                for s in STATUS_ORDER
            )
            rows.append(
                f'<div class="mrow" data-track="{esc(tr["id"])}" data-module="{esc(m["id"])}">'
                f'<div class="mname">{esc(m["name"])} <span class="mt">{esc(m["id"])}</span></div>'
                f'{cells}<div class="mbar"><i style="width:0%"></i></div></div>'
            )
    matrix = (
        '<section id="view-matrix" class="view hide"><div class="matrix">'
        + "".join(head)
        + "".join(rows)
        + '<div class="empty hide" id="matrix-none">没有匹配的模块</div>'
        + '<div class="legend">格子 = 该模块在该状态下的任务数；右侧进度条 = 该模块完成率。</div>'
        + "</div></section>"
    )

    payload = {
        "project": data["project"],
        "tasks": tasks,
    }

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>任务看板 — {esc(data['project'])}</title>
<style>{CSS}</style>
</head>
<body>
<header class="topbar">
  <h1>{esc(data['project'])} · 任务看板</h1>
  <div class="meta">迭代 <b>{esc(data['iteration'])}</b> · 更新 <b>{esc(data['updated'])}</b>
    · 数据源 <b>docs/tasks.yaml</b> · 由 <code style="background:rgba(255,255,255,.16);border-color:transparent;color:#fff">{esc(data['generator'])}</code> 生成（勿手改本页）</div>
</header>
<div class="wrap">
{kpis}
{milestones}
{toolbar}
<main>
{overview(data, tasks)}
{kanban}
{tree}
{matrix}
</main>
</div>
<div class="modal-mask hide" id="modal-mask"><div class="modal" role="dialog" aria-modal="true"></div></div>
<footer>图例：<span class="warn">⚠</span> = 由现有资料反向推断、尚未确认 · 状态四态：{STATUS_LABEL['done']} / {STATUS_LABEL['doing']} / {STATUS_LABEL['blocked']} / {STATUS_LABEL['todo']} · 点击任务卡查看详情 · 离线单文件，可双击打开或直接转发。</footer>
<script>window.__TASKS__ = {json.dumps(payload, ensure_ascii=False)};</script>
<script>{JS}</script>
</body>
</html>
"""


def main() -> int:
    data = load()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(render(data), encoding="utf-8", newline="\n")
    n = len(flatten(data))
    print(f"OK: {n} tasks -> {OUT_FILE.relative_to(REPO_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
