/* SPDX-License-Identifier: AGPL-3.0-only */
(() => {
  const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
  let animation;
  // Lottie Light has no expression evaluator; only the local shape data is loaded.
  if (!motion.matches && window.lottie) {
    animation = window.lottie.loadAnimation({
      container: document.getElementById('maintenance-animation'),
      renderer: 'svg',
      loop: true,
      autoplay: true,
      path: '/__maintenance_assets/maintenance.json',
      rendererSettings: { progressiveLoad: false },
    });
  }
  motion.addEventListener('change', () => {
    if (animation) {
      if (motion.matches) animation.pause();
      else animation.play();
    }
  });
})();
