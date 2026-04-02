#!/usr/bin/env python3
"""
GitBook → MkDocs 同步工具
從 GitBook space 匯出所有頁面和圖片到 MkDocs 結構。

用法:
  python3 sync-from-gitbook.py              # 增量同步（跳過已存在的頁面）
  python3 sync-from-gitbook.py --full       # 全量同步（覆蓋所有頁面）
  python3 sync-from-gitbook.py --rebuild-nav  # 只重建 mkdocs.yml nav
"""
import json
import os
import re
import ssl
import sys
import time
import hashlib
import urllib.request
import urllib.error
from pathlib import Path

try:
    import certifi
    SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CTX = ssl.create_default_context()

# ─── 設定 ───────────────────────────────────────────
GB_TOKEN = "gb_api_t9Zo22p2kmJEHJRawX8PgFlpXztByxBaVF2hbOnO"
GB_SPACE = "EqUCL3D5WQfpxJw8NL3P"
GB_API = "https://api.gitbook.com/v1"

PROJECT_DIR = Path(__file__).parent
DOCS_DIR = PROJECT_DIR / "docs"
IMG_DIR = DOCS_DIR / "images"

# 排除的 section（不匯出）
EXCLUDE_PATHS = {"disable"}

# ─── API ────────────────────────────────────────────

def api_get(path):
    """呼叫 GitBook API，含重試和 rate limit 處理。"""
    url = f"{GB_API}{path}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {GB_TOKEN}"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = int(e.headers.get("Retry-After", 5))
                print(f"    ⏳ Rate limited, waiting {wait}s...")
                time.sleep(wait)
            elif e.code == 404:
                return None
            else:
                time.sleep(2)
        except Exception:
            time.sleep(2)
    return None


def download_image(url, dest):
    """下載圖片到本地。已存在且大於 200 bytes 的跳過。"""
    if dest.exists() and dest.stat().st_size > 200:
        return True
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as resp:
            data = resp.read()
            if len(data) > 200:
                dest.write_bytes(data)
                return True
    except Exception:
        pass
    return False


# ─── Markdown 轉換 ──────────────────────────────────

def convert_markdown(md, page_path, has_children):
    """
    將 GitBook markdown 轉成 MkDocs 格式：
    - <figure><img> → ![caption](local_path)
    - {% hint %} → !!! admonition
    - <mark> → **bold**
    下載圖片到 images/ 資料夾。
    """
    img_count = 0

    def replace_image(match):
        nonlocal img_count
        src_match = re.search(r'src="([^"]+)"', match.group(0))
        if not src_match:
            return match.group(0)

        url = src_match.group(1).replace("&#x26;", "&")
        caption_match = re.search(r'<figcaption><p>([^<]+)</p></figcaption>', match.group(0))
        caption = caption_match.group(1) if caption_match else ""

        # 用 URL hash 作為本地檔名
        url_hash = hashlib.md5(url.encode()).hexdigest()[:16]
        local_name = f"{url_hash}.png"
        local_path = IMG_DIR / local_name

        if download_image(url, local_path):
            img_count += 1
            # 偵測實際檔案格式
            header = local_path.read_bytes()[:8]
            if header[:3] == b'\xff\xd8\xff':
                new_path = local_path.with_suffix('.jpg')
                if not new_path.exists():
                    local_path.rename(new_path)
                local_name = new_path.name
            elif header[:4] == b'RIFF':
                new_path = local_path.with_suffix('.webp')
                if not new_path.exists():
                    local_path.rename(new_path)
                local_name = new_path.name

        # 計算相對路徑
        depth = page_path.count("/") + (1 if has_children else 0)
        prefix = "../" * depth
        return f"![{caption}]({prefix}images/{local_name})"

    # 轉換 <figure> 和 <img> 標籤
    md = re.sub(r'<figure>.*?</figure>', replace_image, md, flags=re.DOTALL)
    md = re.sub(r'<img\s+[^>]*src="[^"]*gitbook[^"]*"[^>]*/?\s*>', replace_image, md)

    # 轉換 GitBook hint → MkDocs admonition
    def convert_hint(match):
        style = match.group(1)
        content = match.group(2).strip()
        mkdocs_type = {
            "info": "info", "warning": "warning",
            "danger": "danger", "success": "tip"
        }.get(style, "note")
        lines = content.split("\n")
        return f"\n!!! {mkdocs_type}\n" + "".join(f"    {line}\n" for line in lines)

    md = re.sub(
        r'{%\s*hint\s+style="([^"]+)"\s*%}(.*?){%\s*endhint\s*%}',
        convert_hint, md, flags=re.DOTALL
    )

    # 轉換 <mark> → **bold**
    md = re.sub(r'<mark\s+style="[^"]*">([^<]*)</mark>', r'**\1**', md)

    # 移除其他 GitBook 特殊語法
    md = re.sub(r'{%\s*embed\s+url="([^"]+)"[^%]*%}', r'[\1](\1)', md)

    return md, img_count


