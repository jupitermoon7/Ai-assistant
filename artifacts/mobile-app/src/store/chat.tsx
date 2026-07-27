import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';
import { Agent, Message } from '../types';

interface ChatState {
  [key: string]: Message[];
}

interface ChatContextType {
  chatState: ChatState;
  addMessage: (agent: Agent, message: Message) => void;
  clearHistory: (agent: Agent) => void;
}

const CHAT_STATE_KEY = 'pi-assistant-chat-history';

const initialGreetings: Record<Agent, string> = {
  data: "I am DATA. Online and ready. Provide the parameters for analysis.",
  cortona: "Hi there! I'm CORTONA. How can I help you today?",
  jarvis: "JARVIS systems initialized. Awaiting your directives, sir.",
  council: "The Council is convened. We are ready to deliberate on your inquiry."
};

function createInitialState(): ChatState {
  return {
    data: [{ id: 'init-data', role: 'assistant', content: initialGreetings.data, timestamp: new Date() }],
    cortona: [{ id: 'init-cortona', role: 'assistant', content: initialGreetings.cortona, timestamp: new Date() }],
    jarvis: [{ id: 'init-jarvis', role: 'assistant', content: initialGreetings.jarvis, timestamp: new Date() }],
    council: [{ id: 'init-council', role: 'assistant', content: initialGreetings.council, timestamp: new Date() }]
  };
}

const ChatContext = createContext<ChatContextType | null>(null);

export function ChatProvider({ children }: { children: React.ReactNode }) {
  const [chatState, setChatState] = useState<ChatState>(() => {
    try {
      const stored = localStorage.getItem(CHAT_STATE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        // Revive dates
        const revived: ChatState = {};
        for (const key in parsed) {
          revived[key] = parsed[key].map((m: any) => ({ ...m, timestamp: new Date(m.timestamp) }));
        }
        // Ensure all agents exist
        const defaultState = createInitialState();
        return { ...defaultState, ...revived };
      }
    } catch (e) {
      console.error('Failed to load chat history', e);
    }
    return createInitialState();
  });

  useEffect(() => {
    localStorage.setItem(CHAT_STATE_KEY, JSON.stringify(chatState));
  }, [chatState]);

  const addMessage = useCallback((agent: Agent, message: Message) => {
    setChatState(prev => {
      const messages = prev[agent] || [];
      return {
        ...prev,
        [agent]: [...messages, message]
      };
    });
  }, []);

  const clearHistory = useCallback((agent: Agent) => {
    setChatState(prev => ({
      ...prev,
      [agent]: [{ id: `init-${agent}-${Date.now()}`, role: 'assistant', content: initialGreetings[agent], timestamp: new Date() }]
    }));
  }, []);

  return (
    <ChatContext.Provider value={{ chatState, addMessage, clearHistory }}>
      {children}
    </ChatContext.Provider>
  );
}

export function useChatStore() {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error('useChatStore must be used within ChatProvider');
  return ctx;
}
