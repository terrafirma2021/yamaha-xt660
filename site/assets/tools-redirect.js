// Preserve old workbench bookmarks while the two workspaces have their own URLs.
(() => {
  const flashing = ['#connect', '#backup', '#flash'].includes(location.hash);
  const target = new URL('../' + (flashing ? 'flashing/' : 'tune/'), location.href);
  target.search = location.search;
  target.hash = location.hash;
  location.replace(target.href);
})();
