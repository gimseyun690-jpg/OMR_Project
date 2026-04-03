const navLinks = Array.from(document.querySelectorAll(".toolbar__nav a"));
const pages = Array.from(document.querySelectorAll(".page"));
const printButton = document.querySelector('[data-action="print"]');

if (printButton) {
  printButton.addEventListener("click", () => {
    window.print();
  });
}

const setActiveLink = () => {
  if (!navLinks.length || !pages.length) return;

  const offset = window.innerHeight * 0.25;
  let activeId = pages[0].id;

  for (const page of pages) {
    const rect = page.getBoundingClientRect();
    if (rect.top <= offset && rect.bottom >= offset) {
      activeId = page.id;
      break;
    }
  }

  navLinks.forEach((link) => {
    const isActive = link.getAttribute("href") === `#${activeId}`;
    link.classList.toggle("is-active", isActive);
  });
};

setActiveLink();
window.addEventListener("scroll", setActiveLink, { passive: true });
