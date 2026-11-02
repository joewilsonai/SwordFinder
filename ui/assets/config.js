// Public runtime config for static UI pages.
// Override by setting window.SWORDFINDER_CONFIG before loading app scripts.
window.SWORDFINDER_CONFIG = Object.assign(
  {
    seasonYear: 2026,
    appName: "SwordFinder",
  },
  window.SWORDFINDER_CONFIG || {}
);
