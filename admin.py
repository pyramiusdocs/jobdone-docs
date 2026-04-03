#!/usr/bin/env python3
"""
Jobdone Docs 管理介面
- 樹狀目錄拖拽排序（上下移動 + 跨資料夾移動）
- 排序存在 order.json，自動同步到 mkdocs.yml nav
- 新增、刪除、重命名

用法: python3 admin.py
介面: http://localhost:8200
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

SKIP_DIRS = {"images", "stylesheets", "javascripts", ".obsidian", "__pycache__"}

# ─── Order 管理 ──────────────────────────────────────

def load_order():
    if ORDER_FILE.exists():
        return json.loads(ORDER_FILE.read_text("utf-8"))
    return {}

def save_order(order):
    ORDER_FILE.write_text(json.dumps(order, ensure_ascii=False, indent=2), "utf-8")

# ─── 檔案樹 ─────────────────────────────────────────

def get_title(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("# "):
                    return line[2:].strip()
                if line and not line.startswith("---"):
                    return line[:50]
        return filepath.stem
    except:
        return filepath.stem

def scan_tree(base, rel=""):
    """掃描目錄，用 order.json 排序。"""
    order = load_order()
    path = base / rel if rel else base
    if not path.is_dir():
        return []

    # 收集所有項目
    items = []
    for entry in path.iterdir():
        name = entry.name
        entry_rel = f"{rel}/{name}" if rel else name
        if name in SKIP_DIRS or name.startswith("."):
            continue
        if entry.is_dir():
            children = scan_tree(base, entry_rel)
            has_index = (entry / "index.md").exists()
            items.append({
                "type": "folder", "name": name, "path": entry_rel,
                "title": get_title(entry / "index.md") if has_index else name,
                "hasIndex": has_index, "children": children
            })
        elif entry.suffix == ".md" and name != "index.md":
            items.append({
                "type": "file", "name": name, "path": entry_rel,
                "title": get_title(entry), "size": entry.stat().st_size
            })

    # 套用 order.json 排序
    dir_key = rel or "__root__"
    if dir_key in order:
        ordered_names = order[dir_key]
        def sort_key(item):
            n = item["name"]
            if n in ordered_names:
                return ordered_names.index(n)
            return 9999
        items.sort(key=sort_key)
    else:
        items.sort(key=lambda x: (not x["type"] == "folder", x["name"]))

    return items

# ─── 排序操作 ────────────────────────────────────────

def reorder(dir_path, ordered_names):
    """設定某個目錄的排序。"""
    order = load_order()
    key = dir_path or "__root__"
    order[key] = ordered_names
    save_order(order)

# ─── Nav 生成 ────────────────────────────────────────

def tree_to_nav_yaml(tree, indent=2, parent_path=""):
    lines = []
    prefix = " " * indent
    for item in tree:
        title = item.get("title", item["name"])
        path = item["path"]
        if item["type"] == "folder":
            lines.append(f"{prefix}- {title}:")
            lines.append(f"{prefix}    - 總覽: {path}/index.md")
            lines.extend(tree_to_nav_yaml(item.get("children", []), indent + 4, path))
        else:
            lines.append(f"{prefix}- {title}: {path}")
    return lines

def rebuild_mkdocs_nav(tree):
    nav_yaml = "\n".join(tree_to_nav_yaml(tree))
    yml = MKDOCS_YML.read_text("utf-8")
    new_nav = f"nav:\n  - 首頁: index.md\n{nav_yaml}\n"
    yml = re.sub(r"nav:.*", new_nav, yml, flags=re.DOTALL)
    MKDOCS_YML.write_text(yml, "utf-8")
    return nav_yaml.count("\n") + 1

# ─── 檔案操作 ────────────────────────────────────────

def rename_item(old_path, new_name):
    src = DOCS_DIR / old_path
    if not src.exists(): return False, "不存在"
    parent = src.parent
    dst = parent / new_name if src.is_dir() else parent / (new_name if new_name.endswith(".md") else new_name + ".md")
    if dst.exists(): return False, "目標已存在"
    shutil.move(str(src), str(dst))
    return True, str(dst.relative_to(DOCS_DIR))

def move_item(src_path, dst_folder):
    src = DOCS_DIR / src_path
    dst_dir = DOCS_DIR / dst_folder if dst_folder else DOCS_DIR
    if not src.exists(): return False, "不存在"
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / src.name
    if dst.exists(): return False, "目標已存在"
    shutil.move(str(src), str(dst))
    return True, str(dst.relative_to(DOCS_DIR))

def create_page(folder, name, title=""):
    if not name.endswith(".md"): name += ".md"
    fp = DOCS_DIR / folder / name if folder else DOCS_DIR / name
    fp.parent.mkdir(parents=True, exist_ok=True)
    if fp.exists(): return False, "已存在"
    title = title or name.replace(".md", "")
    fp.write_text(f"# {title}\n\n", "utf-8")
    return True, str(fp.relative_to(DOCS_DIR))

def create_folder(parent, name):
    folder = DOCS_DIR / parent / name if parent else DOCS_DIR / name
    if folder.exists(): return False, "已存在"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "index.md").write_text(f"# {name}\n\n", "utf-8")
    return True, str(folder.relative_to(DOCS_DIR))

def delete_item(path):
    src = DOCS_DIR / path
    if not src.exists(): return False, "不存在"
    trash = PROJECT_DIR / ".trash"
    trash.mkdir(exist_ok=True)
    dst = trash / src.name
    c = 1
    while dst.exists():
        dst = trash / f"{src.stem}_{c}{src.suffix}"; c += 1
    shutil.move(str(src), str(dst))
    return True, f"已移至 .trash/{dst.name}"

# ─── HTTP ────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<title>Jobdone Docs 管理</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f5f7fa;color:#333}
.header{background:#1a73e8;color:#fff;padding:10px 20px;display:flex;align-items:center;justify-content:space-between}
.header h1{font-size:16px;font-weight:500}
.header .actions{display:flex;gap:6px}
.btn{padding:5px 14px;border:none;border-radius:4px;cursor:pointer;font-size:12px}
.btn-w{background:#fff;color:#1a73e8}.btn-w:hover{background:#e8f0fe}
.btn-d{background:#dc3545;color:#fff}
.btn-sm{padding:3px 8px;font-size:11px}
.wrap{display:flex;height:calc(100vh - 44px)}
.side{width:400px;background:#fff;border-right:1px solid #ddd;overflow-y:auto;padding:8px 0}
.main{flex:1;padding:20px;overflow-y:auto}

.t-item{user-select:none}
.t-row{display:flex;align-items:center;padding:3px 6px;cursor:pointer;border-radius:3px;margin:1px 6px;font-size:12px;position:relative}
.t-row:hover{background:#e8f0fe}
.t-row.active{background:#d2e3fc}
.t-row.drop-above::before{content:'';position:absolute;top:-1px;left:0;right:0;height:2px;background:#1a73e8}
.t-row.drop-inside{background:#c6d9f7}
.t-row.drop-below::after{content:'';position:absolute;bottom:-1px;left:0;right:0;height:2px;background:#1a73e8}
.t-tog{width:18px;text-align:center;color:#999;flex-shrink:0;font-size:10px}
.t-ico{margin-right:4px;flex-shrink:0;font-size:12px}
.t-ttl{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.t-arrows{display:flex;gap:2px;margin-left:4px;opacity:0}
.t-row:hover .t-arrows{opacity:1}
.t-arr{cursor:pointer;font-size:10px;color:#888;padding:0 2px}
.t-arr:hover{color:#1a73e8}
.t-kids{padding-left:14px}
.t-kids.collapsed{display:none}

.ctx{position:fixed;background:#fff;border:1px solid #ddd;border-radius:6px;box-shadow:0 4px 12px rgba(0,0,0,.15);padding:4px 0;z-index:1000;min-width:150px}
.ctx-i{padding:5px 14px;cursor:pointer;font-size:12px}.ctx-i:hover{background:#e8f0fe}
.ctx-s{border-top:1px solid #eee;margin:3px 0}

.toast{position:fixed;bottom:16px;right:16px;background:#333;color:#fff;padding:8px 16px;border-radius:6px;font-size:12px;z-index:2000;transition:opacity .3s}
.toast.hidden{opacity:0;pointer-events:none}

.dlg-ov{position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.4);z-index:1500;display:flex;align-items:center;justify-content:center}
.dlg{background:#fff;border-radius:8px;padding:20px;min-width:340px;box-shadow:0 8px 32px rgba(0,0,0,.2)}
.dlg h3{margin-bottom:12px;font-size:14px}
.dlg input{width:100%;padding:7px 10px;border:1px solid #ddd;border-radius:4px;font-size:13px;margin-bottom:12px}
.dlg .btns{display:flex;gap:6px;justify-content:flex-end}

.detail h2{font-size:15px;margin-bottom:12px}
.df{margin-bottom:10px}.df label{display:block;font-size:11px;color:#888;margin-bottom:3px}
.df input{width:100%;padding:5px 8px;border:1px solid #ddd;border-radius:4px;font-size:12px}
.df .path{font-family:monospace;font-size:11px;color:#999}
</style>
</head>
<body>
<div class="header">
  <h1>Jobdone Docs 管理</h1>
  <div class="actions">
    <button class="btn btn-w" onclick="rebuildNav()">重建 Nav</button>
    <button class="btn btn-w" onclick="window.open('http://localhost:8100','_blank')">預覽網站</button>
  </div>
</div>
<div class="wrap">
  <div class="side" id="side"></div>
  <div class="main"><div class="detail" id="detail">
    <h2>選擇左側項目</h2>
    <p style="color:#888;font-size:12px;margin-top:6px">
      上下箭頭調整順序。拖拽移動到資料夾。右鍵更多操作。<br>
      點擊「在 Obsidian 編輯」可直接開啟對應檔案。
    </p>
  </div></div>
</div>
<div class="toast hidden" id="toast"></div>
<script>
let tree=[],sel=null,ctx=null;

async function api(action,p={}){
  const r=await fetch('/api',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,...p})});
  return r.json();
}
async function loadTree(){tree=(await api('tree')).tree;render()}
async function rebuildNav(){const d=await api('rebuild_nav');toast('Nav 已重建 ('+d.count+' 項)')}

function render(){document.getElementById('side').innerHTML=renderItems(tree,'')}

function renderItems(items,parentPath){
  let h='';
  for(let i=0;i<items.length;i++){
    const it=items[i],isF=it.type==='folder',icon=isF?'📁':'📄';
    const tog=isF?'<span class="t-tog">▶</span>':'<span class="t-tog"></span>';
    const upBtn=i>0?`<span class="t-arr" onclick="event.stopPropagation();moveUp('${parentPath}','${it.name}')">▲</span>`:'';
    const dnBtn=i<items.length-1?`<span class="t-arr" onclick="event.stopPropagation();moveDn('${parentPath}','${it.name}')">▼</span>`:'';
    h+=`<div class="t-item" data-path="${it.path}" data-type="${it.type}">
      <div class="t-row" draggable="true"
        onclick="selItem(this,'${it.path}')"
        oncontextmenu="showCtx(event,'${it.path}','${it.type}','${parentPath}')"
        ondragstart="dStart(event,'${it.path}')"
        ondragover="dOver(event)" ondragleave="dLeave(event)"
        ondrop="dDrop(event,'${it.path}','${it.type}','${parentPath}')">
        ${tog}<span class="t-ico">${icon}</span><span class="t-ttl">${it.title||it.name}</span>
        <span class="t-arrows">${upBtn}${dnBtn}</span>
      </div>`;
    if(isF&&it.children&&it.children.length)
      h+=`<div class="t-kids collapsed">${renderItems(it.children,it.path)}</div>`;
    h+='</div>';
  }
  return h;
}

function selItem(el,path){
  const item=el.closest('.t-item'),kids=item.querySelector('.t-kids');
  if(kids){kids.classList.toggle('collapsed');const t=el.querySelector('.t-tog');if(t)t.textContent=kids.classList.contains('collapsed')?'▶':'▼'}
  document.querySelectorAll('.t-row.active').forEach(r=>r.classList.remove('active'));
  el.classList.add('active');sel=path;showDetail(path);
}

function showDetail(path){
  const it=findItem(tree,path);if(!it)return;
  const isF=it.type==='folder';
  document.getElementById('detail').innerHTML=`
    <h2>${isF?'📁':'📄'} ${it.title||it.name}</h2>
    <div class="df"><label>路徑</label><div class="path">${it.path}</div></div>
    <div class="df"><label>標題</label><input value="${(it.title||'').replace(/"/g,'&quot;')}" onchange="updTitle('${it.path}',this.value)"></div>
    <div style="margin-top:12px;display:flex;gap:6px;flex-wrap:wrap">
      <a class="btn btn-sm btn-w" style="border:1px solid #1a73e8;text-decoration:none" href="obsidian://open?vault=docs&file=${encodeURIComponent(isF?it.path+'/index':it.path.replace('.md',''))}" target="_blank">在 Obsidian 編輯</a>
      <button class="btn btn-sm btn-w" style="border:1px solid #ddd" onclick="promptRename('${it.path}','${it.name}')">重命名</button>
      <button class="btn btn-sm btn-d" onclick="delItem('${it.path}')">刪除</button>
    </div>`;
}

function findItem(items,path){
  for(const it of items){if(it.path===path)return it;if(it.children){const f=findItem(it.children,path);if(f)return f}}return null;
}

// ─── Reorder ──────────────────
async function moveUp(parentPath,name){await api('move_up',{dir:parentPath,name});loadTree()}
async function moveDn(parentPath,name){await api('move_down',{dir:parentPath,name});loadTree()}

// ─── Drag ─────────────────────
let dragPath=null;
function dStart(e,path){dragPath=path;e.dataTransfer.effectAllowed='move'}
function dOver(e){
  e.preventDefault();
  const row=e.currentTarget,rect=row.getBoundingClientRect();
  const y=(e.clientY-rect.top)/rect.height;
  row.classList.remove('drop-above','drop-inside','drop-below');
  if(y<0.25)row.classList.add('drop-above');
  else if(y>0.75)row.classList.add('drop-below');
  else row.classList.add('drop-inside');
}
function dLeave(e){e.currentTarget.classList.remove('drop-above','drop-inside','drop-below')}
async function dDrop(e,targetPath,targetType,targetParent){
  e.preventDefault();const row=e.currentTarget;
  const mode=row.classList.contains('drop-above')?'above':row.classList.contains('drop-below')?'below':'inside';
  row.classList.remove('drop-above','drop-inside','drop-below');
  if(!dragPath||dragPath===targetPath)return;
  if(mode==='inside'&&targetType==='folder'){
    await api('move',{src:dragPath,dst:targetPath});
  }else{
    await api('move_near',{src:dragPath,target:targetPath,position:mode,targetParent});
  }
  dragPath=null;loadTree();
}

// ─── Context Menu ─────────────
function showCtx(e,path,type,parentPath){
  e.preventDefault();hideCtx();
  const m=document.createElement('div');m.className='ctx';m.style.left=e.clientX+'px';m.style.top=e.clientY+'px';
  const items=[];
  if(type==='folder'){
    items.push({l:'新增頁面',a:()=>promptCreate(path,'file')});
    items.push({l:'新增子資料夾',a:()=>promptCreate(path,'folder')});
    items.push({sep:1});
  }
  items.push({l:'重命名',a:()=>{const it=findItem(tree,path);promptRename(path,it?it.name:'')}});
  items.push({l:'移動到...',a:()=>promptMove(path)});
  items.push({sep:1});
  items.push({l:'刪除',a:()=>delItem(path),d:1});
  for(const i of items){
    if(i.sep){m.innerHTML+='<div class="ctx-s"></div>';continue}
    const d=document.createElement('div');d.className='ctx-i';if(i.d)d.style.color='#dc3545';
    d.textContent=i.l;d.onclick=()=>{hideCtx();i.a()};m.appendChild(d);
  }
  document.body.appendChild(m);ctx=m;
  setTimeout(()=>document.addEventListener('click',hideCtx,{once:1}),10);
}
function hideCtx(){if(ctx){ctx.remove();ctx=null}}

// ─── Actions ──────────────────
function promptCreate(folder,type){
  showDlg(type==='folder'?'新增資料夾':'新增頁面','名稱',async n=>{
    if(!n)return;
    const d=type==='folder'?await api('create_folder',{parent:folder,name:n}):await api('create_page',{folder,name:n,title:n});
    d.ok?toast('已建立'):toast('錯誤: '+d.error);loadTree();
  });
}
function promptRename(path,cur){
  showDlg('重命名','新名稱',async n=>{
    if(!n)return;const d=await api('rename',{path,newName:n});
    d.ok?toast('已重命名'):toast('錯誤: '+d.error);loadTree();
  },cur.replace('.md',''));
}
function promptMove(path){
  showDlg('移動到','目標資料夾（空白=根目錄）',async d2=>{
    const d=await api('move',{src:path,dst:d2||''});
    d.ok?toast('已移動'):toast('錯誤: '+d.error);loadTree();
  });
}
async function delItem(path){
  if(!confirm('確定刪除 '+path+'？'))return;
  const d=await api('delete',{path});d.ok?toast(d.message):toast('錯誤: '+d.error);loadTree();
}
async function updTitle(path,t){
  const d=await api('update_title',{path,title:t});if(d.ok)toast('已更新');loadTree();
}

function showDlg(title,ph,cb,dv=''){
  const o=document.createElement('div');o.className='dlg-ov';
  o.innerHTML=`<div class="dlg"><h3>${title}</h3><input id="di" placeholder="${ph}" value="${dv}"><div class="btns"><button class="btn" onclick="this.closest('.dlg-ov').remove()">取消</button><button class="btn btn-w" style="border:1px solid #1a73e8" id="dok">確定</button></div></div>`;
  document.body.appendChild(o);const inp=o.querySelector('#di');inp.focus();inp.select();
  const go=()=>{cb(inp.value);o.remove()};
  o.querySelector('#dok').onclick=go;inp.onkeydown=e=>{if(e.key==='Enter')go()};
}
function toast(m){const e=document.getElementById('toast');e.textContent=m;e.classList.remove('hidden');setTimeout(()=>e.classList.add('hidden'),2500)}

loadTree();
</script>
</body>
</html>"""

