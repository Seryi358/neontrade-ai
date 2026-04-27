module.exports = {
  preset: 'jest-expo',
  transformIgnorePatterns: [
    'node_modules/(?!((jest-)?react-native|@react-native(-community)?)|expo(nent)?|@expo(nent)?/.*|@expo-google-fonts/.*|react-navigation|@react-navigation/.*|@sentry/react-native|native-base|react-native-svg|lightweight-charts)',
  ],
  setupFiles: ['./jest.setup.js'],
  moduleNameMapper: {
    '^react-native-svg$': '<rootDir>/__mocks__/reactNativeSvgMock.js',
    '\\.(ttf|otf|png|jpg|jpeg|gif|svg|ico|icns)$': '<rootDir>/__mocks__/fileMock.js',
  },
  testMatch: ['**/__tests__/**/*.test.{ts,tsx}'],
};
