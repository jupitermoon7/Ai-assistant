import { AgentChat } from '@/components/AgentChat';
import { chatCortona } from '@/lib/api';

export default function CortonaScreen() {
  return (
    <AgentChat
      agentName="Cortona"
      tagline="Intuitive general intelligence. Engineering, research, life tasks, creative thinking."
      accentColor="#A78BFA"
      iconName="cpu"
      sendFn={chatCortona}
    />
  );
}
