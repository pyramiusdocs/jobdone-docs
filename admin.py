#!/usr/bin/env python3
"""
Jobdone Docs 管理介面
- 樹狀目錄編輯（拖拽排序、新增、刪除、重命名）
- 自動更新 mkdocs.yml nav
- 與 Obsidian 共用同一份 docs/ 檔案

用法: python3 admin.py
介面: http://localhost:8200
"""
import http.server
import json
import os
import re
import shutil
import urllib.parse
from pathlib import Path

PORT = 8200
PROJECT_DIR = Path(__file__).parent
DOCS_DIR = PROJECT_DIR / "docs"
MKDOCS_YML = PROJECT_DIR / "mkdocs.yml"

# ─── 檔案樹 ─────────────────────────────────────────

def scan_tree(base, rel=""):
    """掃描 docs/ 目錄，回傳樹狀結構。"""
    items = []
    path = base / rel if rel else base

    if not path.is_dir():
        return items

    entries = sorted(path.iterdir(), key=lambda e: (not e.is_dir(), e.name))

    for entry in entries:
        name = entry.name
        entry_rel = f"{rel}/{name}" if rel else name

        # 跳過非文件目錄
        if name in ("images", "stylesheets", "javascripts", ".obsidian", "__pycache__"):
            continue

        if entry.is_dir():
            children = scan_tree(base, entry_rel)
            has_index = (entry / "index.md").exists()
            items.append({
                "type": "folder",
                "name": name,
                "path": entry_rel,
                "title": get_title(entry / "index.md") if has_index else name,
                "hasIndex": has_index,
                "children": children
            })
        elif entry.suffix == ".md":
            if name == "index.md":
                continue  # 已由父資料夾處理
            items.append({
                "type": "file",
                "name": name,
                "path": entry_rel,
                "title": get_title(entry),
                "size": entry.stat().st_size
            })

    return items


