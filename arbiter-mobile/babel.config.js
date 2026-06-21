module.exports = function (api) {
  api.cache(true);
  return {
    presets: ['babel-preset-expo'],
    // Reanimated 4 ships its plugin via react-native-worklets/plugin.
    // It MUST stay last so other plugins run before worklet hoisting.
    plugins: ['react-native-worklets/plugin'],
  };
};
