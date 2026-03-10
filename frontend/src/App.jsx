import React from 'react';
import { Routes, Route, NavLink } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import MacroView from './pages/MacroView';

const navItems = [
  { to: '/', label: 'Dashboard', icon: '📊' },
  { to: '/macro', label: 'Macro', icon: '🌍' },
];

function Sidebar() {
  return (
    <aside className="fixed left-0 top-0 h-screen w-56 bg-slate-800 border-r border-slate-700 flex flex-col z-50">
      <div className="p-4 border-b border-slate-700">
        <h1 className="text-xl font-bold text-blue-400">AlphaFlow US</h1>
        <p className="text-xs text-slate-400 mt-1">AI Swing Trading</p>
      </div>
      <nav className="flex-1 p-3 space-y-1">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-blue-500/20 text-blue-400'
                  : 'text-slate-300 hover:bg-slate-700 hover:text-white'
              }`
            }
          >
            <span className="text-lg">{item.icon}</span>
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>
      <div className="p-4 border-t border-slate-700">
        <p className="text-xs text-slate-500">v1.0.0</p>
      </div>
    </aside>
  );
}

export default function App() {
  return (
    <div className="flex min-h-screen bg-slate-900">
      <Sidebar />
      <main className="ml-56 flex-1 p-6 overflow-auto">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/macro" element={<MacroView />} />
        </Routes>
      </main>
    </div>
  );
}
