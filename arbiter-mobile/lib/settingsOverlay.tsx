// Global settings overlay context. Lives at the root layout so any
// screen can pop the panel without going through the router — the
// settings UI is presentation chrome, not a destination, so a sliding
// overlay is a closer match than a stack route. The panel itself is
// rendered by SettingsPanel via the provider below; consumers only
// touch the open/close hook.

import React, {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
} from 'react';
import { SettingsPanel } from '../components/Settings/SettingsPanel';

interface SettingsOverlayContextValue {
  isOpen: boolean;
  open: () => void;
  close: () => void;
}

const SettingsOverlayContext = createContext<SettingsOverlayContextValue | null>(null);

export const SettingsOverlayProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const open = useCallback(() => setIsOpen(true), []);
  const close = useCallback(() => setIsOpen(false), []);
  const value = useMemo(() => ({ isOpen, open, close }), [isOpen, open, close]);
  return (
    <SettingsOverlayContext.Provider value={value}>
      {children}
      <SettingsPanel visible={isOpen} onClose={close} />
    </SettingsOverlayContext.Provider>
  );
};

export function useSettingsOverlay(): SettingsOverlayContextValue {
  const ctx = useContext(SettingsOverlayContext);
  if (!ctx) {
    throw new Error('useSettingsOverlay must be used inside <SettingsOverlayProvider>');
  }
  return ctx;
}
