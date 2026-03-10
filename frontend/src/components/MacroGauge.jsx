import React from 'react';

function GaugeSvg({ score, size = 200 }) {
  const normalized = Math.max(-1, Math.min(1, score || 0));
  const angle = -90 + (normalized + 1) * 90;
  const cx = size / 2;
  const cy = size / 2;
  const radius = size * 0.4;
  const needleLen = radius * 0.85;

  const angleRad = (angle * Math.PI) / 180;
  const nx = cx + needleLen * Math.cos(angleRad);
  const ny = cy + needleLen * Math.sin(angleRad);

  const arcRadius = radius;
  const startAngle = -180;
  const endAngle = 0;

  function polarToCart(cx, cy, r, deg) {
    const rad = (deg * Math.PI) / 180;
    return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
  }

  const s = polarToCart(cx, cy, arcRadius, startAngle);
  const e = polarToCart(cx, cy, arcRadius, endAngle);

  return (
    <svg width={size} height={size * 0.6} viewBox={`0 0 ${size} ${size * 0.6}`}>
      <defs>
        <linearGradient id="gaugeGradient" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#f43f5e" />
          <stop offset="25%" stopColor="#fb923c" />
          <stop offset="50%" stopColor="#3b82f6" />
          <stop offset="75%" stopColor="#22d3ee" />
          <stop offset="100%" stopColor="#10b981" />
        </linearGradient>
      </defs>
      <path
        d={`M ${s.x} ${s.y} A ${arcRadius} ${arcRadius} 0 0 1 ${e.x} ${e.y}`}
        fill="none"
        stroke="url(#gaugeGradient)"
        strokeWidth={12}
        strokeLinecap="round"
      />
      <line
        x1={cx} y1={cy} x2={nx} y2={ny}
        stroke="#e2e8f0" strokeWidth={2.5} strokeLinecap="round"
      />
      <circle cx={cx} cy={cy} r={4} fill="#e2e8f0" />
      <text x={8} y={cy + 20} fill="#f43f5e" fontSize={10} fontWeight="bold">FEAR</text>
      <text x={size - 48} y={cy + 20} fill="#10b981" fontSize={10} fontWeight="bold">GREED</text>
    </svg>
  );
}

function MiniBar({ label, value }) {
  const pct = Math.max(0, Math.min(100, (value || 0) * 100));
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-slate-400 w-24 truncate">{label}</span>
      <div className="flex-1 h-1.5 bg-slate-700 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full bg-blue-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-slate-300 w-10 text-right">{value != null ? Number(value).toFixed(2) : '—'}</span>
    </div>
  );
}

export default function MacroGauge({ macro, large = false }) {
  if (!macro) {
    return (
      <div className="bg-slate-800 rounded-xl border border-slate-700 p-6">
        <h2 className="text-lg font-semibold text-white mb-4">Macro Regime</h2>
        <p className="text-slate-400 text-center py-4">No macro data available</p>
      </div>
    );
  }

  const score = macro.regime_score != null ? (Number(macro.regime_score) * 2 - 1) : 0;
  const gaugeSize = large ? 300 : 200;

  const indicators = [
    { label: 'S&P 500 Trend', value: macro.sp500_trend },
    { label: 'VIX Level', value: macro.vix_level },
    { label: 'Yield Curve', value: macro.yield_curve_spread },
    { label: 'Market RSI', value: macro.market_rsi },
    { label: 'Breadth', value: macro.market_breadth },
    { label: 'Put/Call', value: macro.put_call_ratio },
    { label: 'Sentiment', value: macro.macro_news_sentiment },
  ];

  const regimeColors = {
    EXTREME_GREED: 'text-emerald-400',
    GREED: 'text-emerald-400',
    NEUTRAL: 'text-blue-400',
    FEAR: 'text-rose-400',
    EXTREME_FEAR: 'text-rose-400',
  };

  return (
    <div className={large ? '' : 'bg-slate-800 rounded-xl border border-slate-700 p-6'}>
      {!large && <h2 className="text-lg font-semibold text-white mb-4">Macro Regime</h2>}
      <div className="flex flex-col items-center">
        <GaugeSvg score={score} size={gaugeSize} />
        <p className={`text-lg font-bold mt-2 ${regimeColors[macro.regime] || 'text-slate-300'}`}>
          {macro.regime || 'UNKNOWN'}
        </p>
        <p className="text-sm text-slate-400">
          Score: {macro.regime_score != null ? Number(macro.regime_score).toFixed(4) : '—'}
        </p>
      </div>
      <div className="mt-4 space-y-2">
        {indicators.map((ind) => (
          <MiniBar key={ind.label} label={ind.label} value={ind.value} />
        ))}
      </div>
    </div>
  );
}
