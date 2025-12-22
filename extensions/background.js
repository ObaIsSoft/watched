chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === "log_movie") {

        // 1. Get Token from Cookies
        chrome.cookies.get({ url: "https://watched.onrender.com", name: "access_token" }, (cookie) => {
            const token = cookie ? cookie.value : null;

            const headers = { "Content-Type": "application/json" };
            if (token) {
                headers["Authorization"] = `Bearer ${token}`;
            }

            // 2. Forward Request
            fetch("https://watched.onrender.com/api/log", {
                method: "POST",
                headers: headers,
                body: JSON.stringify(request.payload)
            })
                .then(async response => {
                    if (!response.ok) {
                        // Check for 401 specifically
                        if (response.status === 401) {
                            throw new Error("Unauthorized. Please log in at localhost:8000");
                        }
                        const errorData = await response.json().catch(() => ({}));
                        throw new Error(errorData.detail || "Server Error");
                    }
                    return response.json();
                })
                .then(data => {
                    sendResponse({ success: true, data: data });
                })
                .catch(error => {
                    sendResponse({ success: false, error: error.message });
                });
        });

        return true; // Keep channel open
    }
});