// ============================================
// SETTINGS MENU
// ============================================

// ανοίγει / κλείνει το menu του settings
function toggleMenu() {
    document.getElementById("menu").classList.toggle("open");
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

    document.getElementById("theme-dark-btn").classList.remove("active");
    document.getElementById("theme-light-btn").classList.remove("active");
    document.getElementById("theme-auto-btn").classList.remove("active");

    document.getElementById("font-small-btn").classList.remove("active");
    document.getElementById("font-normal-btn").classList.remove("active");
    document.getElementById("font-large-btn").classList.remove("active");

    if (savedMode === "dark") {
        document.getElementById("theme-dark-btn").classList.add("active");
    } else if (savedMode === "light") {
        document.getElementById("theme-light-btn").classList.add("active");
    } else {
        document.getElementById("theme-auto-btn").classList.add("active");
    }

    if (savedFont === "small") {
        document.getElementById("font-small-btn").classList.add("active");
    } else if (savedFont === "large") {
        document.getElementById("font-large-btn").classList.add("active");
    } else {
        document.getElementById("font-normal-btn").classList.add("active");
    }
}


// ============================================
// PAGE LOAD
// ============================================

// τρέχει όταν φορτώνει η σελίδα
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
document.addEventListener("click", function(e) {
    const menu = document.getElementById("menu");
    const gear = document.querySelector(".gear");

    if (!menu.contains(e.target) && !gear.contains(e.target)) {
        menu.classList.remove("open");
    }
});