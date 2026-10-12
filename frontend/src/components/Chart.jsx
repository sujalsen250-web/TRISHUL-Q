import { useEffect, useRef } from "react";

// Lightweight hand-rolled canvas charts (no chart library, no ML).
const F = "11px 'JetBrains Mono', Consolas, monospace";
const COLORS = {
  ok: "#2fbf71", bad: "#e5484d", warn: "#e6a23c", info: "#4aa3e0",
  accent: "#5b6cff", cyan: "#2fb8d8", muted: "#93a0c0",
};

function useCanvas(draw, deps) {
  const ref = useRef(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.parentElement.getBoundingClientRect();
    const w = Math.max(80, rect.width), h = Math.max(80, rect.height);
    canvas.width = w * dpr; canvas.height = h * dpr;
    canvas.style.width = w + "px"; canvas.style.height = h + "px";
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    draw(ctx, w, h);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return ref;
}

function axes(ctx, w, h, maxV, padL = 42, padB = 24, padT = 26, padR = 12) {
  const cw = w - padL - padR, ch = h - padT - padB;
  ctx.strokeStyle = "rgba(147,160,192,.16)"; ctx.fillStyle = "#93a0c0";
  ctx.font = F; ctx.textAlign = "right";
  for (let i = 0; i <= 4; i++) {
    const y = padT + ch - (ch * i / 4);
    ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(w - padR, y); ctx.stroke();
    ctx.fillText((maxV * i / 4).toFixed(maxV <= 1 ? 2 : 0), padL - 6, y + 3);
  }
  return { cw, ch, padL, padB, padT, padR };
}

export function Line({ values = [], color = COLORS.cyan, max = null }) {
  const ref = useCanvas((ctx, w, h) => {
    const maxV = max ?? Math.max(1, ...values);
    const { cw, ch, padL, padT } = axes(ctx, w, h, maxV);
    if (!values.length) {
      ctx.textAlign = "center"; ctx.fillText("no data yet", w / 2, h / 2); return;
    }
    const step = values.length > 1 ? cw / (values.length - 1) : 0;
    const px = (i) => padL + step * i;
    const py = (v) => padT + ch - (v / (maxV || 1)) * ch;
    ctx.beginPath(); ctx.moveTo(px(0), padT + ch);
    values.forEach((v, i) => ctx.lineTo(px(i), py(v)));
    ctx.lineTo(px(values.length - 1), padT + ch); ctx.closePath();
    ctx.fillStyle = color + "22"; ctx.fill();
    ctx.beginPath();
    values.forEach((v, i) => (i ? ctx.lineTo(px(i), py(v)) : ctx.moveTo(px(i), py(v))));
    ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.stroke();
  }, [JSON.stringify(values), color, max]);
  return <canvas ref={ref} />;
}

export function MultiLine({ labels = [], series = [] }) {
  const ref = useCanvas((ctx, w, h) => {
    const maxV = 1;
    const { cw, ch, padL, padT, padR } = axes(ctx, w, h, maxV);
    // legend
    ctx.font = F; ctx.textAlign = "left";
    let lx = padL;
    series.forEach((s) => {
      ctx.fillStyle = s.color; ctx.fillRect(lx, padT - 18, 9, 9);
      ctx.fillStyle = "#93a0c0"; ctx.fillText(s.label, lx + 13, padT - 10);
      lx += 13 + ctx.measureText(s.label).width + 14;
    });
    if (!labels.length) { ctx.textAlign = "center"; ctx.fillText("no data yet", w / 2, h / 2); return; }
    const step = labels.length > 1 ? cw / (labels.length - 1) : 0;
    const px = (i) => padL + step * i;
    const py = (v) => padT + ch - (v / (maxV || 1)) * ch;
    series.forEach((s) => {
      ctx.beginPath();
      s.data.forEach((v, i) => (i ? ctx.lineTo(px(i), py(v)) : ctx.moveTo(px(i), py(v))));
      ctx.strokeStyle = s.color; ctx.lineWidth = 1.8; ctx.stroke();
    });
    ctx.fillStyle = "#93a0c0"; ctx.textAlign = "center";
    labels.forEach((l, i) => { if (i % 2 === 0) ctx.fillText(String(l), px(i), h - 6); });
    void padR;
  }, [JSON.stringify(labels), JSON.stringify(series)]);
  return <canvas ref={ref} />;
}

export function Bars({ labels = [], series = [] }) {
  const ref = useCanvas((ctx, w, h) => {
    const maxV = Math.max(1, ...series.flatMap((s) => s.data));
    const { cw, ch, padL, padT } = axes(ctx, w, h, maxV);
    if (!labels.length || !series.length) { ctx.textAlign = "center"; ctx.fillText("no data yet", w / 2, h / 2); return; }
    const groupW = cw / labels.length;
    const barW = Math.min(28, (groupW * 0.7) / series.length);
    labels.forEach((lab, i) => {
      const gx = padL + groupW * i + groupW / 2;
      series.forEach((s, j) => {
        const v = s.data[i] || 0, bh = (v / maxV) * ch;
        ctx.fillStyle = s.color;
        ctx.fillRect(gx - (barW * series.length) / 2 + j * barW + 1,
          padT + ch - bh, barW - 2, Math.max(0, bh));
      });
      ctx.fillStyle = "#93a0c0"; ctx.textAlign = "center";
      ctx.fillText(String(lab).slice(0, 12), gx, h - 7);
    });
  }, [JSON.stringify(labels), JSON.stringify(series)]);
  return <canvas ref={ref} />;
}

export { COLORS };
