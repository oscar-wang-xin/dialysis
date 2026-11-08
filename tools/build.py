# -*- coding: utf-8 -*-
"""构建「透析家庭照护工具包」的 6 张离线页面。

用法：  python tools/build.py
模板：  src/*.tpl.html（以「透析」目录下那套工具为模板基线）
数据：  data/qr-links.json + data/link-titles.json + data/knowledge.json
产物：  仓库根目录 6 个自包含 HTML（全英文文件名），双击即用、零外部依赖、可直接静态部署

自检：外部资源、脚本闭合、占位符、数据完整性、页面间链接、隐私关键词、机构标识、
来源与存疑残留、ASCII 文件名。
任何一项不过就不写产物。
"""
import html
import json
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
DATA = ROOT / 'data'

PAGES = {
    'index.tpl.html':     'index.html',
    'card.tpl.html':      'care-card.html',
    'sos.tpl.html':       'emergency.html',
    'daily.tpl.html':     'daily-log.html',
    'knowledge.tpl.html': 'knowledge.html',
    'guide.tpl.html':     'guide.html',
}

# 只放具体可识别的真实数据，不放「病历号 / 身份证号」这类通用字段名，
# 否则 PRIVACY.md 里提醒别人别提交的文字会把自己误报成泄密。
PRIVACY_BANNED = [
    '王一平', '77 岁', '67 kg', '干体重 67', '剩约 40 分钟',
]

# 机构标识：不收录任何医院名称、科室抬头或业务电话
ORG_BANNED = [
    '85323591', '药学部', '血液净化科',
]

PLACEHOLDERS = [
    'DATA_CARDS', 'DATA_TRIAGE', 'DATA_CHECKLIST',
    'DATA_LINKS_TREE', 'DATA_LINKS_DRUG',
    'DATA_OPENHINT', 'DATA_DISCLAIMER',
]


def read(p):
    return p.read_text(encoding='utf-8')


def esc(s):
    return html.escape(str(s), quote=True)


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
            })
    return out


# ---------------- 知识页片段 ----------------

def cards_html(kn):
    out = []
    for i, c in enumerate(kn['cards'], 1):
        plain = ' '.join([c['title'], c['body'], c['ask']])
        out.append(
            '<details class="fold" data-s="%s">\n'
            '  <summary><span class="idx">%02d</span><span>%s</span></summary>\n'
            '  <p class="body">%s</p>\n'
            '  <p class="ask"><b>该问医生：</b>%s</p>\n'
            '</details>' % (esc(plain), i, esc(c['title']), esc(c['body']), esc(c['ask']))
        )
    return '\n'.join(out)


def triage_html(kn):
    out = []
    for t in kn['triage']:
        plain = ' '.join([t['title']] + t['items'] + [t['steps'], t['call']])
        items = ''.join('<li>%s</li>' % esc(x) for x in t['items'])
        out.append(
            '<div class="card lv %s" data-s="%s">\n'
            '  <div class="card-head"><h3>%s</h3></div>\n'
            '  <ul>%s</ul>\n'
            '  <p class="step"><b>怎么做：</b>%s</p>\n'
            '  <span class="calltag">%s</span>\n'
            '</div>' % (esc(t['level']), esc(plain), esc(t['title']), items,
                        esc(t['steps']), esc(t['call']))
        )
    return '\n'.join(out)


def checklist_html(kn):
    rows = []
    for c in kn['checklists']:
        plain = ' '.join([c['sign'], c['first'], c['call']])
        rows.append(
            '<tr data-s="%s"><td>%s</td><td>%s</td><td>%s</td></tr>' %
            (esc(plain), esc(c['sign']), esc(c['first']), esc(c['call']))
        )
    return (
        '<table class="chk"><thead><tr>'
        '<th>看到什么</th><th>先记什么 / 做什么</th><th>联系谁</th>'
        '</tr></thead><tbody>\n' + '\n'.join(rows) + '\n</tbody></table>'
    )


