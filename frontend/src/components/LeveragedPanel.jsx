import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Switch } from '@headlessui/react';

export default function LeveragedPanel() {
  const [status, setStatus] = useState(null);
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    try {
      const [statusRes, configRes] = await Promise.all([
        axios.get('/api/macro/leveraged/status'),
        axios.get('/api/macro/leveraged/config'),
      ]);
      setStatus(statusRes.data);
      setConfig(configRes.data);
    } catch (err) {
      console.error('Leveraged fetch error:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const toggleEnabled = async () => {
    const newVal = status?.enabled ? 'false' : 'true';
    try {
      await axios.put('/api/macro/settings/leveraged_enabled', { value: newVal });
      fetchData();
    } catch (err) {
      console.error('Toggle failed:', err);
    }
  };

  if (loading) {
    return (
      <div className="bg-slate-800 rounded-xl border border-slate-700 p-6">
        <h2 className="text-lg font-semibold text-white mb-4">Leveraged ETF Strategy</h2>
        <p className="text-slate-400 text-center py-4">Loading...</p>
      </div>
    );
  }

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-white">Leveraged ETF Strategy</h2>
        <Switch
          checked={status?.enabled || false}
          onChange={toggleEnabled}
          className={`${status?.enabled ? 'bg-blue-500' : 'bg-slate-600'} relative inline-flex h-6 w-11 items-center rounded-full transition-colors`}
        >
          <span className={`${status?.enabled ? 'translate-x-6' : 'translate-x-1'} inline-block h-4 w-4 transform rounded-full bg-white transition-transform`} />
        </Switch>
      </div>

      {/* Warning Banner */}
      <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-3">
        <p className="text-amber-400 text-xs font-medium">
          ⚠️ Leveraged ETFs (TQQQ/SQQQ) are not suitable for long-term holding due to volatility decay.
        </p>
      </div>

      {/* Config */}
      {config && (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs">
          <div className="bg-slate-700/50 rounded-lg p-3">
            <p className="text-slate-400">Max Capital</p>
            <p className="text-white font-medium">{((config.leveraged_max_pct || 0) * 100).toFixed(1)}%</p>
          </div>
          <div className="bg-slate-700/50 rounded-lg p-3">
            <p className="text-slate-400">Stop Loss</p>
            <p className="text-rose-400 font-medium">-{((config.leveraged_stop_loss || 0) * 100).toFixed(0)}%</p>
          </div>
          <div className="bg-slate-700/50 rounded-lg p-3">
            <p className="text-slate-400">Take Profit</p>
            <p className="text-emerald-400 font-medium">+{((config.leveraged_take_profit || 0) * 100).toFixed(0)}%</p>
          </div>
          <div className="bg-slate-700/50 rounded-lg p-3">
            <p className="text-slate-400">Max Hold</p>
            <p className="text-white font-medium">{config.leveraged_max_hold_days || 5} days</p>
          </div>
          <div className="bg-slate-700/50 rounded-lg p-3">
            <p className="text-slate-400">Min Extreme</p>
            <p className="text-white font-medium">{config.leveraged_min_extreme_days || 3} days</p>
          </div>
        </div>
      )}

      {/* Open Positions */}
      {status?.open_positions?.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-white mb-2">Open Positions</h3>
          <div className="space-y-2">
            {status.open_positions.map((pos) => {
              const pnlPct = pos.entry_price > 0 ? ((pos.current_price - pos.entry_price) / pos.entry_price * 100) : 0;
              const daysLeft = (pos.max_hold_days || 5) - Math.floor((Date.now() - new Date(pos.entry_date).getTime()) / 86400000);
              return (
                <div key={pos.id} className="bg-slate-700/50 rounded-lg p-3 flex items-center justify-between">
                  <div>
                    <span className="font-medium text-white">{pos.symbol}</span>
                    <span className="text-xs text-slate-400 ml-2">Entry: ${Number(pos.entry_price).toFixed(2)}</span>
                  </div>
                  <div className="text-right">
                    <p className={`text-sm font-medium ${pnlPct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%
                    </p>
                    <p className="text-xs text-slate-400">{Math.max(0, daysLeft)}d left | SL: ${Number(pos.stop_loss).toFixed(2)} / TP: ${Number(pos.take_profit).toFixed(2)}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* History */}
      {status?.closed_positions?.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-white mb-2">History</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-slate-700">
                  <th className="text-left py-1 px-2 text-slate-400">Symbol</th>
                  <th className="text-left py-1 px-2 text-slate-400">Entry</th>
                  <th className="text-left py-1 px-2 text-slate-400">P&L</th>
                  <th className="text-left py-1 px-2 text-slate-400">Status</th>
                </tr>
              </thead>
              <tbody>
                {status.closed_positions.map((pos) => (
                  <tr key={pos.id} className="border-b border-slate-700/50">
                    <td className="py-1 px-2 text-white">{pos.symbol}</td>
                    <td className="py-1 px-2 text-slate-300">${Number(pos.entry_price).toFixed(2)}</td>
                    <td className={`py-1 px-2 ${pos.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                      ${pos.pnl != null ? Number(pos.pnl).toFixed(2) : '—'}
                    </td>
                    <td className="py-1 px-2 text-slate-400">{pos.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {!status?.open_positions?.length && !status?.closed_positions?.length && (
        <p className="text-slate-400 text-center text-sm py-4">No leveraged positions</p>
      )}
    </div>
  );
}