# ─── 頁面樹 ─────────────────────────────────────────

def flatten_pages(pages):
    """遞迴展開頁面樹。"""
    for p in pages:
        yield p
        if p.get("pages"):
            yield from flatten_pages(p["pages"])


def sanitize_filename(title):
    """將頁面標題轉成安全的檔名。"""
    name = title.replace("**", "").strip()
    name = re.sub(r'[/\\:*?"<>|]', '', name)
    name = re.sub(r'\s+', '-', name).strip('-')
    return name


# ─── 匯出頁面 ───────────────────────────────────────

def export_pages(content_tree, full_mode=False):
    """匯出所有頁面。full_mode=True 時覆蓋已存在的。"""
    IMG_DIR.mkdir(parents=True, exist_ok=True)

    all_pages = list(flatten_pages(content_tree))
    total = len(all_pages)
    exported = 0
    skipped = 0
    errors = 0

    print(f"\n📄 匯出頁面（共 {total} 頁）...")

    for i, page in enumerate(all_pages, 1):
        page_id = page["id"]
        page_path = page.get("path") or page.get("slug") or page_id
        page_title = page.get("title", "Untitled")
        has_children = bool(page.get("pages"))

        # 決定輸出路徑
        if has_children:
            out_file = DOCS_DIR / page_path / "index.md"
        else:
            out_file = DOCS_DIR / f"{page_path}.md"

        # 增量模式：跳過已存在的
        if not full_mode and out_file.exists() and out_file.stat().st_size > 50:
            skipped += 1
            continue

        # 取得 markdown
        data = api_get(f"/spaces/{GB_SPACE}/content/page/{page_id}?format=markdown")
        if not data or "markdown" not in data:
            continue

        md = data["markdown"]
        md, img_count = convert_markdown(md, page_path, has_children)

        # 處理 surrogate 字元
        md = md.encode("utf-8", errors="replace").decode("utf-8")

        # 寫入檔案
        out_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            out_file.write_text(md, encoding="utf-8")
            exported += 1
            status = f" ({img_count} imgs)" if img_count else ""
            print(f"  [{exported}] {page_title}{status}")
        except Exception as e:
            errors += 1
            print(f"  ❌ {page_title}: {e}")

        time.sleep(0.15)

    return exported, skipped, errors


# ─── 重命名為中文 ───────────────────────────────────

def rename_to_chinese(content_tree):
    """將拼音檔名改為中文。"""
    import shutil

    def do_rename(pages, parent_path=""):
        for page in pages:
            title = page.get("title", "Untitled")
            old_slug = page.get("path") or page.get("slug") or page.get("id", "unknown")
            children = page.get("pages", [])
            has_children = bool(children)

            new_name = sanitize_filename(title)
            new_path = f"{parent_path}/{new_name}" if parent_path else new_name

            if has_children:
                old_file = DOCS_DIR / old_slug / "index.md"
                new_file = DOCS_DIR / new_path / "index.md"
            else:
                old_file = DOCS_DIR / f"{old_slug}.md"
                new_file = DOCS_DIR / f"{new_path}.md"

            if old_file.exists() and old_file != new_file:
                new_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(old_file), str(new_file))

            if children:
                do_rename(children, new_path)

    print("\n📁 重命名為中文...")
    do_rename(content_tree)

    # 清理空目錄
    for dirpath, dirnames, filenames in os.walk(DOCS_DIR, topdown=False):
        if not filenames and not dirnames and dirpath != str(DOCS_DIR):
            try:
                os.rmdir(dirpath)
            except OSError:
                pass


