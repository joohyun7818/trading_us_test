import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import KpiCards from '../components/KpiCards';
import SignalList from '../components/SignalList';
import MacroGauge from '../components/MacroGauge';
import NewsPanel from '../components/NewsPanel';
import AnalysisPipeline from '../components/AnalysisPipeline';
import OllamaStatus from '../components/OllamaStatus';
import BackfillProgress from '../components/BackfillProgress';

export default function Dashboard() {
  const [summary, setSummary] = useState(null);
  const [signals, setSignals] = useState([]);
  const [macro, setMacro] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchData = useCallback(async () => {
    try {
      const [summaryRes, signalsRes, macroRes] = await Promise.all([
        axios.get('/api/dashboard/summary'),
        axios.get('/api/dashboard/signals?limit=20'),
        axios.get('/api/macro/regime'),
      ]);
      setSummary(summaryRes.data);
      setSignals(signalsRes.data);
      setMacro(macroRes.data);
      setError(null);
    } catch (err) {
      setError(err.message || 'Failed to fetch data');
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
        <div className="text-slate-400 text-lg">Loading dashboard...</div>
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

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Dashboard</h1>
        <button
          onClick={fetchData}
          className="px-3 py-1.5 bg-slate-700 rounded-lg text-sm text-slate-300 hover:bg-slate-600 transition-colors"
        >
          Refresh
        </button>
      </div>

      {/* KPI Cards */}
      <KpiCards summary={summary} />

      {/* Middle Row: Signals + Macro Gauge */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <SignalList signals={signals} />
        </div>
        <div>
          <MacroGauge macro={macro} />
        </div>
      </div>

      {/* Lower Row: News + Analysis Pipeline */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <NewsPanel />
        <AnalysisPipeline signals={signals} />
      </div>

      {/* Bottom Row: Ollama + Backfill */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <OllamaStatus />
        <BackfillProgress />
      </div>
    </div>
  );
}
