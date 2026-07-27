/**
 * Council mode — all three agents deliberate on a question in two rounds.
 * Round 1: independent answers. Round 2: each reacts to the others.
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
import { chatCouncil, type CouncilRound } from '@/lib/api';

const COUNCIL_ACCENT = '#2DD4BF';

const AGENT_COLORS: Record<'data' | 'cortona' | 'jarvis', string> = {
  data: '#3B82F6',
  cortona: '#A78BFA',
  jarvis: '#FBBF24',
};

const AGENT_ICONS: Record<'data' | 'cortona' | 'jarvis', React.ComponentProps<typeof Feather>['name']> = {
  data: 'bar-chart-2',
  cortona: 'cpu',
  jarvis: 'zap',
};

type ChatEntry =
  | { id: string; type: 'user'; content: string }
  | { id: string; type: 'council'; question: string; rounds: CouncilRound[] }
  | { id: string; type: 'error'; content: string };

function makeId() {
  return Date.now().toString() + Math.random().toString(36).substr(2, 7);
}

interface AgentSectionProps {
  agent: 'data' | 'cortona' | 'jarvis';
  content: string;
  defaultExpanded?: boolean;
}

function AgentSection({ agent, content, defaultExpanded = true }: AgentSectionProps) {
  const colors = useColors();
  const [expanded, setExpanded] = useState(defaultExpanded);
  const color = AGENT_COLORS[agent];
  const icon = AGENT_ICONS[agent];
  const label = agent.charAt(0).toUpperCase() + agent.slice(1);

  return (
    <View style={styles.agentSection}>
      <Pressable
        onPress={() => setExpanded((e) => !e)}
        style={[styles.agentSectionHeader, { borderLeftColor: color }]}
      >
        <View style={styles.agentSectionTitle}>
          <View style={[styles.agentDot, { backgroundColor: color + '25' }]}>
            <Feather name={icon} size={12} color={color} />
          </View>
          <Text style={[styles.agentLabel, { color }]}>{label}</Text>
        </View>
        <Feather
          name={expanded ? 'chevron-up' : 'chevron-down'}
          size={14}
          color={colors.mutedForeground}
        />
      </Pressable>
      {expanded && (
        <View style={styles.agentSectionBody}>
          <MarkdownText content={content} textColor={colors.foreground} accentColor={color} fontSize={13} />
        </View>
      )}
    </View>
  );
}

interface CouncilSessionProps {
  question: string;
  rounds: CouncilRound[];
}

function CouncilSession({ question, rounds }: CouncilSessionProps) {
  const colors = useColors();

  return (
    <View style={[styles.councilCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
      <View style={[styles.councilCardHeader, { borderBottomColor: colors.border }]}>
        <View style={[styles.councilBadge, { backgroundColor: COUNCIL_ACCENT + '20' }]}>
          <Feather name="users" size={12} color={COUNCIL_ACCENT} />
          <Text style={[styles.councilBadgeText, { color: COUNCIL_ACCENT }]}>Council</Text>
        </View>
      </View>

      {rounds.map((round) => (
        <View key={round.round} style={styles.roundBlock}>
          <Text style={[styles.roundLabel, { color: colors.mutedForeground }]}>
            Round {round.round} — {round.label}
          </Text>
          <AgentSection agent="data" content={round.data} defaultExpanded={round.round === 1} />
          <AgentSection agent="cortona" content={round.cortona} defaultExpanded={round.round === 1} />
          <AgentSection agent="jarvis" content={round.jarvis} defaultExpanded={round.round === 1} />
        </View>
      ))}
    </View>
  );
}

export default function CouncilScreen() {
  const colors = useColors();
  const insets = useSafeAreaInsets();
  const inputRef = useRef<TextInput>(null);
  const [entries, setEntries] = useState<ChatEntry[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || loading) return;

    setInput('');
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);

    const userId = makeId();
    setEntries((prev) => [{ id: userId, type: 'user', content: text }, ...prev]);

    setLoading(true);
    try {
      const result = await chatCouncil(text);
      const councilId = makeId();
      setEntries((prev) => [
        { id: councilId, type: 'council', question: result.question, rounds: result.rounds },
        ...prev,
      ]);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Unknown error';
      const errId = makeId();
      setEntries((prev) => [
        { id: errId, type: 'error', content: `Could not reach the server.\n\n${msg}` },
        ...prev,
      ]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  };

  const handleClear = () => {
    setEntries([]);
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
  };

  const renderItem = ({ item }: { item: ChatEntry }) => {
    if (item.type === 'user') {
      return (
        <View style={[styles.messageRow, styles.userRow]}>
          <View style={[styles.bubble, styles.userBubble, { backgroundColor: colors.secondary }]}>
            <Text style={[styles.userText, { color: colors.foreground }]}>{item.content}</Text>
          </View>
        </View>
      );
    }

    if (item.type === 'error') {
      return (
        <View style={[styles.messageRow, styles.agentRow]}>
          <View style={[styles.bubble, styles.agentBubble, { backgroundColor: colors.card, borderColor: colors.border }]}>
            <Text style={[styles.errorText, { color: colors.destructive }]}>{item.content}</Text>
          </View>
        </View>
      );
    }

    // council type
    return (
      <View style={styles.councilRow}>
        <CouncilSession question={item.question} rounds={item.rounds} />
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
      {/* Header */}
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
          <View style={[styles.headerIcon, { backgroundColor: COUNCIL_ACCENT + '20' }]}>
            <Feather name="users" size={18} color={COUNCIL_ACCENT} />
          </View>
          <Text style={[styles.agentName, { color: colors.foreground }]}>Council</Text>
        </View>
        {entries.length > 0 && (
          <Pressable
            onPress={handleClear}
            style={({ pressed }) => [{ opacity: pressed ? 0.6 : 1 }]}
            hitSlop={12}
          >
            <Feather name="trash-2" size={18} color={colors.mutedForeground} />
          </Pressable>
        )}
      </View>

      {/* Message list */}
      <FlatList
        data={entries}
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
        ListHeaderComponent={
          loading ? (
            <View style={[styles.loadingCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
              <ActivityIndicator size="small" color={COUNCIL_ACCENT} />
              <Text style={[styles.loadingText, { color: colors.mutedForeground }]}>
                Council deliberating — this takes a moment…
              </Text>
            </View>
          ) : null
        }
        ListFooterComponent={
          entries.length === 0 && !loading ? (
            <View style={styles.emptyState}>
              <View style={[styles.emptyIcon, { backgroundColor: COUNCIL_ACCENT + '15' }]}>
                <Feather name="users" size={32} color={COUNCIL_ACCENT} />
              </View>
              <Text style={[styles.emptyTitle, { color: COUNCIL_ACCENT }]}>Council Mode</Text>
              <Text style={[styles.emptyTagline, { color: colors.mutedForeground }]}>
                All three agents deliberate together in two rounds. Best for complex questions requiring multiple perspectives.
              </Text>
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
          placeholder="Convene the council..."
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
            { backgroundColor: input.trim() && !loading ? COUNCIL_ACCENT : colors.muted },
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
  root: { flex: 1 },
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
  listContent: {
    paddingHorizontal: 12,
    gap: 8,
    flexGrow: 1,
  },
  messageRow: {
    flexDirection: 'row',
    gap: 8,
    alignItems: 'flex-end',
    marginVertical: 2,
  },
  userRow: { justifyContent: 'flex-end' },
  agentRow: { justifyContent: 'flex-start' },
  bubble: {
    maxWidth: '82%',
    padding: 12,
    borderRadius: 16,
  },
  userBubble: { borderBottomRightRadius: 4 },
  agentBubble: { borderBottomLeftRadius: 4, borderWidth: StyleSheet.hairlineWidth },
  userText: {
    fontFamily: 'Inter_400Regular',
    fontSize: 14,
    lineHeight: 22,
  },
  errorText: {
    fontFamily: 'Inter_400Regular',
    fontSize: 13,
    lineHeight: 20,
  },
  councilRow: { paddingHorizontal: 4, marginVertical: 2 },
  councilCard: {
    borderRadius: 16,
    borderWidth: StyleSheet.hairlineWidth,
    overflow: 'hidden',
  },
  councilCardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  councilBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 8,
  },
  councilBadgeText: {
    fontFamily: 'Inter_600SemiBold',
    fontSize: 12,
  },
  roundBlock: { paddingHorizontal: 14, paddingVertical: 12, gap: 8 },
  roundLabel: {
    fontFamily: 'Inter_500Medium',
    fontSize: 11,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    marginBottom: 4,
  },
  agentSection: { borderRadius: 10, overflow: 'hidden' },
  agentSectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingLeft: 10,
    paddingRight: 10,
    paddingVertical: 8,
    borderLeftWidth: 2,
  },
  agentSectionTitle: { flexDirection: 'row', alignItems: 'center', gap: 7 },
  agentDot: {
    width: 22,
    height: 22,
    borderRadius: 6,
    alignItems: 'center',
    justifyContent: 'center',
  },
  agentLabel: {
    fontFamily: 'Inter_600SemiBold',
    fontSize: 13,
  },
  agentSectionBody: { paddingLeft: 12, paddingRight: 10, paddingVertical: 8 },
  loadingCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    marginHorizontal: 4,
    padding: 14,
    borderRadius: 16,
    borderWidth: StyleSheet.hairlineWidth,
    marginBottom: 4,
  },
  loadingText: {
    fontFamily: 'Inter_400Regular',
    fontSize: 13,
    flex: 1,
    lineHeight: 18,
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
