// PanelWebView — fallback renderer for panel sections that don't yet
// have native components (charts, heatmaps, quadrants, calendar
// heatmaps, comparison matrices). Hosts the inlined HTML/Chart.js
// renderer and auto-sizes its height to the reported content.

import React, { useCallback, useMemo, useRef, useState } from 'react';
import { StyleSheet, View } from 'react-native';
import { WebView, type WebViewMessageEvent } from 'react-native-webview';
import type { Panel } from '../../lib/types';
import { PANEL_RENDERER_HTML } from './panelRendererHtml';

export interface PanelWebViewProps {
  panel: Panel;
  /** Height ceiling — the webview will clamp to this. Default 360. */
  maxHeight?: number;
  /** Initial height before the renderer reports back. Default 240. */
  initialHeight?: number;
  /** Test hook — swap the inner WebView component for one we can fake. */
  WebViewImpl?: typeof WebView;
}

interface RendererMessage {
  type: 'ready' | 'height' | 'error';
  payload: { height?: number; message?: string } | null;
}

export const PanelWebView: React.FC<PanelWebViewProps> = ({
  panel,
  maxHeight = 360,
  initialHeight = 240,
  WebViewImpl = WebView,
}) => {
  const [height, setHeight] = useState(initialHeight);
  const webRef = useRef<WebView | null>(null);
  const panelJson = useMemo(() => JSON.stringify(panel), [panel]);

  const inject = useCallback(() => {
    // Posts the panel payload using both window.postMessage (modern WebView)
    // and document.dispatchEvent (older Android RN-WebView builds).
    const escaped = panelJson.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
    return `
      (function () {
        try {
          var msg = { type: 'panel', payload: JSON.parse('${escaped}') };
          window.postMessage(JSON.stringify(msg), '*');
        } catch (e) {
          if (window.ReactNativeWebView) {
            window.ReactNativeWebView.postMessage(JSON.stringify({ type: 'error', payload: { message: e.message } }));
          }
        }
      })();
      true;
    `;
  }, [panelJson]);

  const onMessage = useCallback(
    (evt: WebViewMessageEvent) => {
      let msg: RendererMessage | null = null;
      try {
        msg = JSON.parse(evt.nativeEvent.data) as RendererMessage;
      } catch {
        return;
      }
      if (!msg) return;
      if (msg.type === 'ready') {
        webRef.current?.injectJavaScript(inject());
      } else if (msg.type === 'height') {
        const reported = Math.ceil(msg.payload?.height ?? 0);
        if (reported > 0) {
          setHeight(Math.min(Math.max(reported, 80), maxHeight));
        }
      }
    },
    [inject, maxHeight],
  );

  return (
    <View style={[styles.wrap, { height }]} testID="panel-webview">
      <WebViewImpl
        ref={(r) => {
          webRef.current = r;
        }}
        originWhitelist={['*']}
        source={{ html: PANEL_RENDERER_HTML }}
        style={styles.web}
        scrollEnabled={false}
        javaScriptEnabled
        domStorageEnabled={false}
        setSupportMultipleWindows={false}
        injectedJavaScript={inject()}
        onMessage={onMessage}
        androidLayerType="hardware"
        // Transparent background — let the parent panel's dark glass show.
        backgroundColor="transparent"
      />
    </View>
  );
};

const styles = StyleSheet.create({
  wrap: { width: '100%', overflow: 'hidden' },
  web: { flex: 1, backgroundColor: 'transparent' },
});

export default PanelWebView;
