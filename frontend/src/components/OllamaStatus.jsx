import React, { useState, useEffect } from 'react';
import axios from 'axios';

const MODEL_INFO = [
  { name: 'qwen3:4b', role: '1st Sentiment Classification', size: '2.6GB' },
  { name: 'qwen3:8b', role: '2nd RAG Deep Analysis', size: '5.2GB' },
  { name: 'qwen3-vl:8b', role: 'Chart Pattern Analysis', size: '~5.5GB' },
  { name: 'bge-m3', role: 'News Embedding', size: '1.2GB' },
];

export default function OllamaStatus() {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const res = await axios.get('/api/ollama/status');
        setStatus(res.data);
      } catch (err) {
        setStatus({ status: 'offline', error: err.message });
      } finally {
        setLoading(false);
      }
    };
    fetchStatus();
    const interval = setInterval(fetchStatus, 30000);
    return () => clearInterval(interval);
  }, []);

  const isOnline = status?.status === 'ok';
  const availableModels = status?.models || [];

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-white">Ollama Status</h2>
        <div className="flex items-center gap-2">
          <span className={`w-2.5 h-2.5 rounded-full ${isOnline ? 'bg-emerald-400 animate-pulse' : 'bg-rose-400'}`} />
          <span className={`text-xs font-medium ${isOnline ? 'text-emerald-400' : 'text-rose-400'}`}>
            {isOnline ? 'Online' : 'Offline'}
          </span>
        </div>
      </div>

      {loading ? (
        <p className="text-slate-400 text-center py-4">Checking Ollama...</p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {MODEL_INFO.map((model) => {
            const isAvailable = availableModels.some((m) => m.includes(model.name.split(':')[0]));
            return (
              <div key={model.name} className="bg-slate-700/50 rounded-lg p-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-white">{model.name}</span>
                  <span className={`w-2 h-2 rounded-full ${isAvailable ? 'bg-emerald-400' : 'bg-rose-400'}`} />
                </div>
                <p className="text-xs text-slate-400 mt-1">{model.role}</p>
                <div className="flex items-center justify-between mt-1">
                  <span className="text-xs text-slate-500">{model.size}</span>
                  <span className={`text-xs ${isAvailable ? 'text-emerald-400' : 'text-slate-500'}`}>
                    {isAvailable ? 'Downloaded' : 'Not found'}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
