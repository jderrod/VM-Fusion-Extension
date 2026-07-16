"""
Generate the panel-validation dashboard: a self-contained HTML report comparing
each scenario's ACTUAL model output against the EXPECTED output recomputed by
panel_expected (the calc-sheet logic). Open the resulting HTML in any browser —
no server required.

    python gen_dashboard.py            # writes validation_dashboard.html
    python gen_dashboard.py out.html   # custom output path
"""
import json
import os
import sys
from datetime import datetime

import compare
import panel_expected as pe


def _fmt(v):
    """Human-friendly value: strip float noise, blank -> em dash."""
    if pe._blank(v):
        return '—'
    try:
        f = float(v)
        if abs(f - round(f)) < 1e-6:
            return str(int(round(f)))
        return f'{round(f, 4):g}'
    except (TypeError, ValueError):
        return str(pe._unquote(v))


INPUT_LABELS = [
    ('panel_section', 'section'),
    ('component_height', 'height'),
    ('component_width', 'width'),
    ('component_floor_clearance', 'floor clr'),
    ('component_ceiling_clearance', 'ceil clr'),
    ('panel_abuts_inline_stile_front', 'abuts front'),
    ('panel_abuts_inline_stile_back', 'abuts back'),
    ('panel_front_inline_stile_floor_to_ceiling', 'front f2c'),
    ('panel_back_inline_stile_floor_to_ceiling', 'back f2c'),
    ('stile_in_the_back_width', 'stile back w'),
    ('cutout_A', 'cutout A'),
    ('cutout_B', 'cutout B'),
]


def build_payload():
    results = compare.scan()
    scenarios = []
    for r in results:
        if 'error' in r:
            scenarios.append({'scenario': r['scenario'], 'error': r['error'],
                              'ok': False, 'counts': {}, 'inputs': {}, 'rows': []})
            continue
        scenarios.append({
            'scenario': r['scenario'],
            'ok': r['ok'],
            'counts': r['counts'],
            'inputs': {k: _fmt(r['inputs'].get(k)) for k, _ in INPUT_LABELS},
            'rows': [{
                'param': row['param'],
                'expected': _fmt(row['expected']),
                'actual': _fmt(row['actual']),
                'status': row['status'],
                'kind': row.get('kind', 'derived'),
            } for row in r['rows']],
        })
    total = len(scenarios)
    passing = sum(1 for s in scenarios if s['ok'])
    params_per_scenario = max((len(s['rows']) for s in scenarios), default=0)
    # aggregate mismatches by param
    from collections import Counter
    pc = Counter()
    for s in scenarios:
        for row in s['rows']:
            if row['status'] == 'mismatch':
                pc[row['param']] += 1
    return {
        'generated': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'total': total,
        'passing': passing,
        'failing': total - passing,
        'params_per_scenario': params_per_scenario,
        'param_mismatches': pc.most_common(),
        'input_labels': INPUT_LABELS,
        'derived_params': pe.DERIVED_PARAMS,
        'helper_params': sorted(pe.HELPER_PARAMS),
        'scenarios': scenarios,
    }


