# How to Publish to the Chrome Web Store

Publishing your "Watched" extension allows anyone to install it easily and ensures automatic updates.

## 1. Prepare Your Package
You need a clean `.zip` file of just your extension code.

1.  **Open Terminal** in your project folder (`watchlist`).
2.  **Zip the `extensions` folder:**
    ```bash
    zip -r watched-extension-v1.zip extensions
    ```
    *(Ensure you are zipping the `extensions` folder, NOT the whole project)*

## 2. Create a Developer Account
1.  Go to the [Chrome Web Store Developer Dashboard](https://chrome.google.com/webstore/developer/dashboard).
2.  Sign in with the Google Account you want to own the extension.
3.  **Register:** You must pay a **one-time $5 fee** to verify your account.

## 3. Upload Your Item
1.  Click **+ New Item**.
2.  Drag and drop your `watched-extension-v1.zip` file.
3.  The Store will read your `manifest.json` and start the listing.

## 4. Fill Out the Listing
You need to provide details for the public page:

*   **Description:** Explain what it does.
    > "Automatically tracks the movies and TV shows you find on Google Search. Connects to your Watched Dashboard to build your viewing history."
*   **Category:** Select **Start Page** or **Search Tools** (or *Entertainment*).
*   **Language:** English.
*   **Graphic Assets:**
    *   **Icon:** `extensions/images/icon128_padded.png` (Required, 96x96 content with padding).
    *   **Store Icon:** `extensions/images/icon128_padded.png` (You can upload this for all required sizes).
    *   **Screenshots:** `extensions/images/screenshot_1.png` and `extensions/images/screenshot_2.png` (1280x800).
    *   **Marquee (Small):** `extensions/images/marquee_promo.png` (440x280).
    *   **Marquee (Large):** `extensions/images/marquee_promo_large.png` (1400x560).
    *   **Global Promo Video:** Optional. Leave blank.

## 5. Privacy Practices (Critical)
Since your `manifest.json` asks for `host_permissions` ("watched.onrender.com") and `cookies` via script injection, you must declare this:

1.  **Privacy Policy URL:** You need a link. You can host a simple MD page on your Render site or GitHub Pages.
2.  **Permissions Justification:**
    *   **ActiveTab/Scripting:** "To identify movie titles on Google Search results."
    *   **Storage/Cookies:** "To authenticate with the user's Watched account to save their history."

    *   **Host Permissions:** "To communicate with the backend API (watched.onrender.com) to save viewing history."

## 6. Test Instructions (Distribution Tab)
The web store requires credentials to test the extension if it's gated by login. Since you use Google Sign-In:

1.  **Username:** "Any valid Google Account"
2.  **Password:** "N/A (Uses Google Sign-In)"
3.  **Additional Instructions:**
    > "1. Install the extension.
    > 2. Visit https://watched.onrender.com/login and sign in with any Google Account.
    > 3. Go to www.google.com and search for a movie (e.g., 'Inception').
    > 4. The Watched overlay will appear on the right side of the results."

## 7. Submit for Review
1.  Click **Submit for Review**.
2.  **Wait:** Reviews typically take **24-48 hours**.
3.  Once approved, you will get a link to your extension on the store!

## Troubleshooting: "Why can't I submit?"
If the button is still disabled:

1.  **Click "Save Draft":** You must save your changes on *every* tab (Store Listing, Privacy, Distribution).
2.  **Check Distribution:** Go to the **Distribution** tab. Ensure you have selected **"All regions"** (or specific countries) so the store knows where to publish it.
3.  **Click the "Why can't I submit?" link:** This link (usually at the top right) will list the *exact* fields missing (e.g., "Missing small promo tile" or "Missing privacy policy").
4.  **Upload the correct Zip:** Ensure you uploaded the `watched-extension-v1.zip` that contains the icons.
