---
name: Pi Agents Mobile App
description: Architecture notes for the Expo mobile companion app (artifacts/mobile-agents) that talks to the Pi Flask server.
---

## API Routing
- Pi Flask server: port 8000, mapped to `/` in `artifacts/api-server/.replit-artifact/artifact.toml`
- Express API server: port 8080, mapped to `/node-api`
- All chat endpoints (`/api/chat/data`, `/api/chat/cortona`, `/api/chat/jarvis`, `/api/chat/council`) are served by Flask at the root path
- Mobile app uses `EXPO_PUBLIC_DOMAIN` (injected at bundle time = `$REPLIT_DEV_DOMAIN`) to build the base URL

**Why:** The Expo app calls `https://${EXPO_PUBLIC_DOMAIN}/api/chat/*` — these hit the Flask server (not Express). Do not add chat routes to the Express API spec; they live on the Pi.

## App Structure
- 4 tabs: `index` (Data), `cortona`, `jarvis`, `council`
- Shared `AgentChat` component in `components/AgentChat.tsx` used by Data/Cortona/Jarvis
- Council screen (`council.tsx`) has its own message type for rendering 2-round deliberation
- Markdown renderer in `lib/markdown.tsx` (handles `**bold**`, `# headers`, `- bullets`)
- API client in `lib/api.ts` — `chatData()`, `chatCortona()`, `chatJarvis()`, `chatCouncil()`
- Theme: dark-only palette in `constants/colors.ts` (both light and dark keys = same dark values)
- `app.json` has `userInterfaceStyle: "dark"` to force dark mode

## Design Decisions
- No AsyncStorage in first build — messages are in-memory only (see follow-up task #6)
- No custom server URL in first build (see follow-up task #7)
- Agent accents: Data=#3B82F6, Cortona=#A78BFA, Jarvis=#FBBF24, Council=#2DD4BF
- Inverted FlatList for chat (newest at bottom, no scrollToEnd needed)
- KeyboardAvoidingView from `react-native-keyboard-controller` with `behavior="padding"`
- Headers are custom (headerShown: false) so each screen owns its own header with agent icon + clear button
