import React from 'react';
import { Agent } from '../types';

const agentConfig = {
  data: {
    name: 'DATA',
    color: '#6aaa64',
    colorClass: 'text-[hsl(var(--agent-data))]'
  },
  cortona: {
    name: 'CORTONA',
    color: '#38bdf8',
    colorClass: 'text-[hsl(var(--agent-cortona))]'
  },
  jarvis: {
    name: 'JARVIS',
    color: '#f59e0b',
    colorClass: 'text-[hsl(var(--agent-jarvis))]'
  },
  council: {
    name: 'THE COUNCIL',
    color: '#a855f7',
    colorClass: 'text-[hsl(var(--agent-council))]'
  }
};

export function getAgentConfig(agent: Agent) {
  return agentConfig[agent];
}
