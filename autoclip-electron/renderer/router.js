// AutoClip Electron SPA Router
// Handles navigation without page reloads using fetch + innerHTML

class Router {
  constructor() {
    this.currentPage = null;
    this.init();
  }

  init() {
    document.addEventListener("DOMContentLoaded", () => {
      // Ensure appState is ready
      if (!window.appState) {
        window.appState = {
          hasRunOnce: false,
          isProcessing: false,
          currentJob: null,
          progress: null,
          clips: [],
          logs: []
        };
      }

      setTimeout(() => {
        this.currentPage = this.getInitialPage();
        this.navigate(this.currentPage, false);
        this.attachGlobalListeners();
      }, 50);
    });
  }

  getInitialPage() {
    // First launch: go to empty.html if no projects run yet
    if (!window.appState || !window.appState.hasRunOnce) {
      return "empty";
    }
    // Returning users: go to dashboard
    return "dashboard";
  }

  canAccess(page) {
    // Access control disabled
    return true;
  }

  async navigate(page, shouldInitUI = true) {
    // Access control
    if (!this.canAccess(page)) {
      console.log(`Access denied to ${page}, redirecting to empty`);
      page = "empty";
    }

    // Standardize page name
    if (page === "index") page = "dashboard";

    try {
      const response = await fetch(`${page}.html`);
      if (!response.ok) throw new Error(`Failed to load ${page}.html`);

      const html = await response.text();

      // Parse HTML
      const parser = new DOMParser();
      const doc = parser.parseFromString(html, "text/html");
      const newBody = doc.body.innerHTML;

      // Update Title
      if (doc.title) document.title = doc.title;

      // Handle CSS injection
      this.handleStyles(doc);

      // Replace content
      const appContent = document.getElementById('app-content');
      if (appContent) {
        appContent.innerHTML = newBody;
      } else {
        console.error("App container not found! Replacing body as fallback.");
        document.body.innerHTML = newBody;
      }

      // Update active navigation state
      this.updateActiveNav(page);

      // Update current page
      this.currentPage = page;

      // Re-initialize UI Controller and bindings
      if (window.uiController) {
        // General UI init
        window.uiController.updateUI();

        // Page specific init
        if (page === "new-project") {
          window.uiController.initNewProjectPage();
        }

        // Bind CTA on empty page and dashboard empty state
        this.bindPageSpecificEvents(page);
      }

    } catch (error) {
      console.error("Navigation failed:", error);
    }
  }

  handleStyles(doc) {
    // Remove old page-specific styles
    const oldLinks = document.head.querySelectorAll('link[data-page-style]');
    oldLinks.forEach(link => link.remove());

    // Add new styles
    const newLinks = doc.querySelectorAll('link[rel="stylesheet"]');
    newLinks.forEach(link => {
      const newLink = document.createElement('link');
      newLink.rel = 'stylesheet';
      newLink.href = link.getAttribute('href');
      newLink.setAttribute('data-page-style', 'true');
      document.head.appendChild(newLink);
    });
  }

  updateActiveNav(activePage) {
    const navItems = document.querySelectorAll(".nav-item");
    navItems.forEach((item) => {
      item.classList.remove("active");
      const page = item.dataset.page || this.getPageFromSpan(item);
      if (page === activePage) {
        item.classList.add("active");
      }
    });
  }

  getPageFromSpan(navItem) {
    const spans = navItem.querySelectorAll("span");
    for (const span of spans) {
      const text = span.textContent.trim();
      switch (text) {
        case "Dashboard": return "dashboard";
        case "New Project": return "new-project";
        case "Queue": return "queue";
        case "Logs": return "logs";
        case "Clips": return "clips";
        case "Settings": return "settings";
      }
    }
    return null;
  }

  attachGlobalListeners() {
    if (document.body.dataset.navListenersAttached) return;

    document.addEventListener("click", (e) => {
      // 1. Find the closest nav-item
      const navItem = e.target.closest(".nav-item");
      if (!navItem) return;

      // 2. IMPORTANT: Only prevent default and navigate if it is INSIDE THE SIDEBAR.
      // This prevents conflict with any elements in the main content that might accidentally bubble 
      // or have similar classes.
      if (!navItem.closest('.sidebar')) return;

      e.preventDefault();
      const page = navItem.dataset.page || this.getPageFromSpan(navItem);
      if (page) {
        this.navigate(page);
      }
    });

    document.body.dataset.navListenersAttached = "true";
  }

  bindPageSpecificEvents(page) {
    // Bind "Mulai Project" or "Buat Project Pertama" buttons
    // We look for buttons that link to new-project
    const newProjectBtns = document.querySelectorAll('[onclick*="new-project"]');
    newProjectBtns.forEach(btn => {
      btn.onclick = (e) => {
        e.preventDefault();
        this.navigate('new-project');
      };
    });

    // Also specifically logic mentions "emptyStartBtn"
    const emptyStartBtn = document.getElementById("emptyStartBtn");
    if (emptyStartBtn) {
      emptyStartBtn.onclick = () => this.navigate("new-project");
    }
  }
}

// Initialize router
window.router = new Router();
