// Stub vis-network for Jest unit tests (graph rendering tested via Playwright E2E)
export const Network = jest.fn().mockImplementation(() => ({
  on: jest.fn(),
  setData: jest.fn(),
  destroy: jest.fn(),
}));
export const DataSet = jest.fn().mockImplementation(() => ({
  add: jest.fn(),
  update: jest.fn(),
  get: jest.fn(() => []),
}));
