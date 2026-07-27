/**
 * Reusable chat interface for Data, Cortona, and Jarvis agents.
 */

import React, { useRef, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { KeyboardAvoidingView } from 'react-native-keyboard-controller';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Feather } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { useColors } from '@/hooks/useColors';
import { MarkdownText } from '@/lib/markdown';

export interface Message {
  id: string;
  role: 'user' | 'agent';
  content: string;
}

interface AgentChatProps {
  agentName: string;
  tagline: string;
  accentColor: string;
  iconName: React.ComponentProps<typeof Feather>['name'];
  sendFn: (text: string) => Promise<string>;
}

function makeId() {
  return Date.now().toString() + Math.random().toString(36).substr(2, 7);
}

export function AgentChat({
  agentName,
  tagline,
  accentColor,
  iconName,
  sendFn,
}: AgentChatProps) {
  const colors = useColors();
  const insets = useSafeAreaInsets();
  const inputRef = useRef<TextInput>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || loading) return;

    setInput('');
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);

    const userMsg: Message = { id: makeId(), role: 'user', content: text };
    setMessages((prev) => [userMsg, ...prev]);

    setLoading(true);
    try {
      const reply = await sendFn(text);
      const agentMsg: Message = { id: makeId(), role: 'agent', content: reply };
      setMessages((prev) => [agentMsg, ...prev]);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Unknown error';
      const errMsg: Message = {
        id: makeId(),
        role: 'agent',
        content: `Could not reach the server.\n\n${msg}\n\nMake sure the Pi is running.`,
      };
      setMessages((prev) => [errMsg, ...prev]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  };

  const handleClear = () => {
    setMessages([]);
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
  };

  const renderItem = ({ item }: { item: Message }) => {
    const isUser = item.role === 'user';
    return (
      <View style={[styles.messageRow, isUser ? styles.userRow : styles.agentRow]}>
        {!isUser && (
          <View style={[styles.avatar, { backgroundColor: accentColor + '20' }]}>
            <Feather name={iconName} size={14} color={accentColor} />
          </View>
        )}
        <View
          style={[
            styles.bubble,
            isUser
              ? [styles.userBubble, { backgroundColor: colors.secondary }]
              : [styles.agentBubble, { backgroundColor: colors.card, borderColor: colors.border }],
          ]}
        >
          <MarkdownText
            content={item.content}
            textColor={colors.foreground}
            accentColor={accentColor}
            fontSize={14}
          />
        </View>
      </View>
    );
  };

  const topPad = insets.top + (Platform.OS === 'web' ? 67 : 0);
  const bottomPad = insets.bottom + (Platform.OS === 'web' ? 34 : 0);

  return (
    <KeyboardAvoidingView
      style={[styles.root, { backgroundColor: colors.background }]}
      behavior="padding"
      keyboardVerticalOffset={0}
    >
      {/* Custom header */}
      <View
        style={[
          styles.header,
          {
            paddingTop: topPad + 12,
            backgroundColor: colors.background,
            borderBottomColor: colors.border,
          },
        ]}
      >
        <View style={styles.agentInfo}>
          <View style={[styles.headerIcon, { backgroundColor: accentColor + '20' }]}>
            <Feather name={iconName} size={18} color={accentColor} />
          </View>
          <Text style={[styles.agentName, { color: colors.foreground }]}>{agentName}</Text>
        </View>
        {messages.length > 0 && (
          <Pressable
            onPress={handleClear}
            style={({ pressed }) => [styles.clearBtn, { opacity: pressed ? 0.6 : 1 }]}
            hitSlop={12}
          >
            <Feather name="trash-2" size={18} color={colors.mutedForeground} />
          </Pressable>
        )}
      </View>

      {/* Message list — inverted so newest is at bottom */}
      <FlatList
        data={messages}
        renderItem={renderItem}
        keyExtractor={(item) => item.id}
        inverted
        contentContainerStyle={[
          styles.listContent,
          { paddingTop: bottomPad + 8, paddingBottom: 12 },
        ]}
        keyboardDismissMode="interactive"
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
        // Typing indicator (appears at bottom in inverted list)
        ListHeaderComponent={
          loading ? (
            <View style={[styles.messageRow, styles.agentRow]}>
              <View style={[styles.avatar, { backgroundColor: accentColor + '20' }]}>
                <Feather name={iconName} size={14} color={accentColor} />
              </View>
              <View
                style={[
                  styles.bubble,
                  styles.agentBubble,
                  { backgroundColor: colors.card, borderColor: colors.border, paddingVertical: 14 },
                ]}
              >
                <ActivityIndicator size="small" color={accentColor} />
              </View>
            </View>
          ) : null
        }
        // Empty state (appears at bottom in inverted list = visually top)
        ListFooterComponent={
          messages.length === 0 && !loading ? (
            <View style={styles.emptyState}>
              <View style={[styles.emptyIcon, { backgroundColor: accentColor + '15' }]}>
                <Feather name={iconName} size={32} color={accentColor} />
              </View>
              <Text style={[styles.emptyTitle, { color: accentColor }]}>{agentName}</Text>
              <Text style={[styles.emptyTagline, { color: colors.mutedForeground }]}>{tagline}</Text>
            </View>
          ) : null
        }
      />

      {/* Input bar */}
      <View
        style={[
          styles.inputBar,
          {
            backgroundColor: colors.card,
            borderTopColor: colors.border,
            paddingBottom: bottomPad + 8,
          },
        ]}
      >
        <TextInput
          ref={inputRef}
          style={[styles.textInput, { color: colors.foreground }]}
          placeholder={`Ask ${agentName}...`}
          placeholderTextColor={colors.mutedForeground}
          value={input}
          onChangeText={setInput}
          multiline
          maxLength={4000}
          returnKeyType="default"
          blurOnSubmit={false}
        />
        <Pressable
          onPress={handleSend}
          disabled={!input.trim() || loading}
          style={({ pressed }) => [
            styles.sendBtn,
            { backgroundColor: input.trim() && !loading ? accentColor : colors.muted },
            pressed && { opacity: 0.75 },
          ]}
        >
          <Feather
            name="arrow-up"
            size={18}
            color={input.trim() && !loading ? '#FFFFFF' : colors.mutedForeground}
          />
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingBottom: 12,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  agentInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  headerIcon: {
    width: 36,
    height: 36,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  agentName: {
    fontFamily: 'Inter_600SemiBold',
    fontSize: 18,
    letterSpacing: -0.3,
  },
  clearBtn: {
    padding: 4,
  },
  listContent: {
    paddingHorizontal: 16,
    gap: 8,
    flexGrow: 1,
  },
  messageRow: {
    flexDirection: 'row',
    gap: 8,
    alignItems: 'flex-end',
    marginVertical: 2,
  },
  userRow: {
    justifyContent: 'flex-end',
  },
  agentRow: {
    justifyContent: 'flex-start',
  },
  avatar: {
    width: 28,
    height: 28,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  bubble: {
    maxWidth: '82%',
    padding: 12,
    borderRadius: 16,
  },
  userBubble: {
    borderBottomRightRadius: 4,
  },
  agentBubble: {
    borderBottomLeftRadius: 4,
    borderWidth: StyleSheet.hairlineWidth,
  },
  emptyState: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingTop: 80,
    paddingHorizontal: 32,
    gap: 12,
  },
  emptyIcon: {
    width: 72,
    height: 72,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 4,
  },
  emptyTitle: {
    fontFamily: 'Inter_700Bold',
    fontSize: 24,
    letterSpacing: -0.5,
  },
  emptyTagline: {
    fontFamily: 'Inter_400Regular',
    fontSize: 14,
    textAlign: 'center',
    lineHeight: 20,
  },
  inputBar: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    paddingHorizontal: 12,
    paddingTop: 10,
    borderTopWidth: StyleSheet.hairlineWidth,
    gap: 8,
  },
  textInput: {
    flex: 1,
    fontFamily: 'Inter_400Regular',
    fontSize: 15,
    lineHeight: 22,
    maxHeight: 120,
    paddingTop: 8,
    paddingBottom: 8,
    paddingHorizontal: 4,
  },
  sendBtn: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
    marginBottom: 1,
  },
});
