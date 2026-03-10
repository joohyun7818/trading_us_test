import React from 'react';

function TypeBadge({ type }) {
  if (type === 'BUY') {
    return <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">BUY</span>;
  }
  if (type === 'SELL') {
    return <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-rose-500/10 text-rose-400 border border-rose-500/30">SELL</span>;
  }
  return <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-slate-500/10 text-slate-400 border border-slate-500/30">HOLD</span>;
}

function ScoreBar({ score, label }) {
  const pct = Math.max(0, Math.min(100, score || 0));
  const color = pct >= 70 ? 'bg-emerald-500' : pct <= 30 ? 'bg-rose-500' : 'bg-blue-500';
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-slate-400 w-8">{label}</span>
      <div className="flex-1 h-1.5 bg-slate-700 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-slate-300 w-8 text-right">{score != null ? score.toFixed(0) : '—'}</span>
    </div>
  );
}

export default function SignalList({ signals }) {
  if (!signals || signals.length === 0) {
    return (
      <div className="bg-slate-800 rounded-xl border border-slate-700 p-6">
        <h2 className="text-lg font-semibold text-white mb-4">Recent Signals</h2>
        <p className="text-slate-400 text-center py-8">No signals yet</p>
      </div>
    );
  }

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-6">
      <h2 className="text-lg font-semibold text-white mb-4">Recent Signals</h2>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-700">
              <th className="text-left py-2 px-3 text-slate-400 font-medium">Symbol</th>
              <th className="text-left py-2 px-3 text-slate-400 font-medium">Type</th>
              <th className="text-left py-2 px-3 text-slate-400 font-medium">Final Score</th>
              <th className="text-left py-2 px-3 text-slate-400 font-medium">Text</th>
              <th className="text-left py-2 px-3 text-slate-400 font-medium">Numeric</th>
              <th className="text-left py-2 px-3 text-slate-400 font-medium">Visual</th>
              <th className="text-left py-2 px-3 text-slate-400 font-medium">Time</th>
            </tr>
          </thead>
          <tbody>
            {signals.map((sig) => (
              <tr key={sig.id} className="border-b border-slate-700/50 hover:bg-slate-700/30 transition-colors">
                <td className="py-2 px-3 font-medium text-white">{sig.stock_symbol}</td>
                <td className="py-2 px-3"><TypeBadge type={sig.signal_type} /></td>
                <td className="py-2 px-3">
                  <ScoreBar score={sig.final_score} label="" />
                </td>
                <td className="py-2 px-3 text-slate-300">{sig.text_score != null ? sig.text_score.toFixed(1) : '—'}</td>
                <td className="py-2 px-3 text-slate-300">{sig.numeric_score != null ? sig.numeric_score.toFixed(1) : '—'}</td>
                <td className="py-2 px-3 text-slate-300">{sig.visual_score != null ? sig.visual_score.toFixed(1) : '—'}</td>
                <td className="py-2 px-3 text-slate-400 text-xs">
                  {sig.created_at ? new Date(sig.created_at).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }) : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
