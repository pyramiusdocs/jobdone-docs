#!/usr/bin/env python3
"""
Jobdone Docs 管理介面
- SortableJS 跨層級拖拽排序
- order.json 持久化排序 + 自動同步 mkdocs.yml nav
- 新增、刪除、重命名、Obsidian 連結
"""
import http.server
import json
import os
import re
import shutil
from pathlib import Path

PORT = 8200
PROJECT_DIR = Path(__file__).parent
DOCS_DIR = PROJECT_DIR / "docs"
MKDOCS_YML = PROJECT_DIR / "mkdocs.yml"
ORDER_FILE = PROJECT_DIR / "order.json"
SKIP = {"images", "stylesheets", "javascripts", ".obsidian", "__pycache__", ".trash"}

def load_order():
    return json.loads(ORDER_FILE.read_text("utf-8")) if ORDER_FILE.exists() else {}

def save_order(order):
    ORDER_FILE.write_text(json.dumps(order, ensure_ascii=False, indent=2), "utf-8")

def get_title(fp):
    try:
        for line in open(fp, "r", encoding="utf-8"):
            line = line.strip()
            if line.startswith("# "):
                return line[2:].strip()
            if line and not line.startswith("---"):
                return line[:50]
        return fp.stem
    except:
        return fp.stem

def scan_tree(base, rel=""):
    order = load_order()
    path = base / rel if rel else base
    if not path.is_dir(): return []
    items = []
    for e in path.iterdir():
        n = e.name; er = f"{rel}/{n}" if rel else n
        if n in SKIP or n.startswith("."): continue
        if e.is_dir():
            hi = (e / "index.md").exists()
            items.append({"type":"folder","name":n,"path":er,
                "title":get_title(e/"index.md") if hi else n,
                "hasIndex":hi,"children":scan_tree(base,er)})
        elif e.suffix == ".md" and n != "index.md":
            items.append({"type":"file","name":n,"path":er,
                "title":get_title(e),"size":e.stat().st_size})
    key = rel or "__root__"
    if key in order:
        ol = order[key]
        items.sort(key=lambda x: ol.index(x["name"]) if x["name"] in ol else 9999)
    else:
        items.sort(key=lambda x: (x["type"]!="folder", x["name"]))
    return items

def tree_to_nav(tree, indent=2):
    lines = []
    p = " " * indent
    for it in tree:
        t = it.get("title", it["name"]); path = it["path"]
        if it["type"] == "folder":
            lines.append(f"{p}- {t}:")
            lines.append(f"{p}    - {path}/index.md")
            lines.extend(tree_to_nav(it.get("children",[]), indent+4))
        else:
            lines.append(f"{p}- {t}: {path}")
    return lines

def rebuild_nav():
    tree = scan_tree(DOCS_DIR)
    nav = "\n".join(tree_to_nav(tree))
    yml = MKDOCS_YML.read_text("utf-8")
    # Only replace the nav section (from "nav:" to end of file or next top-level key)
    new_nav = f"nav:\n  - 首頁: index.md\n{nav}\n"
    # Find where nav starts
    nav_start = yml.find("\nnav:")
    if nav_start >= 0:
        yml = yml[:nav_start+1] + new_nav
    else:
        yml += "\n" + new_nav
    MKDOCS_YML.write_text(yml, "utf-8")
    return tree