def links_html(items, group):
    out = []
    for it in items:
        plain = '%s %02d %s %s' % (it['title'], it['no'], it['url'], it['host'])
        out.append(
            '<li data-s="%s">\n'
            '  <a class="lnk" href="%s" target="_blank" rel="noopener noreferrer">\n'
            '    <div class="lt">%s</div>\n'
            '    <div class="lm"><span class="no">%02d</span>%s<span class="go">↗</span></div>\n'
            '  </a>\n'
            '</li>' % (esc(plain), esc(it['url']), esc(it['title']),
                       it['no'], esc(it['host']))
        )
    return '\n'.join(out)




# ---------------- 自检 ----------------

def self_check(outputs, app):
    problems = []
    all_html = '\n'.join(outputs.values())

    # 1. 零外部资源依赖：不能有自动加载的外部脚本/样式/字体/图片
    if re.search(r'<script[^>]+src\s*=', all_html, re.I):
        problems.append('存在外部 script')
    if re.search(r'@import', all_html, re.I):
        problems.append('存在 @import')
    for m in re.finditer(r'<link[^>]+href\s*=\s*"([^"]+)', all_html, re.I):
        if not m.group(1).startswith('data:'):
            problems.append('存在外部 link：' + m.group(1)[:48])
    if re.search(r'https?://[^\s"\'<>]+?\.(css|js|woff2?|ttf)(\b|$)', all_html, re.I):
        problems.append('存在外部 css / js / 字体 URL')
    if re.search(r'\bfetch\s*\(|XMLHttpRequest|navigator\.sendBeacon', all_html):
        problems.append('页面里出现了网络请求调用')
    if re.search(r'<img[^>]+src\s*=\s*["\']https?://', all_html, re.I):
        problems.append('存在外部图片')

    # 2. 占位符必须全部替换
    for token in PLACEHOLDERS:
        if '<!--' + token + '-->' in all_html:
            problems.append('占位符未替换：' + token)

    # 3. 数据完整性
    if len(app['links']['drug']) != 38:
        problems.append('药物链接应为 38 条，实际 %d' % len(app['links']['drug']))
    if len(app['links']['tree']) != 22:
        problems.append('宣教链接应为 22 条，实际 %d' % len(app['links']['tree']))
    if len(app['cards']) != 9 or len(app['triage']) != 3 or len(app['checklists']) != 5:
        problems.append('常识卡 / 分级 / 排查清单数量不完整')
    for key in ('drug', 'tree'):
        if any(not str(x.get('title', '')).strip() for x in app['links'][key]):
            problems.append('%s 链接存在缺标题的条目' % key)

    # 4. 页面间相对链接必须指向真实存在的成品
    for name, text in outputs.items():
        for m in re.finditer(r'href="([^"#:]+?\.html)"', text):
            target = m.group(1)
            if target not in outputs:
                problems.append('%s 引用了不存在的页面：%s' % (name, target))

    # 5. 脚本闭合粗检
    for name, text in outputs.items():
        if text.count('<script') != text.count('</script>'):
            problems.append('%s 的 script 标签数量不匹配' % name)
        if text.count('<style') != text.count('</style>'):
            problems.append('%s 的 style 标签数量不匹配' % name)

    # 6. 隐私 / 机构标识：全仓库文本不得出现真实患者信息或机构联系方式
    #    先查本次要写出的产物（内存最新版），再查仓库其余文件；
    #    磁盘上同名成品是上一版、马上会被覆盖，跳过避免误报。
    hit, org_hit = [], []
    for name, txt in outputs.items():
        for word in PRIVACY_BANNED:
            if word in txt:
                hit.append('%s -> %s' % (name, word))
        for word in ORG_BANNED:
            if word in txt:
                org_hit.append('%s -> %s' % (name, word))
    for p in sorted(ROOT.rglob('*')):
        if not p.is_file() or p.name.startswith('_patch_') or p.name == 'build.py':
            continue
        if p.parent == ROOT and p.name in outputs:
            continue
        if p.suffix.lower() not in ('.html', '.css', '.js', '.json', '.md', '.py', '.txt', ''):
            continue
        if '.git' in p.parts or '__pycache__' in p.parts or '.playwright-cli' in p.parts:
            continue
        try:
            txt = p.read_text(encoding='utf-8')
        except (UnicodeDecodeError, OSError):
            continue
        for word in PRIVACY_BANNED:
            if word in txt:
                hit.append('%s -> %s' % (p.relative_to(ROOT), word))
        for word in ORG_BANNED:
            if word in txt:
                org_hit.append('%s -> %s' % (p.relative_to(ROOT), word))
    if hit:
        problems.append('疑似真实患者信息：' + '; '.join(hit))
    if org_hit:
        problems.append('疑似机构名称 / 联系方式：' + '; '.join(org_hit))

    # 8. 页面不再展示「来源与存疑」板块，也不再给条目标「存疑」
    for name, text in outputs.items():
        for word in ('来源与存疑', 'class="doubt"', '>存疑<'):
            if word in text:
                problems.append('%s 仍残留来源 / 存疑展示：%s' % (name, word))

    # 7. 部署友好：成品文件名必须 ASCII，根目录不得残留旧中文名页面
    for name in outputs:
        if not name.isascii():
            problems.append('产物文件名含非 ASCII 字符：' + name)
    for p in sorted(ROOT.glob('*.html')):
        if not p.name.isascii():
            problems.append('根目录残留旧中文名成品：' + p.name)

    return problems


