// Hero panel — single oversized stat with optional delta arrow. Used at
// the top of analysis panels to anchor the answer (e.g. "MRR — $4,820").

import React from 'react';
import { View, StyleSheet } from 'react-native';
import { Stat } from '../HUD';
import type { HeroSpec } from '../../lib/types';

export interface PanelHeroProps {
  hero: HeroSpec;
}

export const PanelHero: React.FC<PanelHeroProps> = ({ hero }) => {
  const props: React.ComponentProps<typeof Stat> = {
    label: hero.label ?? '',
    value: String(hero.value ?? ''),
    tone: 'cyan',
  };
  if (hero.delta !== undefined) props.delta = String(hero.delta);
  if (hero.delta_dir) props.deltaDir = hero.delta_dir;
  return (
    <View style={styles.wrap}>
      <Stat {...props} align="left" />
    </View>
  );
};

const styles = StyleSheet.create({
  wrap: { paddingVertical: 4 },
});

export default PanelHero;
