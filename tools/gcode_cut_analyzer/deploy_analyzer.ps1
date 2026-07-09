<#
.SYNOPSIS
    Self-contained deployment script for the G-Code Cut Length Analyzer.
    Creates all files, opens the firewall port, and starts the web server.

.DESCRIPTION
    Run this script on any Windows machine with Python 3 installed.
    It will:
      1. Create C:\GCodeAnalyzer\ with the HTML app and serve script
      2. Add a Windows Firewall inbound rule for port 8080
      3. Start the HTTP server on 0.0.0.0:8080
    
    Anyone on the same network can then access the analyzer at:
      http://<THIS_MACHINE_IP>:8080

.NOTES
    - Requires admin privileges (for firewall rule)
    - Requires Python 3 installed and on PATH
    - Each visitor gets their own independent session (client-side processing)
    - Press Ctrl+C to stop the server
#>

# --- Configuration ---
$InstallDir = "C:\GCodeAnalyzer"
$Port = 8080

# --- Ensure running as admin ---
if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Re-launching as Administrator..." -ForegroundColor Yellow
    Start-Process powershell.exe "-ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

# --- Create install directory ---
if (!(Test-Path $InstallDir)) { New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null }

Write-Host "Installing G-Code Cut Length Analyzer to $InstallDir..." -ForegroundColor Cyan

