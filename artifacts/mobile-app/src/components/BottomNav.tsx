import React from 'react';
import { Link, useLocation } from 'wouter';
import { Database, Sparkles, Zap, Users, Settings } from 'lucide-react';
import { Agent } from '../types';

const tabs = [
  { id: 'data' as Agent, path: '/data', icon: Database, label: 'DATA', color: 'hsl(var(--agent-data))' },
  { id: 'cortona' as Agent, path: '/cortona', icon: Sparkles, label: 'CORTONA', color: 'hsl(var(--agent-cortona))' },
  { id: 'jarvis' as Agent, path: '/jarvis', icon: Zap, label: 'JARVIS', color: 'hsl(var(--agent-jarvis))' },
  { id: 'council' as Agent, path: '/council', icon: Users, label: 'COUNCIL', color: 'hsl(var(--agent-council))' },
  { id: 'settings', path: '/settings', icon: Settings, label: 'Settings', color: 'hsl(var(--muted-foreground))' }
];

export function BottomNav() {
  const [location] = useLocation();

  return (
    <nav className="flex-shrink-0 border-t border-border bg-card/50 backdrop-blur-sm">
      <div className="flex items-center justify-around h-16 px-2">
        {tabs.map((tab) => {
          const isActive = location === tab.path;
          const Icon = tab.icon;
          
          return (
            <Link
              key={tab.id}
              href={tab.path}
              className="flex flex-col items-center justify-center gap-1 px-3 py-2 rounded-lg transition-all no-underline relative"
              style={{
                color: isActive ? tab.color : 'hsl(var(--muted-foreground))'
              }}
              data-testid={`tab-${tab.id}`}
            >
              <div className="relative">
                <Icon className="w-5 h-5" strokeWidth={isActive ? 2.5 : 2} />
                {isActive && tab.id !== 'settings' && (
                  <div
                    className="absolute -inset-2 rounded-full blur-md opacity-30"
                    style={{ backgroundColor: tab.color }}
                  />
                )}
              </div>
              <span className="text-[10px] font-medium tracking-wider">
                {tab.label}
              </span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
