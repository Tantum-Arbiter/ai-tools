import { ApiError, MOBILE_SAFE_ACTIONS } from '../types';

describe('ApiError', () => {
  it('carries kind and status', () => {
    const e = new ApiError('nope', 401, 'unauthorized');
    expect(e).toBeInstanceOf(Error);
    expect(e.name).toBe('ApiError');
    expect(e.status).toBe(401);
    expect(e.kind).toBe('unauthorized');
    expect(e.message).toBe('nope');
  });
});

describe('MOBILE_SAFE_ACTIONS', () => {
  it('includes open_browser and open_url', () => {
    expect(MOBILE_SAFE_ACTIONS.has('open_browser')).toBe(true);
    expect(MOBILE_SAFE_ACTIONS.has('open_url')).toBe(true);
  });

  it('excludes desktop and unknown actions', () => {
    expect(MOBILE_SAFE_ACTIONS.has('desktop_screenshot')).toBe(false);
    expect(MOBILE_SAFE_ACTIONS.has('launch_app')).toBe(false);
    expect(MOBILE_SAFE_ACTIONS.has('arbitrary')).toBe(false);
  });
});
