// ============================================
// SETTINGS MENU
// ============================================

// ανοίγει / κλείνει το menu του settings
function toggleMenu() {
    const menu = document.getElementById("menu");
    if (!menu) return;

    menu.classList.toggle("open");
}


// ============================================
// THEME LOGIC
// ============================================

// αν το mode είναι auto, κοιτάζει το system theme
function getEffectiveTheme(mode) {
    if (mode === "auto") {
        return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    }
    return mode;
}


// εφαρμόζει το theme στο body
function applyTheme(mode) {
    const effectiveTheme = getEffectiveTheme(mode);
    document.body.classList.remove("dark", "light");
    document.body.classList.add(effectiveTheme);
}


// αλλάζει theme και το αποθηκεύει
function setMode(mode) {
    localStorage.setItem("mode", mode);
    applyTheme(mode);
    updateActiveButtons();
}


// ============================================
// FONT SIZE LOGIC
// ============================================

// αλλάζει μέγεθος γραμματοσειράς και το αποθηκεύει
function setFont(size) {
    document.body.classList.remove("font-small", "font-normal", "font-large");
    document.body.classList.add("font-" + size);
    localStorage.setItem("font", size);
    updateActiveButtons();
}


// ============================================
// ACTIVE BUTTONS
// ============================================

// ενημερώνει ποια buttons είναι active
function updateActiveButtons() {
    const savedMode = localStorage.getItem("mode") || "auto";
    const savedFont = localStorage.getItem("font") || "normal";

    const themeDarkBtn = document.getElementById("theme-dark-btn");
    const themeLightBtn = document.getElementById("theme-light-btn");
    const themeAutoBtn = document.getElementById("theme-auto-btn");

    const fontSmallBtn = document.getElementById("font-small-btn");
    const fontNormalBtn = document.getElementById("font-normal-btn");
    const fontLargeBtn = document.getElementById("font-large-btn");

    if (!themeDarkBtn || !themeLightBtn || !themeAutoBtn || !fontSmallBtn || !fontNormalBtn || !fontLargeBtn) {
        return;
    }

    themeDarkBtn.classList.remove("active");
    themeLightBtn.classList.remove("active");
    themeAutoBtn.classList.remove("active");

    fontSmallBtn.classList.remove("active");
    fontNormalBtn.classList.remove("active");
    fontLargeBtn.classList.remove("active");

    if (savedMode === "dark") {
        themeDarkBtn.classList.add("active");
    } else if (savedMode === "light") {
        themeLightBtn.classList.add("active");
    } else {
        themeAutoBtn.classList.add("active");
    }

    if (savedFont === "small") {
        fontSmallBtn.classList.add("active");
    } else if (savedFont === "large") {
        fontLargeBtn.classList.add("active");
    } else {
        fontNormalBtn.classList.add("active");
    }
}


// ============================================
// PAGE LOAD
// ============================================

// τρέχει όταν φορτώνει η σελίδα
// διαβάζει mode / font από localStorage και τα εφαρμόζει
window.onload = () => {
    const savedMode = localStorage.getItem("mode") || "auto";
    const savedFont = localStorage.getItem("font") || "normal";

    document.body.classList.remove("dark", "light", "font-small", "font-normal", "font-large");

    applyTheme(savedMode);
    document.body.classList.add("font-" + savedFont);

    updateActiveButtons();
};


// ============================================
// SYSTEM THEME CHANGE
// ============================================

// αν ο χρήστης έχει auto mode και αλλάξει το system theme,
// ενημερώνεται αυτόματα και το site
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    const savedMode = localStorage.getItem("mode") || "auto";
    if (savedMode === "auto") {
        applyTheme("auto");
        updateActiveButtons();
    }
});


// ============================================
// CLOSE MENU ON OUTSIDE CLICK
// ============================================

// κλείνει το menu αν γίνει click έξω από αυτό
// αλλά ΜΟΝΟ αν το click δεν είναι ούτε πάνω στο menu ούτε πάνω στο γρανάζι
document.addEventListener("click", function (e) {
    const menu = document.getElementById("menu");
    const gear = document.querySelector(".gear");

    if (!menu || !gear) return;

    if (!menu.contains(e.target) && !gear.contains(e.target)) {
        menu.classList.remove("open");
    }
});