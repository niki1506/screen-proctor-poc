// Run in a controlled exam page. Export times relative to the same session/video
// start. Browser events indicate visibility/focus, not which application opened.
// This is a collector example; the POC does not inject it into uploaded videos.
(() => {
  const started = performance.now();
  const events = [];
  const record = (type) => events.push({
    time_seconds: (performance.now() - started) / 1000,
    type
  });
  const hidden = () => { if (document.hidden) record('page_hidden'); };
  const blur = () => record('window_blur');
  const fullscreen = () => { if (!document.fullscreenElement) record('fullscreen_exit'); };
  document.addEventListener('visibilitychange', hidden);
  window.addEventListener('blur', blur);
  document.addEventListener('fullscreenchange', fullscreen);
  window.proctorTelemetry = {
    export: () => JSON.stringify({ events }, null, 2),
    stop: () => {
      document.removeEventListener('visibilitychange', hidden);
      window.removeEventListener('blur', blur);
      document.removeEventListener('fullscreenchange', fullscreen);
    }
  };
})();
