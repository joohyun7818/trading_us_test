import React from 'react';

const kpiConfig = [
  { key: 'portfolio_value', label: 'Total Assets', prefix: '$', format: 'currency' },
  { key: 'today_pnl', label: "Daily P&L", prefix: '$', format: 'pnl' },
  { key: 'active_positions', label: 'Active Positions', format: 'number' },
  { key: 'today_signals', label: "Today's Signals", format: 'number' },
  { key: 'macro_regime', label: 'Macro Regime', format: 'badge' },
  { key: 'ollama', label: 'Ollama Status', format: 'status' },
];

function formatValue(value, format, prefix = '') {
  if (value == null) return '—';
  if (format === 'currency') return `${prefix}${Number(value).toLocaleString('en-US', { minimumFractionDigits: 2 })}`;
  if (format === 'pnl') {
    const num = Number(value);
    const color = num >= 0 ? 'text-emerald-400' : 'text-rose-400';
    const sign = num >= 0 ? '+' : '';
    return <span className={color}>{sign}{prefix}{Math.abs(num).toLocaleString('en-US', { minimumFractionDigits: 2 })}</span>;
  }
  if (format === 'number') return Number(value).toLocaleString();
  return value;
}

function RegimeBadge({ regime }) {
  const colors = {
    EXTREME_GREED: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
    GREED: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
    NEUTRAL: 'bg-blue-500/10 text-blue-400 border-blue-500/30',
    FEAR: 'bg-rose-500/10 text-rose-400 border-rose-500/30',
    EXTREME_FEAR: 'bg-rose-500/10 text-rose-400 border-rose-500/30',
  };
  return (
    <span className={`px-2 py-1 rounded-full text-xs font-medium border ${colors[regime] || colors.NEUTRAL}`}>
      {regime || 'UNKNOWN'}
    </span>
  );
}

export default function KpiCards({ summary }) {
  if (!summary) return null;

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-6">
      {kpiConfig.map((kpi) => (
        <div key={kpi.key} className="bg-slate-800 rounded-xl border border-slate-700 p-6">
          <p className="text-xs font-medium text-slate-400 uppercase tracking-wider">{kpi.label}</p>
          <div className="mt-2 text-xl font-bold">
            {kpi.format === 'badge' ? (
              <RegimeBadge regime={summary.macro_regime} />
            ) : kpi.format === 'status' ? (
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse" />
                <span className="text-sm text-slate-300">Online</span>
              </div>
            ) : (
              formatValue(summary[kpi.key], kpi.format, kpi.prefix)
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
