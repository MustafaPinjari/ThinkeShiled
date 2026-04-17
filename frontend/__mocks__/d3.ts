// Minimal D3 stub for Jest (DOM rendering tested via Playwright E2E)
// All scale/selection methods return a chainable stub that is also callable.

function makeChain(): ReturnType<typeof createChain> {
  return createChain();
}

function createChain(): any {
  const fn: any = jest.fn(() => fn);
  fn.domain = jest.fn(() => fn);
  fn.range = jest.fn(() => fn);
  fn.nice = jest.fn(() => fn);
  fn.paddingInner = jest.fn(() => fn);
  fn.bandwidth = jest.fn(() => 20);
  fn.ticks = jest.fn(() => fn);
  fn.tickFormat = jest.fn(() => fn);
  fn.attr = jest.fn(() => fn);
  fn.call = jest.fn(() => fn);
  fn.select = jest.fn(() => fn);
  fn.selectAll = jest.fn(() => fn);
  fn.data = jest.fn(() => fn);
  fn.join = jest.fn(() => fn);
  fn.append = jest.fn(() => fn);
  fn.text = jest.fn(() => fn);
  fn.style = jest.fn(() => fn);
  fn.remove = jest.fn(() => fn);
  return fn;
}

export const select = jest.fn(() => createChain());
export const scaleLinear = jest.fn(() => createChain());
export const scaleBand = jest.fn(() => createChain());
export const axisBottom = jest.fn(() => createChain());
export const max = jest.fn(() => 1);
export const min = jest.fn(() => 0);

export default { select, scaleLinear, scaleBand, axisBottom, max, min };