# ─── Server ──────────────────────────────────────────

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(HTML.encode())

    def do_POST(self):
        if self.path != "/api":
            self.send_response(404); self.end_headers(); return

        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)))) if int(self.headers.get("Content-Length", 0)) > 0 else {}
        action = body.get("action", "")
        result = {}

        if action == "tree":
            result = {"tree": scan_tree(DOCS_DIR)}

        elif action == "rebuild_nav":
            tree = scan_tree(DOCS_DIR)
            count = rebuild_mkdocs_nav(tree)
            result = {"ok": True, "count": count}

        elif action == "move_up" or action == "move_down":
            dir_path = body.get("dir", "")
            name = body["name"]
            order = load_order()
            key = dir_path or "__root__"

            # Get current items in this directory
            d = DOCS_DIR / dir_path if dir_path else DOCS_DIR
            names = []
            for e in d.iterdir():
                if e.name in SKIP_DIRS or e.name.startswith(".") or (e.suffix == ".md" and e.name == "index.md"):
                    continue
                if e.is_dir() or e.suffix == ".md":
                    names.append(e.name)

            # Apply existing order
            if key in order:
                ordered = [n for n in order[key] if n in names]
                remaining = [n for n in names if n not in ordered]
                names = ordered + remaining
            else:
                names.sort()

            if name in names:
                idx = names.index(name)
                if action == "move_up" and idx > 0:
                    names[idx], names[idx-1] = names[idx-1], names[idx]
                elif action == "move_down" and idx < len(names) - 1:
                    names[idx], names[idx+1] = names[idx+1], names[idx]

            order[key] = names
            save_order(order)
            # Auto rebuild nav
            tree = scan_tree(DOCS_DIR)
            rebuild_mkdocs_nav(tree)
            result = {"ok": True}

        elif action == "move_near":
            # Move src near target (above/below)
            src_path = body["src"]
            target_path = body["target"]
            position = body["position"]  # "above" or "below"
            target_parent = body.get("targetParent", "")

            src = DOCS_DIR / src_path
            if not src.exists():
                result = {"ok": False, "error": "不存在"}
            else:
                # Move file to target's parent directory
                dst_dir = DOCS_DIR / target_parent if target_parent else DOCS_DIR
                dst = dst_dir / src.name
                if src != dst:
                    if dst.exists():
                        result = {"ok": False, "error": "目標已存在"}
                    else:
                        dst_dir.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(src), str(dst))

                # Update order
                order = load_order()
                key = target_parent or "__root__"
                d = DOCS_DIR / target_parent if target_parent else DOCS_DIR
                names = []
                for e in d.iterdir():
                    if e.name in SKIP_DIRS or e.name.startswith(".") or (e.suffix == ".md" and e.name == "index.md"):
                        continue
                    if e.is_dir() or e.suffix == ".md":
                        names.append(e.name)
                if key in order:
                    ordered = [n for n in order[key] if n in names]
                    remaining = [n for n in names if n not in ordered]
                    names = ordered + remaining
                else:
                    names.sort()

                # Insert near target
                target_name = Path(target_path).name
                src_name = src.name
                if src_name in names:
                    names.remove(src_name)
                if target_name in names:
                    idx = names.index(target_name)
                    if position == "below":
                        idx += 1
                    names.insert(idx, src_name)
                else:
                    names.append(src_name)

                order[key] = names
                save_order(order)
                tree = scan_tree(DOCS_DIR)
                rebuild_mkdocs_nav(tree)
                result = {"ok": True}

        elif action == "rename":
            ok, msg = rename_item(body["path"], body["newName"])
            result = {"ok": ok, "error": msg if not ok else None}
            if ok:
                tree = scan_tree(DOCS_DIR); rebuild_mkdocs_nav(tree)

        elif action == "move":
            ok, msg = move_item(body["src"], body["dst"])
            result = {"ok": ok, "error": msg if not ok else None}
            if ok:
                tree = scan_tree(DOCS_DIR); rebuild_mkdocs_nav(tree)

        elif action == "create_page":
            ok, msg = create_page(body.get("folder", ""), body["name"], body.get("title", ""))
            result = {"ok": ok, "error": msg if not ok else None}
            if ok:
                tree = scan_tree(DOCS_DIR); rebuild_mkdocs_nav(tree)

        elif action == "create_folder":
            ok, msg = create_folder(body.get("parent", ""), body["name"])
            result = {"ok": ok, "error": msg if not ok else None}
            if ok:
                tree = scan_tree(DOCS_DIR); rebuild_mkdocs_nav(tree)

        elif action == "delete":
            ok, msg = delete_item(body["path"])
            result = {"ok": ok, "message": msg, "error": msg if not ok else None}
            if ok:
                tree = scan_tree(DOCS_DIR); rebuild_mkdocs_nav(tree)

        elif action == "update_title":
            path = body["path"]
            title = body["title"]
            fp = DOCS_DIR / path
            if not fp.exists():
                fp = DOCS_DIR / path / "index.md"
            if fp.exists():
                content = fp.read_text("utf-8")
                content = re.sub(r"^# .+", f"# {title}", content, count=1, flags=re.MULTILINE)
                fp.write_text(content, "utf-8")
                result = {"ok": True}
                tree = scan_tree(DOCS_DIR); rebuild_mkdocs_nav(tree)
            else:
                result = {"ok": False, "error": "不存在"}

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(result, ensure_ascii=False).encode())

if __name__ == "__main__":
    print(f"📚 Jobdone Docs 管理介面 → http://localhost:{PORT}")
    http.server.HTTPServer(("", PORT), Handler).serve_forever()
