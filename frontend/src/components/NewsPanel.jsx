import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';

function SentimentBar({ score }) {
  if (score == null) return <div className="w-1 h-full bg-slate-600 rounded-full" />;
  const val = Number(score);
  let color = 'bg-slate-500';
  if (val > 0.15) color = 'bg-emerald-500';
  else if (val < -0.15) color = 'bg-rose-500';
  return <div className={`w-1 h-full ${color} rounded-full`} />;
}

export default function NewsPanel() {
  const [news, setNews] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filterSymbol, setFilterSymbol] = useState('');

  const fetchNews = useCallback(async () => {
    try {
      const symbol = filterSymbol.trim().toUpperCase();
      if (symbol) {
        const res = await axios.get(`/api/news/${symbol}?limit=30`);
        setNews(res.data || []);
      } else {
        const summaryRes = await axios.get('/api/dashboard/signals?limit=5');
        const symbols = [...new Set((summaryRes.data || []).map((s) => s.stock_symbol))];
        if (symbols.length > 0) {
          const firstSymbol = symbols[0];
          const res = await axios.get(`/api/news/${firstSymbol}?limit=30`);
          setNews(res.data || []);
        } else {
          setNews([]);
        }
      }
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [filterSymbol]);

  useEffect(() => {
    fetchNews();
  }, [fetchNews]);

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-white">News</h2>
        <input
          type="text"
          placeholder="Filter: AAPL"
          value={filterSymbol}
          onChange={(e) => setFilterSymbol(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && fetchNews()}
          className="w-32 px-3 py-1.5 bg-slate-700 border border-slate-600 rounded-lg text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500"
        />
      </div>

      {loading ? (
        <p className="text-slate-400 text-center py-8">Loading news...</p>
      ) : error ? (
        <p className="text-rose-400 text-center py-8">Error: {error}</p>
      ) : news.length === 0 ? (
        <p className="text-slate-400 text-center py-8">No news articles found</p>
      ) : (
        <div className="space-y-2 max-h-96 overflow-y-auto">
          {news.map((article) => (
            <div key={article.id} className="flex gap-3 p-3 bg-slate-700/30 rounded-lg hover:bg-slate-700/50 transition-colors">
              <div className="flex-shrink-0 pt-1">
                <SentimentBar score={article.sentiment_score} />
              </div>
              <div className="flex-1 min-w-0">
                <a
                  href={article.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm text-white hover:text-blue-400 transition-colors line-clamp-2"
                >
                  {article.title}
                </a>
                <div className="flex items-center gap-3 mt-1">
                  <span className="text-xs text-slate-500">{article.source}</span>
                  <span className="text-xs text-slate-500">
                    {article.published_at
                      ? new Date(article.published_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
                      : ''}
                  </span>
                  <span className={`text-xs font-medium ${
                    article.sentiment_label === 'positive' ? 'text-emerald-400' :
                    article.sentiment_label === 'negative' ? 'text-rose-400' : 'text-slate-400'
                  }`}>
                    {article.sentiment_score != null ? Number(article.sentiment_score).toFixed(3) : ''}
                  </span>
                  {article.is_priced_in && (
                    <span className="text-xs px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-400">priced-in</span>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
