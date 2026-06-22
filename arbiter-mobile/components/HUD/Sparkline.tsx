// HUD Sparkline — tiny SVG trend line for hero stats. Renders a polyline
// across the available width plus a soft area fill below. Returns null
// when there are fewer than two points so callers can drop the row.

import React, { useMemo } from 'react';
import { View, StyleSheet } from 'react-native';
import Svg, { Polyline, Polygon } from 'react-native-svg';
import { HUD_COLORS } from './tokens';

export interface SparklineProps {
  data: number[];
  width?: number;
  height?: number;
  color?: string;
  strokeWidth?: number;
  /** Optional baseline render: filled area under the line. */
  fill?: boolean;
}

export const Sparkline: React.FC<SparklineProps> = ({
  data,
  width = 220,
  height = 44,
  color = HUD_COLORS.cyan,
  strokeWidth = 1.5,
  fill = true,
}) => {
  const { line, area } = useMemo(() => {
    if (!data || data.length < 2) return { line: '', area: '' };
    const min = Math.min(...data);
    const max = Math.max(...data);
    const range = max - min || 1;
    const stepX = width / (data.length - 1);
    const points = data
      .map((v, i) => `${(i * stepX).toFixed(2)},${(height - ((v - min) / range) * (height - 4) - 2).toFixed(2)}`)
      .join(' ');
    return {
      line: points,
      area: `0,${height} ${points} ${width},${height}`,
    };
  }, [data, width, height]);

  if (!line) return null;

  return (
    <View style={[styles.wrap, { width, height }]}>
      <Svg width={width} height={height}>
        {fill && <Polygon points={area} fill={color} fillOpacity={0.10} />}
        <Polyline
          points={line}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      </Svg>
    </View>
  );
};

const styles = StyleSheet.create({
  wrap: { alignSelf: 'stretch' },
});

export default Sparkline;