# --- Write index.html ---
$htmlContent = @'
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>G-Code Cut Length Analyzer</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://unpkg.com/lucide@latest"></script>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
    body { font-family: 'Inter', sans-serif; }
    .mono { font-family: 'JetBrains Mono', monospace; }
    .drop-zone.drag-over { border-color: #6366f1; background: rgba(99,102,241,0.06); }
    .fade-in { animation: fadeIn 0.3s ease-out; }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
    canvas { image-rendering: auto; }
  </style>
</head>
<body class="bg-gray-950 text-gray-100 min-h-screen">

  <!-- Header -->
  <header class="border-b border-gray-800 bg-gray-950/80 backdrop-blur sticky top-0 z-50">
    <div class="max-w-6xl mx-auto px-6 py-4 flex items-center gap-3">
      <div class="w-9 h-9 rounded-lg bg-indigo-600 flex items-center justify-center">
        <i data-lucide="ruler" class="w-5 h-5 text-white"></i>
      </div>
      <div>
        <h1 class="text-lg font-semibold">G-Code Cut Length Analyzer</h1>
        <p class="text-xs text-gray-500">Determine material cut lengths from CNC G-code</p>
      </div>
    </div>
  </header>

  <main class="max-w-6xl mx-auto px-6 py-8 space-y-8">

    <!-- Config + Drop Zone Row -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">

      <!-- Tool Config -->
      <div class="bg-gray-900 rounded-xl border border-gray-800 p-5 space-y-4">
        <div class="flex items-center gap-2 text-sm font-medium text-gray-300">
          <i data-lucide="settings" class="w-4 h-4 text-gray-500"></i>
          Tool Configuration
        </div>
        <div>
          <label class="block text-xs text-gray-500 mb-1">Tool Diameter (inches)</label>
          <input id="toolDiameter" type="number" step="0.001" value="0.5"
            class="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm mono focus:outline-none focus:ring-2 focus:ring-indigo-500" />
        </div>
        <div class="text-xs text-gray-600 flex items-start gap-1.5 pt-1">
          <i data-lucide="info" class="w-3.5 h-3.5 mt-0.5 shrink-0"></i>
          <span>Tool radius is used to determine when the tool edge enters/exits the material boundary. Material edge is at Y&nbsp;=&nbsp;0; tool center at Y&nbsp;=&nbsp;-radius is fully engaged.</span>
        </div>
      </div>

      <!-- Drop Zone -->
      <div class="lg:col-span-2">
        <div id="dropZone"
          class="drop-zone border-2 border-dashed border-gray-700 rounded-xl p-10 flex flex-col items-center justify-center gap-3 cursor-pointer transition-all hover:border-gray-600">
          <i data-lucide="upload" class="w-10 h-10 text-gray-600"></i>
          <p class="text-sm text-gray-400">Drop a G-code file here or <span class="text-indigo-400 underline">browse</span></p>
          <p class="text-xs text-gray-600">Supports .txt and .nc files</p>
          <input id="fileInput" type="file" accept=".txt,.nc" class="hidden" />
        </div>
        <div id="fileInfo" class="hidden mt-3 bg-gray-900 rounded-lg border border-gray-800 px-4 py-3 flex items-center gap-3">
          <i data-lucide="file-text" class="w-5 h-5 text-indigo-400 shrink-0"></i>
          <div class="min-w-0 flex-1">
            <p id="fileName" class="text-sm font-medium truncate"></p>
            <p id="fileSize" class="text-xs text-gray-500"></p>
          </div>
          <button id="clearFile" class="text-gray-500 hover:text-gray-300 transition">
            <i data-lucide="x" class="w-4 h-4"></i>
          </button>
        </div>
      </div>
    </div>

    <!-- Results -->
    <div id="results" class="hidden space-y-6 fade-in">

      <!-- Summary Cards -->
      <div id="summaryCards" class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4"></div>

      <!-- Operations Table -->
      <div class="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
        <div class="px-5 py-4 border-b border-gray-800 flex items-center gap-2">
          <i data-lucide="list" class="w-4 h-4 text-gray-500"></i>
          <span class="text-sm font-medium text-gray-300">Operations Breakdown</span>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead class="bg-gray-800/50 text-gray-400 text-xs uppercase tracking-wider">
              <tr>
                <th class="text-left px-5 py-3">Operation</th>
                <th class="text-left px-5 py-3">Work Offset</th>
                <th class="text-right px-5 py-3">Total Path</th>
                <th class="text-right px-5 py-3">Lead-In</th>
                <th class="text-right px-5 py-3">Cut on Material</th>
                <th class="text-right px-5 py-3">Lead-Out</th>
                <th class="text-right px-5 py-3">Segments</th>
              </tr>
            </thead>
            <tbody id="opsTableBody" class="divide-y divide-gray-800"></tbody>
          </table>
        </div>
      </div>

      <!-- Visualization -->
      <div class="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
        <div class="px-5 py-4 border-b border-gray-800 flex items-center justify-between">
          <div class="flex items-center gap-2">
            <i data-lucide="eye" class="w-4 h-4 text-gray-500"></i>
            <span class="text-sm font-medium text-gray-300">Toolpath Visualization</span>
          </div>
          <div class="flex items-center gap-4 text-xs text-gray-500">
            <span class="flex items-center gap-1.5"><span class="w-3 h-1 rounded bg-yellow-500 inline-block"></span> Rapid (G0)</span>
            <span class="flex items-center gap-1.5"><span class="w-3 h-1 rounded bg-red-400 inline-block"></span> Lead-in/out</span>
            <span class="flex items-center gap-1.5"><span class="w-3 h-1 rounded bg-emerald-400 inline-block"></span> Cutting on material</span>
            <span class="flex items-center gap-1.5"><span class="w-2 h-2 rounded border border-cyan-400 inline-block"></span> Material bounds (X=0, X=sheet)</span>
          </div>
        </div>
        <div class="p-4">
          <canvas id="vizCanvas" class="w-full rounded-lg bg-gray-950" height="400"></canvas>
        </div>
      </div>

      <!-- Raw G-code with annotations -->
      <div class="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
        <div class="px-5 py-4 border-b border-gray-800 flex items-center gap-2">
          <i data-lucide="code" class="w-4 h-4 text-gray-500"></i>
          <span class="text-sm font-medium text-gray-300">Annotated G-Code</span>
        </div>
        <div id="annotatedCode" class="p-5 overflow-x-auto max-h-96 overflow-y-auto mono text-xs leading-6 whitespace-pre"></div>
      </div>
    </div>
  </main>

<script>
// --- G-Code Parser & Analyzer ---

function parseGCode(text, toolDiameter) {
  const toolRadius = toolDiameter / 2;
  const lines = text.split(/\r?\n/);
  const operations = [];
  let currentOp = null;
  let currentWorkOffset = '';
  let x = 0, y = 0, z = 0;
  let activeGCode = null;
  const lineAnnotations = [];

  let sheetX = null, sheetY = null;
  for (const line of lines) {
    const mx = line.match(/#527\s*=\s*([\d.]+)/);
    if (mx) sheetX = parseFloat(mx[1]);
    const my = line.match(/#528\s*=\s*([\d.]+)/);
    if (my) sheetY = parseFloat(my[1]);
    if (sheetX !== null && sheetY !== null) break;
  }

  function getMaterialBounds(workOffset) {
    if (sheetX === null) return null;
    if (workOffset === 'G59') return { lo: -sheetX, hi: 0 };
    return { lo: 0, hi: sheetX };
  }

  function xOnMaterial(xVal, workOffset) {
    const bounds = getMaterialBounds(workOffset);
    if (!bounds) return true;
    return xVal >= bounds.lo && xVal <= bounds.hi;
  }

  function xMaterialDist(x1, x2, workOffset) {
    const bounds = getMaterialBounds(workOffset);
    if (!bounds) return Math.abs(x2 - x1);
    const lo = Math.min(x1, x2);
    const hi = Math.max(x1, x2);
    const clampLo = Math.max(lo, bounds.lo);
    const clampHi = Math.min(hi, bounds.hi);
    if (clampHi <= clampLo) return 0;
    return clampHi - clampLo;
  }

  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i].trim();
    lineAnnotations.push({ line: lines[i], annotation: '', cls: '' });

    const opMatch = raw.match(/^\(([A-Z][A-Z0-9 _/-]+)\)$/);
    if (opMatch && !raw.includes('MACHINE') && !raw.includes('VENDOR') && !raw.includes('MODEL')
        && !raw.includes('DESCRIPTION') && !raw.includes('T001') && !raw.includes('SHEET')
        && !raw.includes('NEW SETUP') && !raw.includes('****')) {
      if (currentOp) operations.push(currentOp);
      currentOp = {
        name: opMatch[1].trim(),
        workOffset: currentWorkOffset,
        segments: [],
        totalPath: 0,
        leadIn: 0,
        cutOnMaterial: 0,
        leadOut: 0,
        startLine: i,
      };
      lineAnnotations[i].cls = 'text-indigo-400 font-semibold';
      continue;
    }

    if (raw.match(/^M30\b/) || raw.match(/^M0\b/) || raw.match(/^N\d+\s+M30\b/)) {
      activeGCode = null;
    }

    if (!raw.match(/^N\d+/) && !raw.match(/^G\d+/) && !raw.match(/^M\d+/)) continue;

    const tokens = raw.replace(/^N\d+\s*/, '').split(/\s+/);
    let lineHasMotionG = false;
    let params = {};
    for (const tok of tokens) {
      const m = tok.match(/^([A-Z])(-?[\d.]+)/);
      if (m) {
        const letter = m[1];
        const val = parseFloat(m[2]);
        if (letter === 'G' && (val === 0 || val === 1 || val === 2 || val === 3)) {
          activeGCode = val;
          lineHasMotionG = true;
        } else if (letter === 'G' && (val === 57 || val === 59)) {
          currentWorkOffset = 'G' + val;
          if (currentOp) currentOp.workOffset = currentWorkOffset;
        } else if (letter === 'G' && (val === 43 || val === 17 || val === 90 || val === 94
                   || val === 20 || val === 21 || val === 28 || val === 49 || val === 8
                   || val === 91)) {
          // Non-motion G codes
        }
        params[letter] = val;
      }
    }

    if (raw.includes('G28')) continue;

    const hasCoords = 'X' in params || 'Y' in params || 'Z' in params;
    const effectiveGCode = lineHasMotionG ? activeGCode : (hasCoords ? activeGCode : null);

    if (effectiveGCode !== null && currentOp) {
      const gCode = effectiveGCode;
      const prevX = x, prevY = y, prevZ = z;

      if ('X' in params) x = params['X'];
      if ('Y' in params) y = params['Y'];
      if ('Z' in params) z = params['Z'];

      if (gCode === 0) {
        lineAnnotations[i].annotation = 'rapid -> (' + x.toFixed(4) + ', ' + y.toFixed(4) + ', ' + z.toFixed(4) + ')';
        lineAnnotations[i].cls = 'text-yellow-600';
        currentOp.segments.push({
          type: 'rapid', gCode: 0,
          x1: prevX, y1: prevY, z1: prevZ,
          x2: x, y2: y, z2: z,
          dist: 0, onMaterial: false, classification: 'rapid',
        });
      } else if (gCode === 1) {
        const dx = x - prevX;
        const dy = y - prevY;
        const dz = z - prevZ;
        const dist = Math.sqrt(dx*dx + dy*dy + dz*dz);

        const atCutZ = z <= 0.5;
        const prevAtCutZ = prevZ <= 0.5;
        const hasXYMove = Math.abs(dx) > 0.0001 || Math.abs(dy) > 0.0001;
        const isCutMove = atCutZ && prevAtCutZ && hasXYMove;

        let matDist = 0;
        let classification = 'plunge';

        if (isCutMove) {
          const absDx = Math.abs(dx);
          const absDy = Math.abs(dy);
          const isRamp = absDy > 0.01 && absDx > 0.001;

          if (isRamp || absDx < 0.0001) {
            matDist = 0;
            classification = 'lead';
          } else {
            matDist = xMaterialDist(prevX, x, currentWorkOffset);
            if (matDist > absDx * 0.999) {
              classification = 'material';
            } else if (matDist > 0.001) {
              classification = 'partial';
            } else {
              classification = 'lead';
            }
          }
        }

        const seg = {
          type: 'linear', gCode: 1,
          x1: prevX, y1: prevY, z1: prevZ,
          x2: x, y2: y, z2: z,
          dist, matDist, onMaterial: matDist > 0.001, classification,
        };
        currentOp.segments.push(seg);
        currentOp.totalPath += dist;

        if (classification === 'material') {
          currentOp.cutOnMaterial += matDist;
          lineAnnotations[i].cls = 'text-emerald-400';
          lineAnnotations[i].annotation = 'cut ' + matDist.toFixed(4) + '" ON MATERIAL';
        } else if (classification === 'partial') {
          currentOp.cutOnMaterial += matDist;
          lineAnnotations[i].cls = 'text-amber-400';
          lineAnnotations[i].annotation = 'partial ' + matDist.toFixed(4) + '" on material / ' + (dist-matDist).toFixed(4) + '" off';
        } else if (classification === 'lead') {
          lineAnnotations[i].cls = 'text-red-400';
          lineAnnotations[i].annotation = 'lead ' + dist.toFixed(4) + '"';
        } else {
          lineAnnotations[i].cls = 'text-gray-500';
          lineAnnotations[i].annotation = 'plunge/retract ' + dist.toFixed(4) + '"';
        }

      } else if (gCode === 2 || gCode === 3) {
        const I = params['I'] || 0;
        const J = params['J'] || 0;
        const cx = prevX + I;
        const cy = prevY + J;
        const r = Math.sqrt(I*I + J*J);

        const startAngle = Math.atan2(prevY - cy, prevX - cx);
        const endAngle = Math.atan2(y - cy, x - cx);

        let sweep;
        if (gCode === 3) {
          sweep = endAngle - startAngle;
          if (sweep <= 0) sweep += 2 * Math.PI;
        } else {
          sweep = startAngle - endAngle;
          if (sweep <= 0) sweep += 2 * Math.PI;
        }
        const arcLen = r * Math.abs(sweep);

        const rFeature = r + toolRadius;
        const sinVal = -cy / rFeature;
        let featureXOnMaterial = 0;
        let matArcXDist = 0;
        let matArcPathLen = 0;

        if (Math.abs(sinVal) <= 1) {
          const aIntersect = Math.asin(sinVal);
          const xInt1 = cx + rFeature * Math.cos(aIntersect);
          const xInt2 = cx + rFeature * Math.cos(Math.PI - aIntersect);

          const arcMinX = Math.min(prevX, x);
          const arcMaxX = Math.max(prevX, x);

          let featureEndX = null;
          for (const xi of [xInt1, xInt2]) {
            if (xi >= arcMinX - toolRadius - 0.5 && xi <= arcMaxX + toolRadius + 0.5) {
              featureEndX = xi;
              break;
            }
          }

          if (featureEndX !== null) {
            const bounds = getMaterialBounds(currentWorkOffset);
            if (bounds) {
              const fxClamped = Math.max(bounds.lo, Math.min(bounds.hi, featureEndX));
              const startXClamped = Math.max(bounds.lo, Math.min(bounds.hi, prevX));
              const endXClamped = Math.max(bounds.lo, Math.min(bounds.hi, x));

              const d1 = Math.abs(fxClamped - startXClamped);
              const d2 = Math.abs(fxClamped - endXClamped);
              matArcXDist = Math.max(d1, d2);
            }
          }
        }

        const SAMPLES = 200;
        for (let s = 0; s < SAMPLES; s++) {
          const t1 = s / SAMPLES;
          const t2 = (s + 1) / SAMPLES;
          let a1, a2;
          if (gCode === 3) {
            a1 = startAngle + sweep * t1;
            a2 = startAngle + sweep * t2;
          } else {
            a1 = startAngle - sweep * t1;
            a2 = startAngle - sweep * t2;
          }
          const sx1 = cx + r * Math.cos(a1);
          const sx2 = cx + r * Math.cos(a2);
          const sy1 = cy + r * Math.sin(a1);
          const sy2 = cy + r * Math.sin(a2);
          const segPathDist = Math.sqrt((sx2-sx1)**2 + (sy2-sy1)**2);
          const midX = (sx1 + sx2) / 2;
          if (xOnMaterial(midX, currentWorkOffset)) {
            matArcPathLen += segPathDist;
          }
        }

        const seg = {
          type: 'arc', gCode,
          x1: prevX, y1: prevY, z1: prevZ,
          x2: x, y2: y, z2: z,
          cx, cy, r, startAngle, endAngle, sweep,
          dist: arcLen, matDist: matArcXDist, matPathLen: matArcPathLen,
          onMaterial: matArcXDist > 0.001,
          classification: matArcPathLen > arcLen * 0.9 ? 'material' : matArcPathLen > 0.001 ? 'partial' : 'lead',
        };
        currentOp.segments.push(seg);
        currentOp.totalPath += arcLen;
        currentOp.cutOnMaterial += matArcXDist;

        const onMatPct = arcLen > 0 ? (matArcPathLen / arcLen * 100).toFixed(0) : 0;
        lineAnnotations[i].annotation = 'arc R' + r.toFixed(3) + '" len=' + arcLen.toFixed(4) + '" (X on mat: ' + matArcXDist.toFixed(4) + '", path on mat: ' + matArcPathLen.toFixed(4) + '")';
        if (matArcPathLen > arcLen * 0.5) {
          lineAnnotations[i].cls = 'text-emerald-400';
        } else if (matArcPathLen > 0.001) {
          lineAnnotations[i].cls = 'text-amber-400';
        } else {
          lineAnnotations[i].cls = 'text-red-400';
        }
      }
    }
  }

  if (currentOp) operations.push(currentOp);

  for (const op of operations) {
    op.leadIn = 0;
    op.leadOut = 0;
    let firstMatIdx = -1, lastMatIdx = -1;

    for (let s = 0; s < op.segments.length; s++) {
      const seg = op.segments[s];
      if (seg.type === 'rapid' || seg.classification === 'plunge') continue;
      if (seg.classification === 'material' || seg.classification === 'partial') {
        if (firstMatIdx === -1) firstMatIdx = s;
        lastMatIdx = s;
      }
    }

    for (let s = 0; s < op.segments.length; s++) {
      const seg = op.segments[s];
      if (seg.type === 'rapid' || seg.classification === 'plunge') continue;
      if (seg.classification === 'material' || seg.classification === 'partial') continue;
      if (firstMatIdx === -1) {
        op.leadIn += seg.dist;
      } else if (s < firstMatIdx) {
        op.leadIn += seg.dist;
      } else if (s > lastMatIdx) {
        op.leadOut += seg.dist;
      }
    }

    for (let s = 0; s < op.segments.length; s++) {
      const seg = op.segments[s];
      if (seg.classification === 'partial') {
        const offMat = seg.dist - seg.matDist;
        if (s === firstMatIdx) op.leadIn += offMat;
        else if (s === lastMatIdx) op.leadOut += offMat;
      }
    }
  }

  return { operations, lineAnnotations, sheetX, sheetY };
}

// --- Visualization ---

function drawVisualization(operations, sheetX, sheetY) {
  const canvas = document.getElementById('vizCanvas');
  const ctx = canvas.getContext('2d');

  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (const op of operations) {
    for (const seg of op.segments) {
      for (const [sx, sy] of [[seg.x1, seg.y1], [seg.x2, seg.y2]]) {
        minX = Math.min(minX, sx); maxX = Math.max(maxX, sx);
        minY = Math.min(minY, sy); maxY = Math.max(maxY, sy);
      }
      if (seg.type === 'arc') {
        minX = Math.min(minX, seg.cx - seg.r); maxX = Math.max(maxX, seg.cx + seg.r);
        minY = Math.min(minY, seg.cy - seg.r); maxY = Math.max(maxY, seg.cy + seg.r);
      }
    }
  }

  const margin = 60;
  const dpr = window.devicePixelRatio || 1;
  canvas.width = canvas.clientWidth * dpr;
  canvas.height = 400 * dpr;
  ctx.scale(dpr, dpr);
  const W = canvas.clientWidth;
  const H = 400;

  const rangeX = maxX - minX || 1;
  const rangeY = maxY - minY || 1;
  const scale = Math.min((W - margin*2) / rangeX, (H - margin*2) / rangeY);

  function tx(v) { return margin + (v - minX) * scale; }
  function ty(v) { return H - margin - (v - minY) * scale; }

  ctx.clearRect(0, 0, W, H);

  ctx.setLineDash([6, 4]);
  ctx.lineWidth = 1;
  ctx.font = '11px Inter';

  if (sheetX !== null) {
    const workOffsets = new Set();
    for (const op of operations) {
      if (op.workOffset) workOffsets.add(op.workOffset);
    }
    if (workOffsets.size === 0) workOffsets.add('G57');

    const drawn = new Set();
    for (const wo of workOffsets) {
      const lo = wo === 'G59' ? -sheetX : 0;
      const hi = wo === 'G59' ? 0 : sheetX;

      const loScreen = tx(lo);
      const hiScreen = tx(hi);

      ctx.fillStyle = 'rgba(34,211,238,0.03)';
      ctx.fillRect(Math.min(loScreen, hiScreen), margin, Math.abs(hiScreen - loScreen), H - margin*2);

      for (const [val, screen] of [[lo, loScreen], [hi, hiScreen]]) {
        const key = val.toFixed(3);
        if (drawn.has(key)) continue;
        drawn.add(key);
        ctx.strokeStyle = 'rgba(34,211,238,0.5)';
        ctx.beginPath();
        ctx.moveTo(screen, margin);
        ctx.lineTo(screen, H - margin);
        ctx.stroke();
        ctx.fillStyle = 'rgba(34,211,238,0.5)';
        ctx.fillText('X=' + val, screen + 4, margin + 14);
      }
    }
  }

  ctx.setLineDash([]);

  for (const op of operations) {
    for (const seg of op.segments) {
      if (seg.type === 'rapid') {
        ctx.strokeStyle = 'rgba(234,179,8,0.3)';
        ctx.lineWidth = 0.5;
        ctx.setLineDash([3, 3]);
      } else if (seg.classification === 'material') {
        ctx.strokeStyle = '#34d399';
        ctx.lineWidth = 2;
        ctx.setLineDash([]);
      } else if (seg.classification === 'partial') {
        ctx.strokeStyle = '#fbbf24';
        ctx.lineWidth = 1.5;
        ctx.setLineDash([]);
      } else {
        ctx.strokeStyle = '#f87171';
        ctx.lineWidth = 1.5;
        ctx.setLineDash([]);
      }

      ctx.beginPath();
      if (seg.type === 'arc') {
        const STEPS = 100;
        for (let s = 0; s <= STEPS; s++) {
          const t = s / STEPS;
          let a;
          if (seg.gCode === 3) {
            a = seg.startAngle + seg.sweep * t;
          } else {
            a = seg.startAngle - seg.sweep * t;
          }
          const px = seg.cx + seg.r * Math.cos(a);
          const py = seg.cy + seg.r * Math.sin(a);
          if (s === 0) ctx.moveTo(tx(px), ty(py));
          else ctx.lineTo(tx(px), ty(py));
        }
      } else {
        ctx.moveTo(tx(seg.x1), ty(seg.y1));
        ctx.lineTo(tx(seg.x2), ty(seg.y2));
      }
      ctx.stroke();
    }
  }

  ctx.setLineDash([]);
  ctx.fillStyle = '#6b7280';
  ctx.font = '10px Inter';
  const xStep = Math.pow(10, Math.floor(Math.log10(rangeX))) || 10;
  for (let v = Math.ceil(minX / xStep) * xStep; v <= maxX; v += xStep) {
    const sx = tx(v);
    ctx.fillText(v.toFixed(0), sx - 8, H - margin + 16);
    ctx.strokeStyle = 'rgba(75,85,99,0.3)';
    ctx.lineWidth = 0.5;
    ctx.beginPath(); ctx.moveTo(sx, margin); ctx.lineTo(sx, H - margin); ctx.stroke();
  }
  const yStep = Math.pow(10, Math.floor(Math.log10(rangeY))) || 1;
  for (let v = Math.ceil(minY / yStep) * yStep; v <= maxY; v += yStep) {
    const sy = ty(v);
    ctx.fillStyle = '#6b7280';
    ctx.fillText(v.toFixed(1), 4, sy + 4);
    ctx.strokeStyle = 'rgba(75,85,99,0.3)';
    ctx.lineWidth = 0.5;
    ctx.beginPath(); ctx.moveTo(margin, sy); ctx.lineTo(W - margin, sy); ctx.stroke();
  }

  ctx.fillStyle = '#9ca3af';
  ctx.font = '11px Inter';
  ctx.fillText('X (inches)', W / 2, H - 8);
  ctx.save();
  ctx.translate(14, H / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.fillText('Y (inches)', 0, 0);
  ctx.restore();
}

// --- UI Rendering ---

function renderResults(result, toolDiameter) {
  const { operations, lineAnnotations, sheetX, sheetY } = result;

  const cards = document.getElementById('summaryCards');
  const totalCut = operations.reduce((s, o) => s + o.cutOnMaterial, 0);
  const totalPath = operations.reduce((s, o) => s + o.totalPath, 0);
  const totalLeadIn = operations.reduce((s, o) => s + o.leadIn, 0);
  const totalLeadOut = operations.reduce((s, o) => s + o.leadOut, 0);

  cards.innerHTML = [
    { label: 'Cut on Material', value: totalCut.toFixed(3) + '"', icon: 'ruler', color: 'emerald' },
    { label: 'Total Toolpath', value: totalPath.toFixed(3) + '"', icon: 'move', color: 'blue' },
    { label: 'Total Lead-In', value: totalLeadIn.toFixed(3) + '"', icon: 'log-in', color: 'amber' },
    { label: 'Operations', value: operations.length, icon: 'layers', color: 'indigo' },
    ...(sheetX !== null ? [{ label: 'Material Length (X)', value: sheetX + '"', icon: 'move-horizontal', color: 'cyan' }] : []),
    ...(sheetY !== null ? [{ label: 'Material Width (Y)', value: sheetY + '"', icon: 'move-vertical', color: 'cyan' }] : []),
  ].map(c => '<div class="bg-gray-900 rounded-xl border border-gray-800 p-5"><div class="flex items-center gap-2 text-xs text-gray-500 mb-2"><i data-lucide="' + c.icon + '" class="w-3.5 h-3.5"></i>' + c.label + '</div><div class="text-2xl font-semibold text-' + c.color + '-400 mono">' + c.value + '</div></div>').join('');

  const tbody = document.getElementById('opsTableBody');
  tbody.innerHTML = operations.map(op => '<tr class="hover:bg-gray-800/50"><td class="px-5 py-3 font-medium">' + op.name + '</td><td class="px-5 py-3 mono text-gray-400">' + (op.workOffset || '\u2014') + '</td><td class="px-5 py-3 text-right mono">' + op.totalPath.toFixed(3) + '"</td><td class="px-5 py-3 text-right mono text-amber-400">' + op.leadIn.toFixed(3) + '"</td><td class="px-5 py-3 text-right mono text-emerald-400 font-semibold">' + op.cutOnMaterial.toFixed(3) + '"</td><td class="px-5 py-3 text-right mono text-amber-400">' + op.leadOut.toFixed(3) + '"</td><td class="px-5 py-3 text-right mono text-gray-400">' + op.segments.filter(s => s.type !== 'rapid').length + '</td></tr>').join('');

  tbody.innerHTML += '<tr class="bg-gray-800/30 font-semibold"><td class="px-5 py-3" colspan="2">TOTAL</td><td class="px-5 py-3 text-right mono">' + totalPath.toFixed(3) + '"</td><td class="px-5 py-3 text-right mono text-amber-400">' + totalLeadIn.toFixed(3) + '"</td><td class="px-5 py-3 text-right mono text-emerald-400">' + totalCut.toFixed(3) + '"</td><td class="px-5 py-3 text-right mono text-amber-400">' + totalLeadOut.toFixed(3) + '"</td><td class="px-5 py-3 text-right mono text-gray-400">' + operations.reduce((s, o) => s + o.segments.filter(x => x.type !== 'rapid').length, 0) + '</td></tr>';

  const codeDiv = document.getElementById('annotatedCode');
  codeDiv.innerHTML = lineAnnotations.map((la, i) => {
    const lineNum = '<span class="text-gray-600 select-none inline-block w-10 text-right mr-4">' + (i+1) + '</span>';
    const code = escapeHtml(la.line);
    const ann = la.annotation ? '  <span class="text-gray-600">// ' + escapeHtml(la.annotation) + '</span>' : '';
    return '<span class="' + (la.cls || 'text-gray-400') + '">' + lineNum + code + ann + '</span>';
  }).join('\n');

  drawVisualization(operations, sheetX, sheetY);
  document.getElementById('results').classList.remove('hidden');
  lucide.createIcons();
}

function escapeHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// --- File Handling ---

const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const fileInfo = document.getElementById('fileInfo');

function handleFile(file) {
  document.getElementById('fileName').textContent = file.name;
  document.getElementById('fileSize').textContent = (file.size / 1024).toFixed(1) + ' KB';
  fileInfo.classList.remove('hidden');

  const reader = new FileReader();
  reader.onload = (e) => {
    const toolDiameter = parseFloat(document.getElementById('toolDiameter').value) || 0.5;
    const result = parseGCode(e.target.result, toolDiameter);
    renderResults(result, toolDiameter);
  };
  reader.readAsText(file);
}

dropZone.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', (e) => { if (e.target.files[0]) handleFile(e.target.files[0]); });

dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('drag-over'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
dropZone.addEventListener('drop', (e) => {
  e.preventDefault();
  dropZone.classList.remove('drag-over');
  if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
});

document.getElementById('clearFile').addEventListener('click', () => {
  fileInput.value = '';
  fileInfo.classList.add('hidden');
  document.getElementById('results').classList.add('hidden');
});

document.getElementById('toolDiameter').addEventListener('change', () => {
  if (fileInput.files[0]) handleFile(fileInput.files[0]);
});

window.addEventListener('resize', () => {
  if (!document.getElementById('results').classList.contains('hidden')) {
    if (fileInput.files[0]) handleFile(fileInput.files[0]);
  }
});

lucide.createIcons();
</script>
</body>
</html>
'@

Set-Content -Path "$InstallDir\index.html" -Value $htmlContent -Encoding UTF8
Write-Host "  [OK] index.html" -ForegroundColor Green

# --- Write serve.py ---
$serveContent = @'
"""
Serve the G-Code Cut Length Analyzer on the local network.
Press Ctrl+C to stop.
"""
import http.server
import socketserver
import socket

PORT = 8080

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

if __name__ == "__main__":
    local_ip = get_local_ip()
    with socketserver.TCPServer(("0.0.0.0", PORT), QuietHandler) as httpd:
        print(f"G-Code Cut Length Analyzer")
        print(f"{'='*40}")
        print(f"  Local:   http://localhost:{PORT}")
        print(f"  Network: http://{local_ip}:{PORT}")
        print(f"{'='*40}")
        print(f"Share the Network URL with anyone on your WiFi.")
        print(f"Each person gets their own independent session.")
        print(f"Press Ctrl+C to stop.\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")
'@

Set-Content -Path "$InstallDir\serve.py" -Value $serveContent -Encoding UTF8
Write-Host "  [OK] serve.py" -ForegroundColor Green

# --- Open firewall port ---
Write-Host "`nConfiguring firewall..." -ForegroundColor Cyan
$existingRule = netsh advfirewall firewall show rule name="G-Code Analyzer HTTP" 2>$null
if ($existingRule -match "G-Code Analyzer HTTP") {
    Write-Host "  [OK] Firewall rule already exists" -ForegroundColor Green
} else {
    netsh advfirewall firewall add rule name="G-Code Analyzer HTTP" dir=in action=allow protocol=tcp localport=$Port | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [OK] Firewall rule added (port $Port)" -ForegroundColor Green
    } else {
        Write-Host "  [WARN] Could not add firewall rule. You may need to do this manually." -ForegroundColor Yellow
    }
}

# --- Start the server (pure PowerShell, no Python needed) ---
$localIP = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
    $_.IPAddress -ne '127.0.0.1' -and
    $_.IPAddress -notlike '169.254.*' -and
    $_.InterfaceAlias -notmatch 'Loopback'
} | Select-Object -First 1).IPAddress
if (-not $localIP) { $localIP = "127.0.0.1" }

