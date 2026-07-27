import React, { useRef, useEffect, useState } from 'react';
import { useChatStore } from '../store/chat';
import { useChatWithAgent } from '@workspace/api-client-react';
import { Agent, Message } from '../types';
import { getAgentConfig } from '../utils/agents';
import { MarkdownRenderer } from '../components/MarkdownRenderer';
import { Send, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface ChatScreenProps {
  agent: Agent;
}

export default function ChatScreen({ agent }: ChatScreenProps) {
  const { chatState, addMessage } = useChatStore();
  const messages = chatState[agent] || [];
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  
  const chatMutation = useChatWithAgent();
  const agentConfig = getAgentConfig(agent);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || chatMutation.isPending) return;

    const userMessage: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: input.trim(),
      timestamp: new Date()
    };

    addMessage(agent, userMessage);
    setInput('');

    const last10Messages = messages.slice(-10).map(m => ({
      role: m.role,
      content: m.content
    }));

    chatMutation.mutate(
      {
        data: {
          agent,
          message: userMessage.content,
          history: last10Messages
        }
      },
      {
        onSuccess: (response) => {
          const assistantMessage: Message = {
            id: `assistant-${Date.now()}`,
            role: 'assistant',
            content: response.reply,
            timestamp: new Date()
          };
          addMessage(agent, assistantMessage);
        },
        onError: (error: any) => {
          const errorMessage: Message = {
            id: `error-${Date.now()}`,
            role: 'assistant',
            content: `Error: ${error?.message || 'Failed to reach agent. Check your connection.'}`,
            timestamp: new Date()
          };
          addMessage(agent, errorMessage);
        }
      }
    );
  };

  return (
    <div className="flex flex-col h-full bg-background">
      {/* Header */}
      <div className="flex-shrink-0 px-4 py-3 border-b border-border">
        <h1 className={`text-lg font-semibold tracking-tight ${agentConfig.colorClass}`}>
          {agentConfig.name}
        </h1>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4 scrollbar-none">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            data-testid={`message-${msg.role}-${msg.id}`}
          >
            {msg.role === 'assistant' && (
              <div className="flex gap-3 max-w-[85%]">
                <div
                  className="w-8 h-8 rounded-full flex-shrink-0 flex items-center justify-center text-xs font-bold"
                  style={{
                    backgroundColor: `${agentConfig.color}20`,
                    color: agentConfig.color
                  }}
                >
                  {agent === 'council' ? 'C' : agentConfig.name[0]}
                </div>
                <div className="flex-1 bg-card border border-card-border rounded-2xl rounded-tl-none px-4 py-3">
                  <MarkdownRenderer content={msg.content} />
                </div>
              </div>
            )}
            {msg.role === 'user' && (
              <div className="bg-muted rounded-2xl rounded-tr-none px-4 py-3 max-w-[85%]">
                <p className="text-sm text-foreground break-words">{msg.content}</p>
              </div>
            )}
          </div>
        ))}
        {chatMutation.isPending && (
          <div className="flex justify-start">
            <div className="flex gap-3 max-w-[85%]">
              <div
                className="w-8 h-8 rounded-full flex-shrink-0 flex items-center justify-center"
                style={{
                  backgroundColor: `${agentConfig.color}20`,
                  color: agentConfig.color
                }}
              >
                <Loader2 className="w-4 h-4 animate-spin" />
              </div>
              <div className="bg-card border border-card-border rounded-2xl rounded-tl-none px-4 py-3 flex items-center gap-2">
                <div className="flex gap-1">
                  <div className="w-2 h-2 rounded-full bg-muted-foreground animate-bounce" style={{ animationDelay: '0ms' }} />
                  <div className="w-2 h-2 rounded-full bg-muted-foreground animate-bounce" style={{ animationDelay: '150ms' }} />
                  <div className="w-2 h-2 rounded-full bg-muted-foreground animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="flex-shrink-0 p-4 border-t border-border">
        <div className="flex items-end gap-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            placeholder={`Message ${agentConfig.name}...`}
            className="flex-1 bg-card border border-input rounded-2xl px-4 py-3 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 focus:ring-offset-background min-h-[44px] max-h-[120px]"
            rows={1}
            disabled={chatMutation.isPending}
            data-testid="input-message"
          />
          <Button
            onClick={handleSend}
            disabled={!input.trim() || chatMutation.isPending}
            size="icon"
            className="h-11 w-11 rounded-full flex-shrink-0"
            style={{
              backgroundColor: input.trim() && !chatMutation.isPending ? agentConfig.color : undefined
            }}
            data-testid="button-send"
          >
            <Send className="w-5 h-5" />
          </Button>
        </div>
      </div>
    </div>
  );
}
