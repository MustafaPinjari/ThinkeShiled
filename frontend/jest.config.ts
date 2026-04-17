import type { Config } from "jest";

const config: Config = {
  testEnvironment: "jsdom",
  setupFilesAfterEnv: ["<rootDir>/jest.setup.ts"],
  transform: {
    "^.+\\.(ts|tsx)$": ["ts-jest", { tsconfig: { jsx: "react-jsx" } }],
  },
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/$1",
    // Stub heavy DOM libraries — visual correctness covered by Playwright E2E
    "^d3$": "<rootDir>/__mocks__/d3.ts",
    "^vis-network$": "<rootDir>/__mocks__/vis-network.ts",
    "\\.(css|scss)$": "<rootDir>/__mocks__/styleMock.ts",
  },
  testMatch: ["**/__tests__/**/*.test.(ts|tsx)"],
  collectCoverageFrom: ["components/**/*.{ts,tsx}"],
};

export default config;
