// Heuristic: Find the Knowledge Graph Title
function findAnchor() {
    return document.querySelector('[data-attrid="title"]');
}

// Show a simple toast notification
function showToast(message, type = 'success') {
    let toast = document.querySelector('.watched-toast');
    if (!toast) {
        toast = document.createElement('div');
        toast.className = 'watched-toast';
        document.body.appendChild(toast);
    }

    toast.innerText = message;
    toast.className = `watched-toast ${type} show`;

    setTimeout(() => {
        toast.classList.remove('show');
    }, 3000);
}

function handleNativeClick(e, status) {
    const anchor = findAnchor();
    if (!anchor) return;

    // Extract Data
    // For native buttons, the title is usually cleaner, but we still ensure we don't grab extra noise
    let titleText = anchor.textContent.trim();

    // Fallback: sometimes title is in a child
    if (anchor.firstChild && anchor.firstChild.nodeType === Node.TEXT_NODE) {
        titleText = anchor.firstChild.nodeValue.trim();
    }

    // Try to find year and media type hint
    let year = null;
    let mediaType = null;

    const subtitle = document.querySelector('[data-attrid="subtitle"]');
    if (subtitle) {
        const text = subtitle.innerText;
        // Year
        const yearMatch = text.match(/\b(19|20)\d{2}\b/);
        if (yearMatch) year = yearMatch[0];

        // TV Hint
        if (text.match(/(season|series|episode)/i)) {
            mediaType = 'tv';
        }
    }

    // Send to Background
    chrome.runtime.sendMessage({
        action: "log_movie",
        payload: { title: titleText, year: year, status: status, media_type: mediaType }
    }, (response) => {
        if (response && response.success) {
            const statusText = status === 'watched' ? 'Watched' : 'Watchlist';
            const msg = response.note === "Already in watchlist"
                ? `already in ${statusText}`
                : `saved to ${statusText}`;
            showToast(`✔ "${titleText}" ${msg}`);
        } else {
            console.error("Watched Error:", response);
            showToast(`⚠ Error saving "${titleText}"`, 'error');
        }
    });
}

// Function to attach listeners to Google's buttons
function attachListeners() {
    // We look for elements with role="button" that contain specific text
    // This is a heuristic and might change if Google changes their UI
    const buttons = document.querySelectorAll('[role="button"]');
    // console.log("Watched: Found", buttons.length, "buttons"); // Too noisy? maybe debug level

    buttons.forEach(btn => {
        if (btn.dataset.watchedListenerAttached) return;

        // Use textContent for broader matching, create a cleaner version
        const text = btn.textContent.toLowerCase().trim();

        // Debugging specific potential candidates
        // if (text.includes('watch')) console.log("Watched candidate:", text, btn);

        if (text.includes('want to watch')) {
            console.log("Watched: Attaching to 'Want to watch' button", btn);
            btn.addEventListener('click', (e) => handleNativeClick(e, 'watchlist'));
            btn.dataset.watchedListenerAttached = "true";
            // Optional: visual indicator that we attached successfully? changing border color? 
            // Best to keep it invisible as requested.
        } else if (text.includes('watched') && !text.includes('want to')) {
            console.log("Watched: Attaching to 'Watched' button", btn);
            btn.addEventListener('click', (e) => handleNativeClick(e, 'watched'));
            btn.dataset.watchedListenerAttached = "true";
        }
    });
}

// --- GOOGLE COLLECTIONS (WATCHLIST) SCRAPER ---
if (window.location.href.includes('google.com/save')) {
    initCollectionImporter();
}

function initCollectionImporter() {
    const btn = document.createElement('button');
    btn.className = 'watched-import-fab';
    btn.innerText = 'Import to Watched';
    btn.onclick = importAll;
    document.body.appendChild(btn);
}

async function importAll() {
    // 1. Find Items
    // Heuristic: Grid items in Google Collections often change class names. 
    // Look for A tags with specific attributes or role="listitem" containers.
    // A reliable selector for the "Saved" grid items:
    const items = document.querySelectorAll('div[data-id]');

    if (items.length === 0) {
        showToast("No items found. Scroll down to load more?", "error");
        return;
    }

    showToast(`Found ${items.length} items. Starting import...`);

    let count = 0;
    for (const item of items) {
        // Extract Title
        // Usually in a div/h3 with specific class. Let's try finding the longest text node or specific tag.
        // Google Save cards usually have an image and a title below.

        // Strategy: deepest non-empty text node?
        // Or aria-label?
        let title = item.innerText.split('\n')[0]; // Often the first line is title

        // Clean up
        if (!title) continue;

        // Extract Image (optional, for visual feedback)
        const img = item.querySelector('img');
        const imgUrl = img ? img.src : null;

        // Send to Background
        chrome.runtime.sendMessage({
            action: "log_movie",
            payload: {
                title: title,
                status: 'watchlist',
                media_type: null // Check if we can detect? hard. Let backend fuzzy match.
            }
        }, (response) => {
            if (response && response.success) {
                console.log(`Imported: ${title}`);
            }
        });

        count++;
        // Slight delay to not nuke the backend
        await new Promise(r => setTimeout(r, 200));
    }

    showToast(`Imported ${count} items!`);
}

// --- GOOGLE SEARCH SCRAPER (Original) ---
if (window.location.href.includes('search')) {
    // Observe DOM changes (Google is a dynamic SPA)
    const observer = new MutationObserver((mutations) => {
        attachListeners();
    });
    observer.observe(document.body, { childList: true, subtree: true });
    // Initial run
    attachListeners();
}
// ... (Keep existing helpers like findAnchor, handleNativeClick usually, but need to attach them only if search)