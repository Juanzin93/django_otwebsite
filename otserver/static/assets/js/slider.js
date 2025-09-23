(function () {
  function makeSlider(root) {
    const viewport = root.querySelector(".slider__viewport");
    const track    = root.querySelector(".slider__track");
    const prev     = root.querySelector(".slider__btn--prev");
    const next     = root.querySelector(".slider__btn--next");
    const dotsBox  = root.querySelector(".slider__dots");
    const slides   = Array.from(track.children);

    let index = 0, timer;

    function configuredPerView() {
      const v = getComputedStyle(root).getPropertyValue("--per-view");
      return parseInt(v || "3", 10);
    }
    function perView() {
      // Don’t show more than we have
      return Math.max(1, Math.min(configuredPerView(), slides.length || 1));
    }
    function metrics() {
      const pv  = perView();
      const gap = parseFloat(getComputedStyle(track).gap) || 0;
      const w   = slides[0]?.getBoundingClientRect().width || viewport.clientWidth / pv;
      const maxIndex = Math.max(0, slides.length - pv);   // last fully-visible start index
      return { pv, gap, w, maxIndex };
    }
    function offsetFor(i) {
      const { gap, w } = metrics();
      return i * (w + gap);
    }

    // Move by ONE thumb (not a full page)
    function go(i) {
      const { maxIndex } = metrics();
      if (i > maxIndex)      index = 0;         // wrap to first
      else if (i < 0)        index = maxIndex;  // wrap to last "page start"
      else                   index = i;

      track.style.transform = `translateX(-${offsetFor(index)}px)`;
      drawDots();
      updateControls();
    }

    function drawDots() {
      const { pv } = metrics();
      const pageCount = Math.max(1, Math.ceil(slides.length / pv));
      const active    = Math.floor(index / pv);

      dotsBox.innerHTML = "";
      for (let i = 0; i < pageCount; i++) {
        const b = document.createElement("button");
        b.className = "dot" + (i === active ? " is-active" : "");
        b.type = "button";
        b.addEventListener("click", () => go(i * pv));
        dotsBox.appendChild(b);
      }
    }

    function updateControls() {
      const single = slides.length <= perView();
      if (prev)    prev.style.display = single ? "none" : "";
      if (next)    next.style.display = single ? "none" : "";
      if (dotsBox) dotsBox.style.display = single ? "none" : "";
    }

    // Buttons
    prev?.addEventListener("click", () => go(index - 1));
    next?.addEventListener("click", () => go(index + 1));
    window.addEventListener("resize", () => go(index));

    // Autoplay (loops)
    const autoplay = root.dataset.autoplay === "true";
    const interval = parseInt(root.dataset.interval || "4000", 10);
    function start(){ if (!autoplay || slides.length <= perView()) return; stop(); timer = setInterval(() => go(index + 1), interval); }
    function stop(){ if (timer) clearInterval(timer); }
    root.addEventListener("mouseenter", stop);
    root.addEventListener("mouseleave", start);
    document.addEventListener("visibilitychange", () => { if (document.hidden) stop(); else start(); });

    go(0);
    start();
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".slider").forEach(makeSlider);
  });
})();
