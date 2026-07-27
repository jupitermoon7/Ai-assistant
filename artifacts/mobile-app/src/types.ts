export type Agent = 'data' | 'cortona' | 'jarvis' | 'council';

export type Message = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
};
