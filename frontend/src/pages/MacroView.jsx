import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import MacroGauge from '../components/MacroGauge';
import LeveragedPanel from '../components/LeveragedPanel';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';

const INDICATOR_COLORS = {
  sp500_trend: '#3b82f6',
  vix_level: '#ef4444',
  yield_curve_spread: '#f59e0b',
  market_rsi: '#10b981',
  market_breadth: '#8b5cf6',
  put_call_ratio: '#ec4899',
  macro_news_sentiment: '#06b6d4',
};

const INDICATOR_LABELS = {
  sp500_trend: 'S&P 500 Trend',
  vix_level: 'VIX Level',
  yield_curve_spread: 'Yield Curve',
  market_rsi: 'Market RSI',
  market_breadth: 'Breadth',
  put_call_ratio: 'Put/Call',
  macro_news_sentiment: 'Macro Sentiment',
};

export default function MacroView() {
  const [macro, setMacro] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchData = useCallback(async () => {
    try {
      const [macroRes, historyRes] = await Promise.all([
        axios.get('/api/macro/regime'),
        axios.get('/api/macro/regime/history?limit=30'),
      ]);
      setMacro(macroRes.data);
      setHistory(historyRes.data.reverse());
      setError(null);
    } catch (err) {
      setError(err.message || 'Failed to fetch macro data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="text-slate-400 text-lg">Loading macro data...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-rose-500/10 border border-rose-500/30 rounded-xl p-6">
        <p className="text-rose-400">Error: {error}</p>
        <button onClick={fetchData} className="mt-3 px-4 py-2 bg-blue-500 rounded-lg text-sm hover:bg-blue-600">
          Retry
        </button>
      </div>
    );
  }

  const chartData = history.map((item) => ({
    date: item.created_at ? new Date(item.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '',
    sp500_trend: item.sp500_trend != null ? Number(item.sp500_trend) : null,
    vix_level: item.vix_level != null ? Number(item.vix_level) : null,
    yield_curve_spread: item.yield_curve_spread != null ? Number(item.yield_curve_spread) : null,
    market_rsi: item.market_rsi != null ? Number(item.market_rsi) : null,
    market_breadth: item.market_breadth != null ? Number(item.market_breadth) : null,
    put_call_ratio: item.put_call_ratio != null ? Number(item.put_call_ratio) : null,
    macro_news_sentiment: item.macro_news_sentiment != null ? Number(item.macro_news_sentiment) : null,
  }));

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">Macro Regime</h1>

      {/* Large Macro Gauge */}
      <div className="bg-slate-800 rounded-xl border border-slate-700 p-6">
        <MacroGauge macro={macro} large />
      </div>

      {/* 7 Indicator Trend Lines */}
      <div className="bg-slate-800 rounded-xl border border-slate-700 p-6">
        <h2 className="text-lg font-semibold text-white mb-4">Macro Indicators (30-Day Trend)</h2>
        {chartData.length === 0 ? (
          <p className="text-slate-400 text-center py-8">No history data available</p>
        ) : (
          <ResponsiveContainer width="100%" height={400}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="date" stroke="#94a3b8" fontSize={12} />
              <YAxis stroke="#94a3b8" fontSize={12} domain={[0, 1]} />
              <Tooltip
                contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569', borderRadius: '8px' }}
                labelStyle={{ color: '#e2e8f0' }}
              />
              <Legend />
              {Object.keys(INDICATOR_COLORS).map((key) => (
                <Line
                  key={key}
                  type="monotone"
                  dataKey={key}
                  name={INDICATOR_LABELS[key]}
                  stroke={INDICATOR_COLORS[key]}
                  strokeWidth={2}
                  dot={false}
                  connectNulls
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Leveraged Panel */}
      <LeveragedPanel />
    </div>
  );
}