def get_title(filepath):
    """從 .md 檔案取得標題（第一行 # 開頭）。"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("# "):
                    return line[2:].strip()
                if line and not line.startswith("---"):
                    return line[:50]
        return filepath.stem
    except Exception:
        return filepath.stem


# ─── Nav 生成 ────────────────────────────────────────

def tree_to_nav(tree, parent_path=""):
    """將樹狀結構轉成 mkdocs.yml nav 格式。"""
    lines = []
    for item in tree:
        path = item["path"]
        title = item.get("title", item["name"])

        if item["type"] == "folder":
            lines.append({"title": title, "children": [], "index": f"{path}/index.md"})
            child_nav = tree_to_nav(item.get("children", []), path)
            lines[-1]["children"] = child_nav
        else:
            lines.append({"title": title, "path": path})

    return lines


def nav_to_yaml(nav, indent=2):
    """將 nav 結構轉成 YAML 字串。"""
    result = []

    def write(items, level):
        prefix = " " * (indent * level)
        for item in items:
            title = item["title"]
            if "children" in item:
                result.append(f"{prefix}- {title}:")
                if item.get("index"):
                    result.append(f"{prefix}  - 總覽: {item['index']}")
                write(item["children"], level + 1)
            else:
                result.append(f"{prefix}- {title}: {item['path']}")

    write(nav, 1)
    return "\n".join(result)


def rebuild_mkdocs_nav(tree):
    """重建 mkdocs.yml 的 nav 區段。"""
    nav = tree_to_nav(tree)
    nav_yaml = nav_to_yaml(nav)

    yml = MKDOCS_YML.read_text(encoding="utf-8")

    # 替換 nav: 開始到檔案結尾
    new_nav = f"nav:\n  - 首頁: index.md\n{nav_yaml}\n"
    yml = re.sub(r"nav:.*", new_nav, yml, flags=re.DOTALL)

    MKDOCS_YML.write_text(yml, encoding="utf-8")
    return len(nav)


# ─── 檔案操作 ────────────────────────────────────────

def rename_item(old_path, new_name):
    """重命名檔案或資料夾。"""
    src = DOCS_DIR / old_path
    if not src.exists():
        return False, "檔案不存在"

    parent = src.parent
    if src.is_dir():
        dst = parent / new_name
    else:
        dst = parent / (new_name + ".md" if not new_name.endswith(".md") else new_name)

    if dst.exists():
        return False, "目標已存在"

    shutil.move(str(src), str(dst))
    return True, str(dst.relative_to(DOCS_DIR))


def move_item(src_path, dst_folder):
    """移動檔案或資料夾到另一個目錄。"""
    src = DOCS_DIR / src_path
    dst_dir = DOCS_DIR / dst_folder if dst_folder else DOCS_DIR

    if not src.exists():
        return False, "來源不存在"
    if not dst_dir.is_dir():
        dst_dir.mkdir(parents=True, exist_ok=True)

    dst = dst_dir / src.name
    if dst.exists():
        return False, "目標已存在"

    shutil.move(str(src), str(dst))
    return True, str(dst.relative_to(DOCS_DIR))


def create_page(folder, name, title=""):
    """在指定資料夾建立新頁面。"""
    if not name.endswith(".md"):
        name += ".md"
    filepath = DOCS_DIR / folder / name if folder else DOCS_DIR / name
    filepath.parent.mkdir(parents=True, exist_ok=True)

    if filepath.exists():
        return False, "檔案已存在"

    title = title or name.replace(".md", "").replace("-", " ")
    filepath.write_text(f"# {title}\n\n", encoding="utf-8")
    return True, str(filepath.relative_to(DOCS_DIR))


def create_folder(parent, name):
    """建立新資料夾（含 index.md）。"""
    folder = DOCS_DIR / parent / name if parent else DOCS_DIR / name
    if folder.exists():
        return False, "資料夾已存在"

    folder.mkdir(parents=True, exist_ok=True)
    index = folder / "index.md"
    index.write_text(f"# {name}\n\n", encoding="utf-8")
    return True, str(folder.relative_to(DOCS_DIR))


def delete_item(path):
    """刪除檔案或資料夾（移到 .trash）。"""
    src = DOCS_DIR / path
    if not src.exists():
        return False, "不存在"

    trash = PROJECT_DIR / ".trash"
    trash.mkdir(exist_ok=True)
    dst = trash / src.name
    counter = 1
    while dst.exists():
        dst = trash / f"{src.stem}_{counter}{src.suffix}"
        counter += 1

    shutil.move(str(src), str(dst))
    return True, f"已移至 .trash/{dst.name}"


# ─── HTTP Server ─────────────────────────────────────

HTML = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Jobdone Docs 管理</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f5f7fa; color: #333; }
.header { background: #1a73e8; color: white; padding: 12px 24px; display: flex; align-items: center; justify-content: space-between; }
.header h1 { font-size: 18px; font-weight: 500; }
.header .actions { display: flex; gap: 8px; }
.btn { padding: 6px 16px; border: none; border-radius: 4px; cursor: pointer; font-size: 13px; }
.btn-primary { background: white; color: #1a73e8; }
.btn-primary:hover { background: #e8f0fe; }
.btn-danger { background: #dc3545; color: white; }
.btn-danger:hover { background: #c82333; }
.btn-sm { padding: 3px 10px; font-size: 12px; }
.container { display: flex; height: calc(100vh - 48px); }
.sidebar { width: 380px; background: white; border-right: 1px solid #ddd; overflow-y: auto; padding: 12px 0; }
.main { flex: 1; padding: 24px; overflow-y: auto; }

/* Tree */
.tree-item { user-select: none; }
.tree-row { display: flex; align-items: center; padding: 4px 8px; cursor: pointer; border-radius: 4px; margin: 1px 8px; font-size: 13px; }
.tree-row:hover { background: #e8f0fe; }
.tree-row.active { background: #d2e3fc; }
.tree-row.drag-over { border-top: 2px solid #1a73e8; }
.tree-toggle { width: 20px; text-align: center; color: #666; flex-shrink: 0; }
.tree-icon { margin-right: 6px; flex-shrink: 0; }
.tree-title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tree-children { padding-left: 16px; }
.tree-children.collapsed { display: none; }

/* Context menu */
.context-menu { position: fixed; background: white; border: 1px solid #ddd; border-radius: 6px; box-shadow: 0 4px 12px rgba(0,0,0,0.15); padding: 4px 0; z-index: 1000; min-width: 160px; }
.context-menu-item { padding: 6px 16px; cursor: pointer; font-size: 13px; }
.context-menu-item:hover { background: #e8f0fe; }
.context-menu-sep { border-top: 1px solid #eee; margin: 4px 0; }

/* Detail panel */
.detail h2 { font-size: 16px; margin-bottom: 16px; }
.detail-field { margin-bottom: 12px; }
.detail-field label { display: block; font-size: 12px; color: #666; margin-bottom: 4px; }
.detail-field input { width: 100%; padding: 6px 10px; border: 1px solid #ddd; border-radius: 4px; font-size: 13px; }
.detail-field .path { font-family: monospace; font-size: 12px; color: #888; }

/* Toast */
.toast { position: fixed; bottom: 20px; right: 20px; background: #333; color: white; padding: 10px 20px; border-radius: 6px; font-size: 13px; z-index: 2000; transition: opacity 0.3s; }
.toast.hidden { opacity: 0; pointer-events: none; }

/* Dialog */
.dialog-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.4); z-index: 1500; display: flex; align-items: center; justify-content: center; }
.dialog { background: white; border-radius: 8px; padding: 24px; min-width: 360px; box-shadow: 0 8px 32px rgba(0,0,0,0.2); }
.dialog h3 { margin-bottom: 16px; }
.dialog input { width: 100%; padding: 8px 12px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; margin-bottom: 16px; }
.dialog .btns { display: flex; gap: 8px; justify-content: flex-end; }
</style>
</head>
<body>

<div class="header">
  <h1>📚 Jobdone Docs 管理</h1>
  <div class="actions">
    <button class="btn btn-primary" onclick="rebuildNav()">🔄 重建 Nav</button>
    <button class="btn btn-primary" onclick="window.open('http://localhost:8100','_blank')">👁 預覽網站</button>
  </div>
</div>

<div class="container">
  <div class="sidebar" id="sidebar"></div>
  <div class="main">
    <div class="detail" id="detail">
      <h2>選擇左側項目進行編輯</h2>
      <p style="color:#888; font-size:13px; margin-top:8px;">
        右鍵點擊項目可以新增、重命名、移動、刪除。<br>
        拖拽項目可以移動到其他資料夾。
      </p>
    </div>
  </div>
</div>

<div class="toast hidden" id="toast"></div>

<script>
let treeData = [];
let selectedItem = null;
let dragItem = null;
let contextMenu = null;

// ─── API ──────────────────────────
async function api(action, params = {}) {
  const resp = await fetch('/api', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, ...params })
  });
  return await resp.json();
}

async function loadTree() {
  const data = await api('tree');
  treeData = data.tree;
  renderTree();
}

async function rebuildNav() {
  const data = await api('rebuild_nav');
  toast(`Nav 已重建（${data.count} 項）`);
}

// ─── Render ───────────────────────
function renderTree() {
  document.getElementById('sidebar').innerHTML = renderItems(treeData, '');
}

function renderItems(items, parentPath) {
  let html = '';
  for (const item of items) {
    const isFolder = item.type === 'folder';
    const icon = isFolder ? '📁' : '📄';
    const toggle = isFolder ? '<span class="tree-toggle">▶</span>' : '<span class="tree-toggle"></span>';

    html += `<div class="tree-item" data-path="${item.path}" data-type="${item.type}">
      <div class="tree-row" draggable="true"
           onclick="selectItem(this, '${item.path}')"
           oncontextmenu="showContext(event, '${item.path}', '${item.type}')"
           ondragstart="onDragStart(event, '${item.path}')"
           ondragover="onDragOver(event)"
           ondrop="onDrop(event, '${item.path}', '${item.type}')">
        ${toggle}
        <span class="tree-icon">${icon}</span>
        <span class="tree-title">${item.title || item.name}</span>
      </div>`;

    if (isFolder && item.children && item.children.length > 0) {
      html += `<div class="tree-children collapsed">${renderItems(item.children, item.path)}</div>`;
    }
    html += '</div>';
  }
  return html;
}

function selectItem(el, path) {
  // Toggle folder
  const item = el.closest('.tree-item');
  const children = item.querySelector('.tree-children');
  if (children) {
    children.classList.toggle('collapsed');
    const toggle = el.querySelector('.tree-toggle');
    if (toggle) toggle.textContent = children.classList.contains('collapsed') ? '▶' : '▼';
  }

  // Highlight
  document.querySelectorAll('.tree-row.active').forEach(r => r.classList.remove('active'));
  el.classList.add('active');
  selectedItem = path;

  // Show detail
  showDetail(path);
}

function showDetail(path) {
  const item = findItem(treeData, path);
  if (!item) return;

  const isFolder = item.type === 'folder';
  document.getElementById('detail').innerHTML = `
    <h2>${isFolder ? '📁' : '📄'} ${item.title || item.name}</h2>
    <div class="detail-field">
      <label>路徑</label>
      <div class="path">${item.path}</div>
    </div>
    <div class="detail-field">
      <label>標題</label>
      <input value="${item.title || ''}" onchange="renameTitle('${item.path}', this.value)">
    </div>
    ${!isFolder ? `<div class="detail-field"><label>大小</label><div>${item.size || 0} bytes</div></div>` : ''}
    <div style="margin-top:16px; display:flex; gap:8px;">
      <button class="btn btn-sm btn-primary" onclick="promptRename('${item.path}', '${item.name}')">✏️ 重命名</button>
      <button class="btn btn-sm btn-danger" onclick="deleteItem('${item.path}')">🗑 刪除</button>
    </div>
  `;
}

function findItem(items, path) {
  for (const item of items) {
    if (item.path === path) return item;
    if (item.children) {
      const found = findItem(item.children, path);
      if (found) return found;
    }
  }
  return null;
}

// ─── Context Menu ─────────────────
function showContext(e, path, type) {
  e.preventDefault();
  hideContext();

  const menu = document.createElement('div');
  menu.className = 'context-menu';
  menu.style.left = e.clientX + 'px';
  menu.style.top = e.clientY + 'px';

  const items = [];
  if (type === 'folder') {
    items.push({ label: '📄 新增頁面', action: () => promptCreate(path, 'file') });
    items.push({ label: '📁 新增子資料夾', action: () => promptCreate(path, 'folder') });
    items.push({ sep: true });
  }
  items.push({ label: '✏️ 重命名', action: () => {
    const item = findItem(treeData, path);
    promptRename(path, item ? item.name : '');
  }});
  items.push({ label: '📋 移動到...', action: () => promptMove(path) });
  items.push({ sep: true });
  items.push({ label: '🗑 刪除', action: () => deleteItem(path), danger: true });

  for (const item of items) {
    if (item.sep) {
      menu.innerHTML += '<div class="context-menu-sep"></div>';
    } else {
      const div = document.createElement('div');
      div.className = 'context-menu-item';
      if (item.danger) div.style.color = '#dc3545';
      div.textContent = item.label;
      div.onclick = () => { hideContext(); item.action(); };
      menu.appendChild(div);
    }
  }

  document.body.appendChild(menu);
  contextMenu = menu;

  // Auto-close
  setTimeout(() => document.addEventListener('click', hideContext, { once: true }), 10);
}

function hideContext() {
  if (contextMenu) { contextMenu.remove(); contextMenu = null; }
}

// ─── Drag & Drop ──────────────────
function onDragStart(e, path) {
  dragItem = path;
  e.dataTransfer.effectAllowed = 'move';
}

function onDragOver(e) {
  e.preventDefault();
  e.currentTarget.classList.add('drag-over');
}

function onDrop(e, targetPath, targetType) {
  e.preventDefault();
  e.currentTarget.classList.remove('drag-over');
  if (!dragItem || dragItem === targetPath) return;

  const destFolder = targetType === 'folder' ? targetPath : targetPath.split('/').slice(0, -1).join('/');
  moveItem(dragItem, destFolder);
  dragItem = null;
}

// ─── Actions ──────────────────────
function promptCreate(folder, type) {
  showDialog(type === 'folder' ? '新增資料夾' : '新增頁面', '名稱', async (name) => {
    if (!name) return;
    const data = type === 'folder'
      ? await api('create_folder', { parent: folder, name })
      : await api('create_page', { folder, name, title: name });
    if (data.ok) { toast('已建立'); loadTree(); }
    else toast('錯誤: ' + data.error);
  });
}

function promptRename(path, currentName) {
  showDialog('重命名', '新名稱', async (name) => {
    if (!name) return;
    const data = await api('rename', { path, newName: name });
    if (data.ok) { toast('已重命名'); loadTree(); }
    else toast('錯誤: ' + data.error);
  }, currentName.replace('.md', ''));
}

function promptMove(path) {
  showDialog('移動到（資料夾路徑）', '目標資料夾（空白=根目錄）', async (dest) => {
    const data = await api('move', { src: path, dst: dest || '' });
    if (data.ok) { toast('已移動'); loadTree(); }
    else toast('錯誤: ' + data.error);
  });
}

async function deleteItem(path) {
  if (!confirm(`確定刪除 ${path}？（會移到 .trash）`)) return;
  const data = await api('delete', { path });
  if (data.ok) { toast(data.message); loadTree(); }
  else toast('錯誤: ' + data.error);
}

async function renameTitle(path, newTitle) {
  // Just update the first line of the md file
  const data = await api('update_title', { path, title: newTitle });
  if (data.ok) { toast('標題已更新'); loadTree(); }
}

// ─── Dialog ───────────────────────
function showDialog(title, placeholder, callback, defaultValue = '') {
  const overlay = document.createElement('div');
  overlay.className = 'dialog-overlay';
  overlay.innerHTML = `
    <div class="dialog">
      <h3>${title}</h3>
      <input id="dialogInput" placeholder="${placeholder}" value="${defaultValue}">
      <div class="btns">
        <button class="btn" onclick="this.closest('.dialog-overlay').remove()">取消</button>
        <button class="btn btn-primary" id="dialogOk">確定</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  const input = overlay.querySelector('#dialogInput');
  input.focus();
  input.select();

  const submit = () => { callback(input.value); overlay.remove(); };
  overlay.querySelector('#dialogOk').onclick = submit;
  input.onkeydown = (e) => { if (e.key === 'Enter') submit(); };
}

// ─── Toast ────────────────────────
function toast(msg) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.remove('hidden');
  setTimeout(() => el.classList.add('hidden'), 2500);
}

// ─── Init ─────────────────────────
loadTree();
</script>
</body>
</html>"""


class AdminHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # suppress logs

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(HTML.encode("utf-8"))

    def do_POST(self):
        if self.path != "/api":
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length > 0 else {}
        action = body.get("action", "")

        result = {}

        if action == "tree":
            result = {"tree": scan_tree(DOCS_DIR)}

        elif action == "rebuild_nav":
            tree = scan_tree(DOCS_DIR)
            count = rebuild_mkdocs_nav(tree)
            result = {"ok": True, "count": count}

        elif action == "rename":
            ok, msg = rename_item(body["path"], body["newName"])
            result = {"ok": ok, "error": msg if not ok else None, "newPath": msg if ok else None}

        elif action == "move":
            ok, msg = move_item(body["src"], body["dst"])
            result = {"ok": ok, "error": msg if not ok else None}

        elif action == "create_page":
            ok, msg = create_page(body.get("folder", ""), body["name"], body.get("title", ""))
            result = {"ok": ok, "error": msg if not ok else None}

        elif action == "create_folder":
            ok, msg = create_folder(body.get("parent", ""), body["name"])
            result = {"ok": ok, "error": msg if not ok else None}

        elif action == "delete":
            ok, msg = delete_item(body["path"])
            result = {"ok": ok, "message": msg, "error": msg if not ok else None}

        elif action == "update_title":
            path = body["path"]
            title = body["title"]
            filepath = DOCS_DIR / path
            if not filepath.exists():
                # Check if it's a folder index
                filepath = DOCS_DIR / path / "index.md"
            if filepath.exists():
                content = filepath.read_text(encoding="utf-8")
                # Replace first # line
                new_content = re.sub(r"^# .+", f"# {title}", content, count=1, flags=re.MULTILINE)
                filepath.write_text(new_content, encoding="utf-8")
                result = {"ok": True}
            else:
                result = {"ok": False, "error": "檔案不存在"}

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))


if __name__ == "__main__":
    print(f"📚 Jobdone Docs 管理介面")
    print(f"   http://localhost:{PORT}")
    print(f"   Ctrl+C 停止")
    server = http.server.HTTPServer(("", PORT), AdminHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n停止")
