(function () {
  const switcher = document.querySelector("[data-account-switcher]");
  if (!switcher) return;

  const trigger = switcher.querySelector("[data-account-trigger]");
  const menu = switcher.querySelector("[data-account-menu]");
  if (!trigger || !menu) return;

  function openMenu() {
    switcher.classList.add("open");
    menu.classList.remove("hidden");
    trigger.setAttribute("aria-expanded", "true");
  }

  function closeMenu() {
    switcher.classList.remove("open");
    menu.classList.add("hidden");
    trigger.setAttribute("aria-expanded", "false");
  }

  trigger.addEventListener("click", function () {
    if (switcher.classList.contains("open")) {
      closeMenu();
      return;
    }
    openMenu();
  });

  document.addEventListener("click", function (event) {
    if (!switcher.contains(event.target)) {
      closeMenu();
    }
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      closeMenu();
    }
  });
})();
