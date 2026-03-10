import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer, Tooltip } from 'recharts';

export default function AnalysisPipeline({ signals }) {
  const [mode, setMode] = useState('text_numeric');

  useEffect(() => {
    const fetchMode = async () => {
      try {
        const res = await axios.get('/api/macro/settings/analysis_mode');
        setMode(res.data?.value || 'text_numeric');
      } catch (err) {
        console.error('Failed to fetch analysis mode:', err);
      }
    };
    fetchMode();
  }, []);

  const latestSignal = signals && signals.length > 0 ? signals[0] : null;

  const radarData = [
    {
      axis: 'Text',
      score: latestSignal?.text_score || 0,
      fullMark: 100,
      active: true,
    },
    {
      axis: 'Numeric',
      score: latestSignal?.numeric_score || 0,
      fullMark: 100,
      active: true,
    },
    {
      axis: 'Visual',
      score: mode === 'full' ? (latestSignal?.visual_score || 0) : 0,
      fullMark: 100,
      active: mode === 'full',
    },
  ];

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-white">Analysis Pipeline</h2>
        <span className="px-2 py-1 rounded-full text-xs font-medium bg-blue-500/10 text-blue-400 border border-blue-500/30">
          {mode}
        </span>
      </div>

      <div className="flex flex-col items-center">
        <ResponsiveContainer width="100%" height={250}>
          <RadarChart data={radarData} cx="50%" cy="50%" outerRadius="75%">
            <PolarGrid stroke="#475569" />
            <PolarAngleAxis
              dataKey="axis"
              tick={({ x, y, payload }) => {
                const item = radarData.find((d) => d.axis === payload.value);
                const color = item?.active ? '#e2e8f0' : '#64748b';
                return (
                  <text x={x} y={y} fill={color} fontSize={12} textAnchor="middle" dominantBaseline="middle">
                    {payload.value}
                    {!item?.active && ' (OFF)'}
                  </text>
                );
              }}
            />
            <PolarRadiusAxis angle={90} domain={[0, 100]} tick={false} />
            <Radar
              name="Score"
              dataKey="score"
              stroke="#3b82f6"
              fill="#3b82f6"
              fillOpacity={0.3}
              strokeWidth={2}
            />
            <Tooltip
              contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569', borderRadius: '8px' }}
              labelStyle={{ color: '#e2e8f0' }}
            />
          </RadarChart>
        </ResponsiveContainer>

        {/* Score Details */}
        <div className="w-full grid grid-cols-3 gap-3 mt-2">
          {radarData.map((item) => (
            <div
              key={item.axis}
              className={`text-center p-2 rounded-lg ${
                item.active ? 'bg-slate-700/50' : 'bg-slate-700/20'
              }`}
            >
              <p className={`text-xs ${item.active ? 'text-slate-400' : 'text-slate-600'}`}>
                {item.axis}
              </p>
              <p className={`text-lg font-bold ${
                item.active
                  ? item.score >= 70 ? 'text-emerald-400' : item.score <= 30 ? 'text-rose-400' : 'text-blue-400'
                  : 'text-slate-600'
              }`}>
                {item.active ? item.score.toFixed(1) : 'OFF'}
              </p>
              <span className={`inline-block w-2 h-2 rounded-full mt-1 ${
                item.active ? 'bg-emerald-400' : 'bg-slate-600'
              }`} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
