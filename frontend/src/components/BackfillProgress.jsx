import React, { useState, useEffect } from 'react';
import axios from 'axios';

function StatusBadge({ status }) {
  const colors = {
    completed: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
    running: 'bg-blue-500/10 text-blue-400 border-blue-500/30',
    error: 'bg-rose-500/10 text-rose-400 border-rose-500/30',
    pending: 'bg-slate-500/10 text-slate-400 border-slate-500/30',
  };
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium border ${colors[status] || colors.pending}`}>
      {status || 'pending'}
    </span>
  );
}

export default function BackfillProgress() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchProgress = async () => {
      try {
        const res = await axios.get('/api/news/backfill/status');
        setData(res.data);
      } catch (err) {
        console.error('Backfill status error:', err);
      } finally {
        setLoading(false);
      }
    };
    fetchProgress();
    const interval = setInterval(fetchProgress, 30000);
    return () => clearInterval(interval);
  }, []);

  const startBackfill = async () => {
    try {
      await axios.post('/api/news/backfill/start');
      const res = await axios.get('/api/news/backfill/status');
      setData(res.data);
    } catch (err) {
      console.error('Start backfill error:', err);
    }
  };

  const total = data?.total || 0;
  const completed = data?.completed || 0;
  const progressPct = total > 0 ? Math.round((completed / total) * 100) : 0;

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-white">Backfill Progress</h2>
        <div className="flex items-center gap-2">
          {data?.is_running && (
            <span className="text-xs text-blue-400 animate-pulse">Running...</span>
          )}
          <button
            onClick={startBackfill}
            disabled={data?.is_running}
            className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
              data?.is_running
                ? 'bg-slate-700 text-slate-500 cursor-not-allowed'
                : 'bg-blue-500 text-white hover:bg-blue-600'
            }`}
          >
            Start Backfill
          </button>
        </div>
      </div>

      {loading ? (
        <p className="text-slate-400 text-center py-4">Loading...</p>
      ) : (
        <>
          {/* Overall Progress */}
          <div className="mb-4">
            <div className="flex items-center justify-between text-sm mb-1">
              <span className="text-slate-400">Overall Progress</span>
              <span className="text-white font-medium">{completed}/{total} ({progressPct}%)</span>
            </div>
            <div className="w-full h-2 bg-slate-700 rounded-full overflow-hidden">
              <div
                className="h-full bg-blue-500 rounded-full transition-all duration-500"
                style={{ width: `${progressPct}%` }}
              />
            </div>
          </div>

          {/* Per-Symbol Table */}
          {data?.progress?.length > 0 && (
            <div className="max-h-48 overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-slate-800">
                  <tr className="border-b border-slate-700">
                    <th className="text-left py-1 px-2 text-slate-400">Symbol</th>
                    <th className="text-left py-1 px-2 text-slate-400">Source</th>
                    <th className="text-left py-1 px-2 text-slate-400">Articles</th>
                    <th className="text-left py-1 px-2 text-slate-400">Last Date</th>
                    <th className="text-left py-1 px-2 text-slate-400">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {data.progress.slice(0, 50).map((item, idx) => (
                    <tr key={idx} className="border-b border-slate-700/50">
                      <td className="py-1 px-2 text-white">{item.stock_symbol}</td>
                      <td className="py-1 px-2 text-slate-400">{item.source}</td>
                      <td className="py-1 px-2 text-slate-300">{item.article_count}</td>
                      <td className="py-1 px-2 text-slate-400">
                        {item.last_date ? new Date(item.last_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '—'}
                      </td>
                      <td className="py-1 px-2"><StatusBadge status={item.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {(!data?.progress || data.progress.length === 0) && (
            <p className="text-slate-400 text-center text-sm py-4">No backfill data. Click "Start Backfill" to begin.</p>
          )}
        </>
      )}
    </div>
  );
}
