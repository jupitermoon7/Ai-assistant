import { AgentChat } from '@/components/AgentChat';
import { chatData } from '@/lib/api';

export default function DataScreen() {
  return (
    <AgentChat
      agentName="Data"
      tagline="Pure analytics. Numbers, stats, structured reports. Cold, precise, no fluff."
      accentColor="#3B82F6"
      iconName="bar-chart-2"
      sendFn={chatData}
    />
  );
}
