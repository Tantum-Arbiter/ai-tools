// Root layout for expo-router. Wraps the navigation stack in the
// gesture-handler root view (needed by reanimated bottom sheet) and
// the credentials provider so every screen can access the API.

import React from 'react';
import { StatusBar } from 'expo-status-bar';
import { Stack } from 'expo-router';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { CredentialsProvider } from '../lib/credentials';

export default function RootLayout() {
  return (
    <GestureHandlerRootView style={{ flex: 1, backgroundColor: '#080f1e' }}>
      <SafeAreaProvider>
        <CredentialsProvider>
          <StatusBar style="light" />
          <Stack
            screenOptions={{
              headerShown: false,
              contentStyle: { backgroundColor: '#080f1e' },
              animation: 'fade',
            }}
          />
        </CredentialsProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
