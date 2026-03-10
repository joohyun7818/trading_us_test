import React, { useState, useEffect } from 'react';
import axios from 'axios';

function RsiIndicator({ rsi }) {
  if (rsi == null) return <span className="text-slate-500">—</span>;
  const val = Number(rsi);
  let color = 'text-slate-300';
  if (val <= 30) color = 'text-emerald-400';
  else if (val >= 70) color = 'text-rose-400';
  return <span className={`font-medium ${color}`}>{val.toFixed(1)}</span>;
}

export default function SectorGauge() {
  const [sectors, setSectors] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchSectors = async () => {
      try {
        const res = await axios.get('/api/dashboard/sectors');
        setSectors(res.data || []);
      } catch (err) {
        console.error('Failed to fetch sectors:', err);
      } finally {
        setLoading(false);
      }
    };
    fetchSectors();
  }, []);

  if (loading) {
    return (
      <div className="bg-slate-800 rounded-xl border border-slate-700 p-6">
        <h2 className="text-lg font-semibold text-white mb-4">Sector Overview</h2>
        <p className="text-slate-400 text-center py-4">Loading sectors...</p>
      </div>
    );
  }

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-6">
      <h2 className="text-lg font-semibold text-white mb-4">Sector Overview</h2>
      {sectors.length === 0 ? (
        <p className="text-slate-400 text-center py-4">No sector data available</p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {sectors.map((sector) => (
            <div key={sector.sector_name} className="bg-slate-700/50 rounded-lg p-4 space-y-2">
              <h3 className="text-sm font-medium text-white">{sector.sector_name}</h3>
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-400">Stocks: <span className="text-slate-200">{sector.stock_count}</span></span>
                <span className="text-slate-400">Avg RSI: <RsiIndicator rsi={sector.avg_rsi} /></span>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-400">
                  Avg Sentiment:{' '}
                  <span className={
                    sector.avg_sentiment > 0 ? 'text-emerald-400' :
                    sector.avg_sentiment < 0 ? 'text-rose-400' : 'text-slate-300'
                  }>
                    {sector.avg_sentiment != null ? Number(sector.avg_sentiment).toFixed(3) : '—'}
                  </span>
                </span>
                <span className="text-slate-400">
                  Chg:{' '}
                  <span className={
                    sector.avg_change_pct > 0 ? 'text-emerald-400' :
                    sector.avg_change_pct < 0 ? 'text-rose-400' : 'text-slate-300'
                  }>
                    {sector.avg_change_pct != null ? `${Number(sector.avg_change_pct).toFixed(2)}%` : '—'}
                  </span>
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