Write-Host ""
Write-Host "G-Code Cut Length Analyzer" -ForegroundColor White
Write-Host ("=" * 40)
Write-Host "  Local:   http://localhost:$Port" -ForegroundColor Green
Write-Host "  Network: http://${localIP}:$Port" -ForegroundColor Green
Write-Host ("=" * 40)
Write-Host "Share the Network URL with anyone on your WiFi."
Write-Host "Each person gets their own independent session."
Write-Host "Press Ctrl+C to stop.`n"

$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add("http://+:$Port/")
$listener.Start()

try {
    while ($listener.IsListening) {
        $context = $listener.GetContext()
        $request = $context.Request
        $response = $context.Response

        $urlPath = $request.Url.LocalPath
        if ($urlPath -eq "/" -or $urlPath -eq "") { $urlPath = "/index.html" }

        $filePath = Join-Path $InstallDir ($urlPath.TrimStart("/"))

        if (Test-Path $filePath) {
            $bytes = [System.IO.File]::ReadAllBytes($filePath)
            $ext = [System.IO.Path]::GetExtension($filePath).ToLower()
            $contentType = switch ($ext) {
                ".html" { "text/html; charset=utf-8" }
                ".css"  { "text/css" }
                ".js"   { "application/javascript" }
                ".json" { "application/json" }
                ".png"  { "image/png" }
                ".svg"  { "image/svg+xml" }
                default { "application/octet-stream" }
            }
            $response.ContentType = $contentType
            $response.ContentLength64 = $bytes.Length
            $response.OutputStream.Write($bytes, 0, $bytes.Length)
        } else {
            $response.StatusCode = 404
            $msg = [System.Text.Encoding]::UTF8.GetBytes("Not Found")
            $response.OutputStream.Write($msg, 0, $msg.Length)
        }
        $response.Close()
    }
} finally {
    $listener.Stop()
    Write-Host "`nServer stopped." -ForegroundColor Yellow
}
