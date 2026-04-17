import "@testing-library/jest-dom";

// Stub ResizeObserver (not available in jsdom)
global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};

// Stub SVGElement methods used by D3
Object.defineProperty(SVGElement.prototype, "getBBox", {
  writable: true,
  value: () => ({ x: 0, y: 0, width: 0, height: 0 }),
});
