/**
 * Simple markdown renderer for React Native.
 * Handles the formatting agents produce: **bold**, # headers, - bullets.
 */

import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

interface MarkdownTextProps {
  content: string;
  textColor: string;
  accentColor: string;
  fontSize?: number;
}

/** Splits a string on **...** markers and alternates bold / normal spans. */
function InlineText({
  text,
  baseColor,
  fontSize,
  bold: defaultBold,
}: {
  text: string;
  baseColor: string;
  fontSize: number;
  bold?: boolean;
}): React.ReactElement {
  const parts = text.split(/\*\*/);
  if (parts.length === 1) {
    return (
      <Text
        style={[
          styles.inline,
          { color: baseColor, fontSize },
          defaultBold ? styles.bold : null,
        ]}
      >
        {text}
      </Text>
    );
  }
  return (
    <>
      {parts.map((part, i) =>
        part ? (
          <Text
            key={i}
            style={[
              styles.inline,
              { color: baseColor, fontSize },
              i % 2 === 1 ? styles.bold : null,
            ]}
          >
            {part}
          </Text>
        ) : null,
      )}
    </>
  );
}

export function MarkdownText({
  content,
  textColor,
  accentColor,
  fontSize = 14,
}: MarkdownTextProps) {
  const lines = content.split('\n');

  const rendered = lines.map((line, idx) => {
    // H1
    if (line.startsWith('# ')) {
      const text = line.slice(2);
      return (
        <Text key={idx} style={[styles.h1, { color: textColor, fontSize: fontSize + 4 }]}>
          <InlineText text={text} baseColor={textColor} fontSize={fontSize + 4} bold />
        </Text>
      );
    }

    // H2
    if (line.startsWith('## ')) {
      const text = line.slice(3);
      return (
        <Text key={idx} style={[styles.h2, { color: textColor, fontSize: fontSize + 2 }]}>
          <InlineText text={text} baseColor={textColor} fontSize={fontSize + 2} bold />
        </Text>
      );
    }

    // H3
    if (line.startsWith('### ')) {
      const text = line.slice(4);
      return (
        <Text key={idx} style={[styles.h3, { color: textColor, fontSize: fontSize + 1 }]}>
          <InlineText text={text} baseColor={textColor} fontSize={fontSize + 1} bold />
        </Text>
      );
    }

    // Bullet: "- " or "* " or "• "
    if (/^[-*•] /.test(line)) {
      const text = line.slice(2);
      return (
        <View key={idx} style={styles.bulletRow}>
          <Text style={[styles.bulletDot, { color: accentColor, fontSize }]}>•</Text>
          <Text style={[styles.bulletText, { color: textColor, fontSize }]}>
            <InlineText text={text} baseColor={textColor} fontSize={fontSize} />
          </Text>
        </View>
      );
    }

    // Indented bullet: "  - " or "  * "
    if (/^ {2,}[-*•] /.test(line)) {
      const text = line.replace(/^ {2,}[-*•] /, '');
      return (
        <View key={idx} style={[styles.bulletRow, styles.indentedBullet]}>
          <Text style={[styles.bulletDot, { color: accentColor, fontSize: fontSize - 1 }]}>◦</Text>
          <Text style={[styles.bulletText, { color: textColor, fontSize: fontSize - 1 }]}>
            <InlineText text={text} baseColor={textColor} fontSize={fontSize - 1} />
          </Text>
        </View>
      );
    }

    // Horizontal rule
    if (line.trim() === '---' || line.trim() === '━━━') {
      return <View key={idx} style={[styles.hr, { backgroundColor: accentColor + '44' }]} />;
    }

    // Empty line
    if (line.trim() === '') {
      return <View key={idx} style={styles.spacer} />;
    }

    // Normal paragraph
    return (
      <Text key={idx} style={[styles.paragraph, { color: textColor, fontSize }]}>
        <InlineText text={line} baseColor={textColor} fontSize={fontSize} />
      </Text>
    );
  });

  return <View style={styles.root}>{rendered}</View>;
}

const styles = StyleSheet.create({
  root: {
    gap: 2,
  },
  inline: {
    lineHeight: 20,
  },
  bold: {
    fontFamily: 'Inter_700Bold',
  },
  h1: {
    fontFamily: 'Inter_700Bold',
    marginTop: 8,
    marginBottom: 4,
    lineHeight: 26,
  },
  h2: {
    fontFamily: 'Inter_600SemiBold',
    marginTop: 6,
    marginBottom: 2,
    lineHeight: 24,
  },
  h3: {
    fontFamily: 'Inter_600SemiBold',
    marginTop: 4,
    marginBottom: 2,
    lineHeight: 22,
  },
  paragraph: {
    fontFamily: 'Inter_400Regular',
    lineHeight: 22,
  },
  bulletRow: {
    flexDirection: 'row',
    gap: 8,
    paddingLeft: 4,
  },
  indentedBullet: {
    paddingLeft: 20,
  },
  bulletDot: {
    fontFamily: 'Inter_700Bold',
    lineHeight: 22,
  },
  bulletText: {
    fontFamily: 'Inter_400Regular',
    flex: 1,
    lineHeight: 22,
  },
  hr: {
    height: 1,
    marginVertical: 8,
  },
  spacer: {
    height: 6,
  },
});
