import { AgentChat } from '@/components/AgentChat';
import { chatJarvis } from '@/lib/api';

export default function JarvisScreen() {
  return (
    <AgentChat
      agentName="Jarvis"
      tagline="Full-spectrum intelligence. Analytical depth + intuitive breadth combined. Handles anything."
      accentColor="#FBBF24"
      iconName="zap"
      sendFn={chatJarvis}
    />
  );
}
