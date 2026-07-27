import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from '@/components/ui/toaster';
import { TooltipProvider } from '@/components/ui/tooltip';
import { Route, Switch, Router as WouterRouter, Redirect } from 'wouter';
import { SettingsProvider } from './store/settings';
import { ChatProvider } from './store/chat';
import { BottomNav } from './components/BottomNav';
import ChatScreen from './pages/ChatScreen';
import SettingsPage from './pages/SettingsPage';
import NotFound from '@/pages/not-found';

const queryClient = new QueryClient();

function Router() {
  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <div className="flex-1 overflow-hidden">
        <Switch>
          <Route path="/">
            <Redirect to="/data" />
          </Route>
          <Route path="/data">
            <ChatScreen agent="data" />
          </Route>
          <Route path="/cortona">
            <ChatScreen agent="cortona" />
          </Route>
          <Route path="/jarvis">
            <ChatScreen agent="jarvis" />
          </Route>
          <Route path="/council">
            <ChatScreen agent="council" />
          </Route>
          <Route path="/settings" component={SettingsPage} />
          <Route component={NotFound} />
        </Switch>
      </div>
      <BottomNav />
    </div>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <SettingsProvider>
          <ChatProvider>
            <WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, '')}>
              <Router />
            </WouterRouter>
          </ChatProvider>
        </SettingsProvider>
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>
  );
}

export default App;
