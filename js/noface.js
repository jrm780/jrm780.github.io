(function () {
  const noface = document.getElementById('noface');
  const footer = document.querySelector('footer');
  if (!noface || !footer) return;
  footer.addEventListener('mouseenter', () => {
    noface.style.transition = 'none';
    noface.style.transform = ''; // clear pin so CSS default (translateX) applies for entry
    noface.getBoundingClientRect(); // force reflow so browser commits the start position
    noface.style.transition = 'opacity 650ms ease, transform 650ms ease';
    noface.classList.add('visible');
  });
  footer.addEventListener('mouseleave', () => {
    noface.style.transform = 'translateX(0)'; // pin in place before class removal
    noface.style.transition = 'opacity 500ms ease';
    noface.classList.remove('visible');
  });
})();
