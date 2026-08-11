import base from './playwright.config.mjs';

export default {
  ...base,
  testMatch: /cot-intelligence\.spec\.mjs$/,
};
