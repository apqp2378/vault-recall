"""인터랙티브 그래프 리포트 — self-contained HTML (force-graph CDN).

react-force-graph의 개념을 빌드 없이: 노드=노트(폴더별 색·연결수 크기),
클릭 시 메타 표시. 산출물 하나로 볼트 전체 구조를 눈으로 검증한다.
"""
from __future__ import annotations

import json
from pathlib import Path

PALETTE = ["#4c6ef5", "#f76707", "#0ca678", "#ae3ec9", "#f59f00",
           "#e64980", "#1098ad", "#74b816", "#7048e8", "#868e96"]

TEMPLATE = """<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8"><title>vault-recall — 지식그래프</title>
<style>
 body{margin:0;font-family:system-ui,sans-serif;background:#fafafa}
 #info{position:fixed;top:12px;left:12px;max-width:340px;background:#fff;
   border:1px solid #ddd;border-radius:10px;padding:12px 16px;font-size:13px;
   box-shadow:0 2px 10px rgba(0,0,0,.08)}
 #legend{position:fixed;bottom:12px;left:12px;background:#fff;border:1px solid #ddd;
   border-radius:10px;padding:8px 12px;font-size:12px}
 .sw{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px}
</style></head><body>
<div id="graph"></div>
<div id="info"><b>vault-recall 지식그래프</b><br>노드를 클릭하면 상세가 보입니다.</div>
<div id="legend">__LEGEND__</div>
<script src="https://unpkg.com/force-graph@1"></script>
<script>
const data = __DATA__;
const el = document.getElementById('info');
ForceGraph()(document.getElementById('graph'))
  .graphData(data)
  .nodeId('id')
  .nodeLabel(n => n.id)
  .nodeVal(n => 2 + n.degree)
  .nodeColor(n => n.color)
  .linkColor(() => 'rgba(0,0,0,0.12)')
  .onNodeClick(n => {
    el.innerHTML = '<b>'+n.id+'</b><br>'+n.folder+' · '+n.type+
      (n.verified==='True'?' · ✓검증':' · ⚠미검증')+'<br>연결 '+n.degree+
      '<br><i>'+(n.desc||'')+'</i>';
  });
</script></body></html>"""


def build(notes, graph, out_path: str | Path) -> str:
    folders = sorted({n.folder for n in notes.values()})
    color = {f: PALETTE[i % len(PALETTE)] for i, f in enumerate(folders)}
    nodes = [{"id": n.name, "folder": n.folder, "type": n.type,
              "verified": str(n.verified), "degree": graph.degree(n.name),
              "desc": n.description[:160], "color": color[n.folder]}
             for n in notes.values()]
    links = [{"source": s, "target": t} for s, ts in graph.out.items() for t in ts]
    legend = "".join('<span class="sw" style="background:' + color[f] + '"></span>' + f + "&nbsp;&nbsp;"
                     for f in folders)
    html = (TEMPLATE.replace("__DATA__", json.dumps({"nodes": nodes, "links": links},
                                                    ensure_ascii=False))
                    .replace("__LEGEND__", legend))
    Path(out_path).write_text(html, encoding="utf-8")
    return str(out_path)
