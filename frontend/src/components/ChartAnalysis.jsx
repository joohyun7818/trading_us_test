import React, { useState, useEffect } from 'react';
import axios from 'axios';

export default function ChartAnalysis() {
  const [mode, setMode] = useState('text_numeric');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchMode = async () => {
      try {
        const res = await axios.get('/api/macro/settings/analysis_mode');
        setMode(res.data?.value || 'text_numeric');
      } catch (err) {
        console.error('Failed to fetch analysis mode:', err);
      } finally {
        setLoading(false);
      }
    };
    fetchMode();
  }, []);

  if (loading) {
    return (
      <div className="bg-slate-800 rounded-xl border border-slate-700 p-6">
        <h2 className="text-lg font-semibold text-white mb-4">Chart Analysis</h2>
        <p className="text-slate-400 text-center py-4">Loading...</p>
      </div>
    );
  }

  if (mode === 'text_numeric') {
    return (
      <div className="bg-slate-800 rounded-xl border border-slate-700 p-6">
        <h2 className="text-lg font-semibold text-white mb-4">Chart Analysis</h2>
        <div className="bg-slate-700/50 rounded-lg p-8 text-center">
          <div className="text-4xl mb-3">📊</div>
          <p className="text-slate-400 text-sm">
            Visual chart analysis is disabled in <span className="text-blue-400 font-medium">text_numeric</span> mode.
          </p>
          <p className="text-slate-500 text-xs mt-2">
            Switch to <span className="font-medium">full</span> mode to enable qwen3-vl:8b chart pattern analysis.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-6">
      <h2 className="text-lg font-semibold text-white mb-4">Chart Analysis</h2>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Left: Candlestick Chart Image */}
        <div className="bg-slate-700/50 rounded-lg p-4">
          <h3 className="text-sm font-medium text-slate-300 mb-2">Candlestick Chart</h3>
          <div className="bg-slate-900 rounded-lg h-64 flex items-center justify-center">
            <p className="text-slate-500 text-sm">Chart image loads after analysis</p>
          </div>
        </div>

        {/* Right: VL Analysis Results */}
        <div className="bg-slate-700/50 rounded-lg p-4 space-y-3">
          <h3 className="text-sm font-medium text-slate-300 mb-2">VL Analysis Results</h3>
          <div className="space-y-2">
            <div className="flex justify-between items-center">
              <span className="text-xs text-slate-400">Pattern</span>
              <span className="text-xs text-white font-medium">Waiting for analysis...</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-xs text-slate-400">Confidence</span>
              <span className="text-xs text-slate-300">—</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-xs text-slate-400">Trend</span>
              <span className="text-xs text-slate-300">—</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-xs text-slate-400">Support</span>
              <span className="text-xs text-slate-300">—</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-xs text-slate-400">Resistance</span>
              <span className="text-xs text-slate-300">—</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
