import React, { useState } from 'react';
import { useSettings } from '../store/settings';
import { Server, Info } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

export default function SettingsPage() {
  const { settings, updateSettings } = useSettings();
  const [serverUrl, setServerUrl] = useState(settings.serverUrl);
  const [saved, setSaved] = useState(false);

  const handleSave = () => {
    updateSettings({ serverUrl });
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="flex flex-col h-full bg-background">
      {/* Header */}
      <div className="flex-shrink-0 px-4 py-3 border-b border-border">
        <h1 className="text-lg font-semibold tracking-tight">Settings</h1>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-4 py-6 space-y-6">
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="server-url" className="flex items-center gap-2">
              <Server className="w-4 h-4" />
              Server URL
            </Label>
            <Input
              id="server-url"
              type="url"
              value={serverUrl}
              onChange={(e) => setServerUrl(e.target.value)}
              placeholder="http://100.120.55.121:8000"
              className="bg-card border-input"
              data-testid="input-server-url"
            />
            <div className="flex items-start gap-2 p-3 bg-card border border-card-border rounded-lg">
              <Info className="w-4 h-4 text-muted-foreground mt-0.5 flex-shrink-0" />
              <p className="text-xs text-muted-foreground leading-relaxed">
                Leave blank to use Replit cloud. Enter your Pi's Tailscale IP to connect directly
                (e.g., <span className="font-mono">http://100.120.55.121:8000</span>).
              </p>
            </div>
          </div>

          <Button
            onClick={handleSave}
            className="w-full"
            data-testid="button-save-settings"
          >
            {saved ? 'Saved!' : 'Save Settings'}
          </Button>
        </div>

        <div className="pt-6 border-t border-border">
          <h2 className="text-sm font-semibold mb-3">About Pi Assistant</h2>
          <p className="text-xs text-muted-foreground leading-relaxed">
            Pi Assistant connects you to your personal AI command center running on a Raspberry Pi.
            Chat with specialized agents for sports analytics, research, and general intelligence.
          </p>
        </div>
      </div>
    </div>
  );
}