HTML = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Panel Validation Dashboard</title>
<style>
  :root{--bg:#10141a;--card:#1a2027;--border:#2a3340;--text:#e6ebf1;--muted:#8b98a8;
    --green:#34c07a;--red:#e5534b;--amber:#e3a008;--blue:#4a9eda;}
  *{box-sizing:border-box;margin:0}
  body{background:var(--bg);color:var(--text);font:14px/1.45 "Segoe UI",system-ui,sans-serif;padding:22px}
  .wrap{max-width:1180px;margin:0 auto}
  h1{font-size:20px;font-weight:650}
  .sub{color:var(--muted);font-size:12.5px;margin-top:3px}
  .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:11px;margin:18px 0}
  .card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:13px 15px}
  .card .label{color:var(--muted);font-size:11.5px;text-transform:uppercase;letter-spacing:.05em}
  .card .value{font-size:25px;font-weight:650;margin-top:4px}
  .value.good{color:var(--green)}.value.bad{color:var(--red)}
  h2{font-size:13.5px;color:var(--muted);margin:20px 0 9px;text-transform:uppercase;letter-spacing:.05em}
  .aggwrap{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:6px 14px}
  .agg{display:flex;align-items:center;gap:10px;padding:6px 0;border-top:1px solid var(--border)}
  .agg:first-child{border-top:0}
  .agg .bar{height:8px;background:var(--red);border-radius:4px;min-width:2px}
  .agg .pn{font-family:ui-monospace,monospace;font-size:12.5px;min-width:230px}
  .agg .ct{color:var(--muted);font-size:12px}
  .controls{display:flex;gap:8px;margin:14px 0;flex-wrap:wrap}
  button{border:1px solid var(--border);background:var(--card);color:var(--text);border-radius:7px;
    padding:7px 13px;font-size:13px;cursor:pointer}
  button.active{background:var(--blue);color:#08121c;border-color:var(--blue);font-weight:600}
  .scn{background:var(--card);border:1px solid var(--border);border-radius:9px;margin-bottom:7px;overflow:hidden}
  .scn .hd{display:flex;align-items:center;gap:12px;padding:11px 14px;cursor:pointer}
  .scn .hd:hover{background:#20272f}
  .badge{padding:3px 10px;border-radius:999px;font-weight:650;font-size:12px}
  .badge.pass{background:#14351f;color:var(--green)}
  .badge.fail{background:#3a1715;color:var(--red)}
  .scid{font-family:ui-monospace,monospace;font-weight:600;min-width:120px}
  .hd .meta{color:var(--muted);font-size:12.5px;flex:1}
  .hd .chev{color:var(--muted)}
  .body{display:none;padding:4px 14px 14px;border-top:1px solid var(--border)}
  .scn.open .body{display:block}
  .inputs{display:flex;flex-wrap:wrap;gap:6px 16px;padding:10px 0;color:var(--muted);font-size:12.5px}
  .inputs b{color:var(--text);font-weight:600}
  table{width:100%;border-collapse:collapse;font-size:13px}
  th,td{text-align:left;padding:6px 10px}
  th{color:var(--muted);font-weight:600;font-size:11.5px;text-transform:uppercase;letter-spacing:.04em}
  tr+tr td{border-top:1px solid #232b34}
  td.param{font-family:ui-monospace,monospace}
  td.kind{color:var(--muted);font-size:11.5px;text-transform:uppercase;letter-spacing:.04em}
  td.num{text-align:right;font-variant-numeric:tabular-nums}
  .st{padding:2px 8px;border-radius:5px;font-size:11.5px;font-weight:600}
  .st.match{background:#14351f;color:var(--green)}
  .st.mismatch{background:#3a1715;color:var(--red)}
  .st.empty{background:#242c34;color:var(--muted)}
  .st.na{background:#242c34;color:var(--muted)}
  tr.mismatch td{background:#2a1614}
  .footer{color:var(--muted);font-size:12px;margin-top:18px}
</style></head><body><div class="wrap">
  <h1>Panel Validation Dashboard</h1>
  <div class="sub" id="sub"></div>
  <div class="grid" id="cards"></div>
  <h2>Mismatches by parameter</h2>
  <div class="aggwrap" id="agg"></div>
  <h2>Scenarios</h2>
  <div class="controls">
    <button data-f="fail" class="active">Failing only</button>
    <button data-f="all">All</button>
    <button data-f="pass">Passing</button>
  </div>
  <div id="list"></div>
  <div class="footer" id="footer"></div>
</div>
<script>
const DATA = __DATA__;
let filter = DATA.failing > 0 ? 'fail' : 'all';

function card(label,val,cls){return `<div class="card"><div class="label">${label}</div><div class="value ${cls||''}">${val}</div></div>`}

function renderTop(){
  document.getElementById('sub').textContent =
    `Expected values recomputed from each scenario's inputs via the Panel Calculated Values logic — ValidationOutputs sheet NOT used. Generated ${DATA.generated}.`;
  const passPct = DATA.total? Math.round(100*DATA.passing/DATA.total):0;
  document.getElementById('cards').innerHTML =
    card('Scenarios', DATA.total) +
    card('Passing', `${DATA.passing} (${passPct}%)`, 'good') +
    card('Failing', DATA.failing, DATA.failing?'bad':'good') +
    card('Params checked / scenario', DATA.params_per_scenario);
  const maxc = DATA.param_mismatches.length? DATA.param_mismatches[0][1]:1;
  document.getElementById('agg').innerHTML = DATA.param_mismatches.length
    ? DATA.param_mismatches.map(([p,n])=>
        `<div class="agg"><span class="pn">${p}</span><span class="bar" style="width:${Math.round(240*n/maxc)}px"></span><span class="ct">${n}</span></div>`).join('')
    : '<div class="agg"><span class="ct">No mismatches — every checked parameter matches expected.</span></div>';
}

function renderList(){
  const scns = DATA.scenarios.filter(s=> filter==='all' ? true : filter==='fail' ? !s.ok : s.ok);
  document.getElementById('list').innerHTML = scns.map(s=>{
    const c = s.counts||{};
    const inputs = DATA.input_labels.map(([k,lbl])=>`${lbl}=<b>${(s.inputs[k]??'—')}</b>`).join(' · ');
    const rows = (s.rows||[]).map(r=>`<tr class="${r.status}">
        <td class="param">${r.param}</td>
        <td class="kind">${r.kind}</td>
        <td class="num">${r.expected}</td>
        <td class="num">${r.actual}</td>
        <td><span class="st ${r.status}">${r.status}</span></td></tr>`).join('');
    const meta = s.error ? `<span style="color:var(--red)">error: ${s.error}</span>`
        : `${c.match||0} match · ${c.mismatch||0} mismatch · ${c.empty||0} empty · ${c.na||0} n/a`;
    return `<div class="scn ${s.ok?'':'open'}">
      <div class="hd" onclick="this.parentNode.classList.toggle('open')">
        <span class="badge ${s.ok?'pass':'fail'}">${s.ok?'PASS':'FAIL'}</span>
        <span class="scid">${s.scenario}</span>
        <span class="meta">${meta}</span>
        <span class="chev">▾</span>
      </div>
      <div class="body">
        <div class="inputs">${inputs}</div>
        <table><thead><tr><th>parameter</th><th>kind</th><th style="text-align:right">expected</th><th style="text-align:right">actual</th><th>status</th></tr></thead>
        <tbody>${rows}</tbody></table>
      </div></div>`;
  }).join('') || '<div class="card">No scenarios in this view.</div>';
  document.getElementById('footer').textContent =
    `Showing ${scns.length} of ${DATA.total} scenarios. Helper params (${DATA.helper_params.join(', ')}) are not model outputs and show as n/a.`;
}

document.querySelectorAll('.controls button').forEach(b=>b.onclick=()=>{
  filter=b.dataset.f;
  document.querySelectorAll('.controls button').forEach(x=>x.classList.toggle('active',x===b));
  renderList();
});
document.querySelectorAll('.controls button').forEach(b=>b.classList.toggle('active', b.dataset.f===filter));
renderTop(); renderList();
</script></body></html>
"""


def main():
    payload = build_payload()
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(__file__), 'validation_dashboard.html')
    html = HTML.replace('__DATA__', json.dumps(payload))
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'Wrote {out}')
    print(f'  {payload["passing"]}/{payload["total"]} scenarios pass '
          f'({payload["failing"]} failing)')
    if payload['param_mismatches']:
        print('  mismatching params:',
              ', '.join(f'{p}({n})' for p, n in payload['param_mismatches']))


if __name__ == '__main__':
    main()