HTML = r"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<title>Jobdone Docs 管理</title>
<script src="https://cdn.jsdelivr.net/npm/sortablejs@1.15.6/Sortable.min.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f5f7fa;color:#333}
.hd{background:#1a73e8;color:#fff;padding:10px 20px;display:flex;align-items:center;justify-content:space-between}
.hd h1{font-size:16px;font-weight:500}
.hd .acts{display:flex;gap:6px}
.btn{padding:5px 14px;border:none;border-radius:4px;cursor:pointer;font-size:12px;text-decoration:none;display:inline-flex;align-items:center}
.btn-w{background:#fff;color:#1a73e8}.btn-w:hover{background:#e8f0fe}
.btn-d{background:#dc3545;color:#fff}
.btn-g{background:#28a745;color:#fff}
.btn-sm{padding:3px 10px;font-size:11px}
.wrap{display:flex;height:calc(100vh - 44px)}
.side{width:420px;background:#fff;border-right:1px solid #ddd;overflow-y:auto;padding:8px}
.main{flex:1;padding:20px;overflow-y:auto}

/* Tree */
.tree-list{list-style:none;padding-left:0}
.tree-list .tree-list{padding-left:18px}
.tree-node{margin:1px 0}
.node-row{display:flex;align-items:center;padding:3px 6px;cursor:grab;border-radius:3px;font-size:12.5px}
.node-row:hover{background:#e8f0fe}
.node-row.active{background:#d2e3fc}
.node-toggle{width:16px;text-align:center;color:#999;flex-shrink:0;cursor:pointer;font-size:9px;user-select:none}
.node-icon{margin-right:4px;flex-shrink:0}
.node-title{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.node-kids{overflow:hidden;transition:max-height .2s}
.node-kids.collapsed{max-height:0!important}
.sortable-ghost{opacity:.4;background:#d2e3fc}
.sortable-chosen{background:#e8f0fe}

.toast{position:fixed;bottom:16px;right:16px;background:#333;color:#fff;padding:8px 16px;border-radius:6px;font-size:12px;z-index:2000;transition:opacity .3s}.toast.hid{opacity:0;pointer-events:none}
.dlg-ov{position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.4);z-index:1500;display:flex;align-items:center;justify-content:center}
.dlg{background:#fff;border-radius:8px;padding:20px;min-width:340px;box-shadow:0 8px 32px rgba(0,0,0,.2)}
.dlg h3{margin-bottom:12px;font-size:14px}
.dlg input{width:100%;padding:7px 10px;border:1px solid #ddd;border-radius:4px;font-size:13px;margin-bottom:12px}
.dlg .btns{display:flex;gap:6px;justify-content:flex-end}
.df{margin-bottom:10px}.df label{display:block;font-size:11px;color:#888;margin-bottom:3px}
.df input{width:100%;padding:5px 8px;border:1px solid #ddd;border-radius:4px;font-size:12px}
.df .path{font-family:monospace;font-size:11px;color:#999}
</style>
</head>
<body>
<div class="hd">
  <h1>Jobdone Docs 管理</h1>
  <div class="acts">
    <button class="btn btn-g" onclick="saveOrder()">💾 儲存排序</button>
    <button class="btn btn-w" onclick="window.open('http://localhost:8100','_blank')">預覽網站</button>
  </div>
</div>
<div class="wrap">
  <div class="side" id="side"></div>
  <div class="main"><div id="detail">
    <h2 style="font-size:15px">選擇左側項目</h2>
    <p style="color:#888;font-size:12px;margin-top:6px">拖拽調整順序（可跨層級）。點擊展開/收合。右側編輯詳情。</p>
  </div></div>
</div>
<div class="toast hid" id="toast"></div>
<script>
let tree=[];

async function api(action,p={}){
  return (await fetch('/api',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,...p})})).json();
}

async function load(){tree=(await api('tree')).tree;render()}

function render(){
  document.getElementById('side').innerHTML='<ul class="tree-list" id="root-list">'+renderNodes(tree)+'</ul>';
  initSortable(document.getElementById('root-list'));
}

function renderNodes(items){
  let h='';
  for(const it of items){
    const isF=it.type==='folder';
    h+=`<li class="tree-node" data-path="${it.path}" data-name="${it.name}" data-type="${it.type}">
      <div class="node-row" onclick="sel(this,'${esc(it.path)}')" oncontextmenu="ctx(event,'${esc(it.path)}','${it.type}')">
        <span class="node-toggle" onclick="event.stopPropagation();tog(this)">${isF?'▶':''}</span>
        <span class="node-icon">${isF?'📁':'📄'}</span>
        <span class="node-title">${it.title||it.name}</span>
      </div>`;
    if(isF){
      h+=`<div class="node-kids collapsed"><ul class="tree-list">${renderNodes(it.children||[])}</ul></div>`;
    }
    h+='</li>';
  }
  return h;
}

function esc(s){return s.replace(/'/g,"\\'")}

function initSortable(el){
  if(!el)return;
  Sortable.create(el,{
    group:'nested',animation:150,fallbackOnBody:true,swapThreshold:0.65,
    handle:'.node-row',ghostClass:'sortable-ghost',chosenClass:'sortable-chosen',
    onEnd:function(){}  // order is read on save
  });
  // Init all nested lists too
  el.querySelectorAll('.tree-list').forEach(ul=>{
    if(ul===el)return;
    Sortable.create(ul,{
      group:'nested',animation:150,fallbackOnBody:true,swapThreshold:0.65,
      handle:'.node-row',ghostClass:'sortable-ghost',chosenClass:'sortable-chosen',
    });
  });
}

function tog(el){
  const li=el.closest('.tree-node');
  const kids=li.querySelector('.node-kids');
  if(!kids)return;
  kids.classList.toggle('collapsed');
  el.textContent=kids.classList.contains('collapsed')?'▶':'▼';
}

function sel(el,path){
  document.querySelectorAll('.node-row.active').forEach(r=>r.classList.remove('active'));
  el.classList.add('active');
  const it=findItem(tree,path);if(!it)return;
  const isF=it.type==='folder';
  const obsLink=`obsidian://open?vault=docs&file=${encodeURIComponent(isF?it.path+'/index':it.path.replace('.md',''))}`;
  document.getElementById('detail').innerHTML=`
    <h2 style="font-size:15px">${isF?'📁':'📄'} ${it.title||it.name}</h2>
    <div class="df"><label>路徑</label><div class="path">${it.path}</div></div>
    <div class="df"><label>標題</label><input value="${(it.title||'').replace(/"/g,'&quot;')}" onchange="updTitle('${esc(it.path)}',this.value)"></div>
    <div style="margin-top:12px;display:flex;gap:6px;flex-wrap:wrap">
      <a class="btn btn-sm btn-w" style="border:1px solid #1a73e8" href="${obsLink}">在 Obsidian 編輯</a>
      <button class="btn btn-sm btn-w" style="border:1px solid #ddd" onclick="promptRename('${esc(it.path)}','${esc(it.name)}')">重命名</button>
      <button class="btn btn-sm btn-d" onclick="delItem('${esc(it.path)}')">刪除</button>
    </div>`;
}

function findItem(items,path){
  for(const it of items){if(it.path===path)return it;if(it.children){const f=findItem(it.children,path);if(f)return f}}return null;
}

// ─── Save order by reading current DOM tree ───
async function saveOrder(){
  const order=readDomOrder(document.getElementById('root-list'),'');
  const d=await api('save_order',{order});
  if(d.ok)toast('排序已儲存，Nav 已更新');
  else toast('錯誤: '+(d.error||'unknown'));
}

function readDomOrder(ul,parentPath){
  const result={};
  const names=[];
  for(const li of ul.children){
    if(li.tagName!=='LI')continue;
    const name=li.dataset.name;
    const path=li.dataset.path;
    names.push(name);
    const childUl=li.querySelector(':scope > .node-kids > .tree-list');
    if(childUl){
      const childOrder=readDomOrder(childUl,path);
      Object.assign(result,childOrder);
    }
  }
  const key=parentPath||'__root__';
  if(names.length)result[key]=names;
  return result;
}

// ─── Context menu ─────────────────
function ctx(e,path,type){
  e.preventDefault();
  document.querySelectorAll('.ctx-menu').forEach(m=>m.remove());
  const m=document.createElement('div');m.className='ctx-menu';
  m.style.cssText=`position:fixed;left:${e.clientX}px;top:${e.clientY}px;background:#fff;border:1px solid #ddd;border-radius:6px;box-shadow:0 4px 12px rgba(0,0,0,.15);padding:4px 0;z-index:1000;min-width:150px`;
  const add=(label,fn,danger)=>{
    const d=document.createElement('div');
    d.style.cssText=`padding:5px 14px;cursor:pointer;font-size:12px;${danger?'color:#dc3545':''}`;
    d.textContent=label;d.onmouseover=()=>d.style.background='#e8f0fe';d.onmouseout=()=>d.style.background='';
    d.onclick=()=>{m.remove();fn()};m.appendChild(d);
  };
  if(type==='folder'){
    add('新增頁面',()=>promptCreate(path,'file'));
    add('新增子資料夾',()=>promptCreate(path,'folder'));
    const sep=document.createElement('div');sep.style.cssText='border-top:1px solid #eee;margin:3px 0';m.appendChild(sep);
  }
  add('重命名',()=>{const it=findItem(tree,path);promptRename(path,it?it.name:'')});
  add('刪除',()=>delItem(path),true);
  document.body.appendChild(m);
  setTimeout(()=>document.addEventListener('click',()=>m.remove(),{once:true}),10);
}

// ─── Actions ──────────────────
function promptCreate(folder,type){
  showDlg(type==='folder'?'新增資料夾':'新增頁面','名稱',async n=>{
    if(!n)return;
    const d=type==='folder'?await api('create_folder',{parent:folder,name:n}):await api('create_page',{folder,name:n,title:n});
    d.ok?toast('已建立'):toast('錯誤: '+d.error);load();
  });
}
function promptRename(path,cur){
  showDlg('重命名','新名稱',async n=>{
    if(!n)return;const d=await api('rename',{path,newName:n});
    d.ok?toast('已重命名'):toast('錯誤: '+d.error);load();
  },cur.replace('.md',''));
}
async function delItem(path){
  if(!confirm('確定刪除 '+path+'？'))return;
  const d=await api('delete',{path});d.ok?toast(d.message):toast('錯誤: '+d.error);load();
}
async function updTitle(path,t){
  const d=await api('update_title',{path,title:t});if(d.ok)toast('已更新');load();
}

function showDlg(title,ph,cb,dv=''){
  const o=document.createElement('div');o.className='dlg-ov';
  o.innerHTML=`<div class="dlg"><h3>${title}</h3><input id="di" placeholder="${ph}" value="${dv}"><div class="btns"><button class="btn" onclick="this.closest('.dlg-ov').remove()">取消</button><button class="btn btn-w" style="border:1px solid #1a73e8" id="dok">確定</button></div></div>`;
  document.body.appendChild(o);const inp=o.querySelector('#di');inp.focus();inp.select();
  const go=()=>{cb(inp.value);o.remove()};o.querySelector('#dok').onclick=go;inp.onkeydown=e=>{if(e.key==='Enter')go()};
}
function toast(m){const e=document.getElementById('toast');e.textContent=m;e.classList.remove('hid');setTimeout(()=>e.classList.add('hid'),2500)}

load();
</script>
</body>
</html>"""

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self,*a):pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type","text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(HTML.encode())

    def do_POST(self):
        if self.path!="/api":
            self.send_response(404);self.end_headers();return
        body=json.loads(self.rfile.read(int(self.headers.get("Content-Length",0)))) if int(self.headers.get("Content-Length",0))>0 else {}
        action=body.get("action","")
        result={}

        if action=="tree":
            result={"tree":scan_tree(DOCS_DIR)}

        elif action=="save_order":
            order=body.get("order",{})
            save_order(order)
            rebuild_nav()
            result={"ok":True}

        elif action=="rename":
            src=DOCS_DIR/body["path"]
            if not src.exists():result={"ok":False,"error":"不存在"}
            else:
                nn=body["newName"]
                dst=src.parent/(nn if src.is_dir() else (nn if nn.endswith(".md") else nn+".md"))
                if dst.exists():result={"ok":False,"error":"已存在"}
                else:shutil.move(str(src),str(dst));rebuild_nav();result={"ok":True}

        elif action=="create_page":
            n=body["name"];
            if not n.endswith(".md"):n+=".md"
            fp=DOCS_DIR/body.get("folder","")/n if body.get("folder") else DOCS_DIR/n
            fp.parent.mkdir(parents=True,exist_ok=True)
            if fp.exists():result={"ok":False,"error":"已存在"}
            else:fp.write_text(f"# {body.get('title',n.replace('.md',''))}\n\n","utf-8");rebuild_nav();result={"ok":True}

        elif action=="create_folder":
            f=DOCS_DIR/body.get("parent","")/body["name"] if body.get("parent") else DOCS_DIR/body["name"]
            if f.exists():result={"ok":False,"error":"已存在"}
            else:f.mkdir(parents=True,exist_ok=True);(f/"index.md").write_text(f"# {body['name']}\n\n","utf-8");rebuild_nav();result={"ok":True}

        elif action=="delete":
            src=DOCS_DIR/body["path"]
            if not src.exists():result={"ok":False,"error":"不存在"}
            else:
                trash=PROJECT_DIR/".trash";trash.mkdir(exist_ok=True)
                dst=trash/src.name;c=1
                while dst.exists():dst=trash/f"{src.stem}_{c}{src.suffix}";c+=1
                shutil.move(str(src),str(dst));rebuild_nav()
                result={"ok":True,"message":f"已移至 .trash/{dst.name}"}

        elif action=="update_title":
            fp=DOCS_DIR/body["path"]
            if not fp.exists():fp=DOCS_DIR/body["path"]/"index.md"
            if fp.exists():
                c=fp.read_text("utf-8")
                c=re.sub(r"^# .+",f"# {body['title']}",c,count=1,flags=re.MULTILINE)
                fp.write_text(c,"utf-8");rebuild_nav();result={"ok":True}
            else:result={"ok":False,"error":"不存在"}

        self.send_response(200)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(result,ensure_ascii=False).encode())

if __name__=="__main__":
    print(f"📚 Jobdone Docs 管理 → http://localhost:{PORT}")
    http.server.HTTPServer(("",PORT),Handler).serve_forever()