def main():
    qr = json.loads(read(DATA / 'qr-links.json'))
    kn = json.loads(read(DATA / 'knowledge.json'))
    titles = json.loads(read(DATA / 'link-titles.json'))

    if len(titles['drug']) != 38 or len(titles['tree']) != 22:
        print('构建中止：海报标题应为 38 / 22 条')
        return 1

    app = {
        'generated': date.today().isoformat(),
        'source': kn['source'],
        'cards': kn['cards'],
        'triage': kn['triage'],
        'checklists': kn['checklists'],
        'links': {
            'drug': ordered_links(qr['drug'], 60, titles['drug']),
            'tree': ordered_links(qr['tree'], 60, titles['tree']),
        },
    }

    outputs = {}
    for tpl, target in PAGES.items():
        text = read(SRC / tpl)
        if tpl == 'knowledge.tpl.html':
            text = (text
                    .replace('<!--DATA_CARDS-->', cards_html(kn))
                    .replace('<!--DATA_TRIAGE-->', triage_html(kn))
                    .replace('<!--DATA_CHECKLIST-->', checklist_html(kn))
                    .replace('<!--DATA_LINKS_TREE-->',
                             links_html(app['links']['tree'], 'tree'))
                    .replace('<!--DATA_LINKS_DRUG-->',
                             links_html(app['links']['drug'], 'drug'))
                    .replace('<!--DATA_OPENHINT-->', esc(kn['source']['openHint']))
                    .replace('<!--DATA_DISCLAIMER-->', esc(kn['disclaimer'])))
        outputs[target] = text

    problems = self_check(outputs, app)
    if problems:
        print('构建中止，自检未通过：')
        for p in problems:
            print('  - ' + p)
        return 1

    for name, text in outputs.items():
        (ROOT / name).write_text(text, encoding='utf-8', newline='\n')

    total = sum((ROOT / n).stat().st_size for n in outputs)
    print('构建完成：%d 张离线页面，共 %.1f KB' % (len(outputs), total / 1024))
    for name in outputs:
        print('  - %-22s %6.1f KB' % (name, (ROOT / name).stat().st_size / 1024))
    print('  宣教链接  %d 条 / 药物链接  %d 条（标题索引）' %
          (len(app['links']['tree']), len(app['links']['drug'])))
    print('  常识卡    %d 张 / 分级排查 %d 级 / 问题清单 %d 条' %
          (len(app['cards']), len(app['triage']), len(app['checklists'])))
    print('  自检      外部资源 / 占位符 / 数据完整性 / 页面链接 / 脚本闭合 / 隐私 / 机构标识 / 来源与存疑 / ASCII 文件名  全部通过')
    return 0


if __name__ == '__main__':
    sys.exit(main())