# ─── 修正圖片路徑 ───────────────────────────────────

def fix_image_paths():
    """修正子目錄頁面的圖片相對路徑。"""
    print("\n🔗 修正圖片路徑...")
    for md_file in DOCS_DIR.rglob("*.md"):
        if "images" in str(md_file) or "stylesheets" in str(md_file) or "javascripts" in str(md_file):
            continue
        content = md_file.read_text(encoding="utf-8")
        depth = len(md_file.parent.relative_to(DOCS_DIR).parts)
        if depth == 0:
            continue
        prefix = "../" * depth
        # 修正所有 images/ 開頭的路徑
        new_content = re.sub(r'\]\((?:\.\./)*images/', f']({prefix}images/', content)
        if new_content != content:
            md_file.write_text(new_content, encoding="utf-8")


# ─── 重建 Nav ───────────────────────────────────────

def build_nav_yaml(pages, indent=2):
    """從頁面樹建立 mkdocs.yml 的 nav 區段。"""
    lines = []
    prefix = " " * indent

    for page in pages:
        title = page.get("title", "Untitled")
        new_name = sanitize_filename(title)
        children = page.get("pages", [])

        if children:
            lines.append(f"{prefix}- {title}:")
            lines.append(f"{prefix}    - 總覽: {new_name}/index.md")
            lines.extend(build_nav_yaml(children, indent + 4))
        else:
            lines.append(f"{prefix}- {title}: {new_name}.md")

    return lines


def rebuild_nav(content_tree):
    """重建 mkdocs.yml 的 nav 區段。"""
    print("\n📋 重建 mkdocs.yml nav...")

    # 讀取現有 mkdocs.yml
    yml_path = PROJECT_DIR / "mkdocs.yml"
    yml = yml_path.read_text(encoding="utf-8")

    # 建立新 nav
    nav_lines = build_nav_yaml(content_tree)
    nav_yaml = "\n".join(nav_lines)

    # 替換 nav 區段
    new_nav = f"nav:\n  - 首頁: index.md\n{nav_yaml}\n"
    yml = re.sub(r'nav:.*', new_nav, yml, flags=re.DOTALL)

    yml_path.write_text(yml, encoding="utf-8")
    print(f"  ✓ nav 已更新（{len(nav_lines)} 項）")


# ─── 主程式 ─────────────────────────────────────────

def main():
    full_mode = "--full" in sys.argv
    nav_only = "--rebuild-nav" in sys.argv

    print("=" * 50)
    print("  GitBook → MkDocs 同步工具")
    print("=" * 50)

    mode = "全量" if full_mode else ("僅 nav" if nav_only else "增量")
    print(f"  Space: {GB_SPACE}")
    print(f"  模式: {mode}")

    # 取得內容樹
    print("\n🌳 取得內容樹...")
    content = api_get(f"/spaces/{GB_SPACE}/content")
    if not content:
        print("❌ 無法取得內容樹")
        sys.exit(1)

    # 過濾排除的 section
    pages = [p for p in content["pages"] if p.get("path", "") not in EXCLUDE_PATHS]
    total = sum(1 for _ in flatten_pages(pages))
    print(f"  {total} 頁（排除: {', '.join(EXCLUDE_PATHS)}）")

    if nav_only:
        rebuild_nav(pages)
        return

    # 匯出頁面
    exported, skipped, errors = export_pages(pages, full_mode)

    # 重命名為中文
    rename_to_chinese(pages)

    # 修正圖片路徑
    fix_image_paths()

    # 重建 nav
    rebuild_nav(pages)

    # 統計
    img_count = sum(1 for _ in IMG_DIR.iterdir()) if IMG_DIR.exists() else 0
    md_count = sum(1 for _ in DOCS_DIR.rglob("*.md")
                   if "images" not in str(_) and "stylesheets" not in str(_) and "javascripts" not in str(_))

    print("\n" + "=" * 50)
    print(f"  ✅ 完成")
    print(f"  新增: {exported} 頁")
    print(f"  跳過: {skipped} 頁")
    print(f"  錯誤: {errors}")
    print(f"  圖片: {img_count}")
    print(f"  總頁數: {md_count}")
    print("=" * 50)


if __name__ == "__main__":
    main()
