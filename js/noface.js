(function () {
  const noface = document.getElementById('noface');
  const footer = document.querySelector('footer');
  if (!noface || !footer) return;
  new Image().src = '/images/smtotoro.gif'; // preload so it's cached before first hover
  const characters = [
    { src: '/images/noface.gif', duration: '400ms', right: 'calc(50% - 32px)' },
    { src: '/images/smtotoro.gif', duration: '200ms', right: 'calc(50% - 16px)' },
  ];
  let index = 0;
  footer.addEventListener('mouseenter', () => {
    const { src, duration, right } = characters[index];
    index = (index + 1) % characters.length;
    noface.src = '';
    noface.src = src;
    noface.style.transition = 'none';
    noface.style.transform = ''; // clear pin so CSS default (translateX) applies for entry
    noface.style.right = right;
    noface.getBoundingClientRect(); // force reflow so browser commits the start position
    noface.style.transition = `opacity ${duration} ease, transform ${duration} ease`;
    noface.classList.add('visible');
  });
  footer.addEventListener('mouseleave', () => {
    noface.style.transform = 'translateX(0)'; // pin in place before class removal
    noface.style.transition = 'opacity 500ms ease';
    noface.classList.remove('visible');
  });
})();
