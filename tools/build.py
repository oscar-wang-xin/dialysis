# -*- coding: utf-8 -*-
"""构建单文件成品 index.html。

用法：  python tools/build.py
源码：  src/shell.html + src/app.css + src/app.js + data/*.json
产物：  index.html（提交进仓库，双击即用，零外部依赖）

构建时会做四类自检：外部资源引用、脚本闭合、链接条数、隐私关键词。
任何一项不过就不写产物。
"""
import json
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
DATA = ROOT / 'data'
OUT = ROOT / 'index.html'

# 只放「具体可识别的真实数据」，不放「病历号 / 身份证号」这类通用字段名，
# 否则 PRIVACY.md 里提醒别人别提交的文字会把自己误报成泄密。
PRIVACY_BANNED = [
    '王一平', '77 岁', '67 kg', '干体重 67', '剩约 40 分钟',
]


def read(p):
    return p.read_text(encoding='utf-8')


def ordered_links(items, row_gap=60, titles=None):
    """按海报坐标聚类成行、行内从左到右编号。药表能还原 1–38 的阅读顺序。"""
    rows = []
    for item in sorted(items, key=lambda o: (o['y'], o['x'])):
        if rows and item['y'] - rows[-1][0]['y'] <= row_gap:
            rows[-1].append(item)
        else:
            rows.append([item])
    out, n = [], 0
    for row in rows:
        for item in sorted(row, key=lambda o: o['x']):
            n += 1
            url = item['text']
            out.append({
                'no': n,
                'title': (titles[n - 1] if titles and n <= len(titles) else ''),
                'url': url,
                'host': urlparse(url).netloc,
                'x': item['x'],
                'y': item['y'],
            })
    return out


def self_check(html, css, js, app):
    problems = []

    # 1. 零外部资源：不允许 script/link 外链、@import、外部字体/脚本 URL
    if re.search(r'<script[^>]+src\s*=|@import', html):
        problems.append('存在外部 script 或 @import')
    for m in re.finditer(r'<link[^>]+href\s*=\s*"([^"]+)', html):
        if not m.group(1).startswith('data:'):
            problems.append('存在外部 link：' + m.group(1)[:48])
    if re.search(r'https?://[^\s"\'<>]+?\.(css|js|woff2?|ttf)(\b|$)', html):
        problems.append('存在外部 css / js / 字体 URL')
    if 'fetch(' in js or 'XMLHttpRequest' in js or 'navigator.sendBeacon' in js:
        problems.append('应用逻辑里出现了网络请求调用')

    # 2. 脚本闭合：内联脚本里不能出现字面 </script>
    if '</script' in js.lower() or '</script' in css.lower():
        problems.append('内联样式/脚本里含 </script，会截断 HTML')

    # 3. 占位符必须全部替换
    for token in ('/*__CSS__*/', '/*__JS__*/', '/*__DATA__*/'):
        if token in html:
            problems.append('占位符未替换：' + token)

    # 4. 知识数据完整性
    if len(app['links']['drug']) != 38:
        problems.append('药物链接应为 38 条，实际 %d' % len(app['links']['drug']))
    if len(app['links']['tree']) != 22:
        problems.append('宣教链接应为 22 条，实际 %d' % len(app['links']['tree']))
    if len(app['cards']) < 6 or len(app['triage']) != 3:
        problems.append('常识卡或分级数据不完整')
    for key in ('drug', 'tree'):
        if any(not str(x.get('title', '')).strip() for x in app['links'][key]):
            problems.append('%s 链接存在缺标题的条目' % key)

    # 5. 隐私：全仓库文本不得出现真实患者信息
    hit = []
    for p in sorted(ROOT.rglob('*')):
        # build.py 自身保存了违禁词清单，跳过，否则会命中自己
        if not p.is_file() or p.name.startswith('_patch_') or p.name == 'build.py':
            continue
        if p.suffix.lower() not in ('.html', '.css', '.js', '.json', '.md', '.py', '.txt', ''):
            continue
        if '.git' in p.parts or '__pycache__' in p.parts:
            continue
        try:
            txt = p.read_text(encoding='utf-8')
        except (UnicodeDecodeError, OSError):
            continue
        for word in PRIVACY_BANNED:
            if word in txt:
                hit.append('%s -> %s' % (p.relative_to(ROOT), word))
    if hit:
        problems.append('疑似真实患者信息：' + '; '.join(hit))

    return problems


def main():
    shell = read(SRC / 'shell.html')
    css = read(SRC / 'app.css')
    js = read(SRC / 'app.js')
    qr = json.loads(read(DATA / 'qr-links.json'))
    kn = json.loads(read(DATA / 'knowledge.json'))
    titles = json.loads(read(DATA / 'link-titles.json'))
    if len(titles['drug']) != 38 or len(titles['tree']) != 22:
        print('构建中止：海报标题应为 38 / 22 条')
        return 1

    app = {
        'version': 1,
        'generated': date.today().isoformat(),
        'source': kn['source'],
        'groups': kn['groups'],
        'cards': kn['cards'],
        'triage': kn['triage'],
        'checklists': kn['checklists'],
        'symptoms': kn['symptoms'],
        'labNames': kn['labNames'],
        'dailyTypes': kn['dailyTypes'],
        'glucoseTags': kn['glucoseTags'],
        'disclaimer': kn['disclaimer'],
        'links': {
            'drug': ordered_links(qr['drug'], 60, titles['drug']),
            'tree': ordered_links(qr['tree'], 60, titles['tree']),
        },
    }

    payload = json.dumps(app, ensure_ascii=False, separators=(',', ':'))
    # 避免数据里的 < 被 HTML 解析器当成标签起始
    payload = payload.replace('<', '\\u003c')

    html = (shell
            .replace('/*__CSS__*/', css)
            .replace('/*__DATA__*/', payload)
            .replace('/*__JS__*/', js))

    problems = self_check(html, css, js, app)
    if problems:
        print('构建中止，自检未通过：')
        for p in problems:
            print('  - ' + p)
        return 1

    OUT.write_text(html, encoding='utf-8', newline='\n')
    print('构建完成：%s' % OUT)
    print('  大小      %.1f KB' % (OUT.stat().st_size / 1024))
    print('  宣教链接  %d 条' % len(app['links']['tree']))
    print('  药物链接  %d 条' % len(app['links']['drug']))
    print('  标题      %d 条（海报逐块辨认）' % (len(titles['drug']) + len(titles['tree'])))
    print('  常识卡    %d 张' % len(app['cards']))
    print('  自检      外部资源 / 脚本闭合 / 数据完整性 / 隐私关键词  全部通过')
    return 0


if __name__ == '__main__':
    sys.exit(main())
