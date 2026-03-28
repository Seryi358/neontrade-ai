// Mock react-native-web modules that cause issues in test env
jest.mock('expo-font', () => ({
  useFonts: () => [true],
  loadAsync: jest.fn().mockResolvedValue(undefined),
}));

jest.mock('expo-status-bar', () => ({
  StatusBar: 'StatusBar',
}));

jest.mock('expo-notifications', () => ({
  getPermissionsAsync: jest.fn().mockResolvedValue({ status: 'granted' }),
  requestPermissionsAsync: jest.fn().mockResolvedValue({ status: 'granted' }),
}));

// Mock lightweight-charts (web-only library)
jest.mock('lightweight-charts', () => ({
  createChart: jest.fn(() => ({
    addCandlestickSeries: jest.fn(() => ({
      setData: jest.fn(),
      applyOptions: jest.fn(),
      createPriceLine: jest.fn(),
    })),
    addHistogramSeries: jest.fn(() => ({
      setData: jest.fn(),
      applyOptions: jest.fn(),
    })),
    addLineSeries: jest.fn(() => ({
      setData: jest.fn(),
      applyOptions: jest.fn(),
    })),
    applyOptions: jest.fn(),
    timeScale: jest.fn(() => ({
      fitContent: jest.fn(),
      applyOptions: jest.fn(),
    })),
    remove: jest.fn(),
    resize: jest.fn(),
  })),
  CrosshairMode: { Normal: 0, Magnet: 1 },
}));

// Suppress console.error for expected test warnings
const originalConsoleError = console.error;
console.error = (...args) => {
  // Suppress act() warnings and known test noise
  if (
    typeof args[0] === 'string' &&
    (args[0].includes('act(') || args[0].includes('Not implemented'))
  ) {
    return;
  }
  originalConsoleError(...args);
};

// Global fetch mock
global.fetch = jest.fn();
